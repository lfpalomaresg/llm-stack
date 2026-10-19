#!/usr/bin/env python3
"""opencode-watchdog — vigilante EXTERNO de bucles de opencode (stdlib, Python >= 3.9).

Por qué existe: el tope `steps` de opencode no frena los reintentos por error (no cuentan
como pasos). Incidentes: 17/10/2026, 916 `stream error` en 21 h en una sesión de
subagente; 11/10/2026, 60 en 37 min.

Qué hace cada ejecución (LaunchAgent cada 60 s):
  1. Lee SOLO las líneas nuevas de ~/.local/share/opencode/log/opencode.log desde el
     offset guardado en ~/.local/state/opencode-watchdog/state.json.
       - Primera ejecución (sin estado): se posiciona al FINAL y no actúa sobre histórico.
       - Si el log rota (otro inodo) o encoge: relee desde 0 pero descarta toda línea con
         timestamp <= último ya procesado (no reprocesa histórico).
       - Una línea sin '\\n' final se deja para la siguiente pasada.
  2. Ventana deslizante de 10 min por session.id (tiempo = timestamp del log):
       >= 15 `message="stream error"`  o  >= 12 `message=stream agent=compaction`.
  3. Acción: SIGTERM al proceso opencode culpable, SIGKILL a los 10 s si sigue vivo,
     notificación macOS y línea en ~/llm-stack/opencode-watchdog.log.
     Una vez por sesión cada 10 min. Nunca actúa sobre eventos de hace > 15 min.

Mapeo sesión -> pid (investigado en el log real 19/10/2026):
  - `run=` es un id POR PROCESO: un proceso opencode escribe siempre el mismo run= (aunque
    cree varias "creating instance"), y el log NO registra el pid.
  - El primer timestamp de cada run= cae 1-2 s después del arranque (lstart) de su proceso
    (verificado en los 8 opencode vivos ese día).
  - Criterio: candidato = proceso cuyo comm termina en "/opencode" (o es "opencode"),
    con 0 <= primer_ts(run) - lstart <= 10 s (tolerancia -1 s por redondeo), y que tiene
    abierto el log (lsof). Debe haber EXACTAMENTE uno; si hay 0 o varios, NO se mata nada
    y se registra pid=?. Antes del SIGKILL se re-verifica la identidad (pid+lstart+comm).
  - Matar el proceso corta también la sesión padre de ese proceso (los subagentes corren
    dentro del mismo proceso opencode). No se tocan sus hijos (MCP, node...): solo opencode.

Uso:
  opencode-watchdog.py            # modo normal (lo que ejecuta el LaunchAgent)
  opencode-watchdog.py --dry-run  # detecta y registra, no mata ni notifica
Desactivar sin desinstalar: crear ~/.local/state/opencode-watchdog/disabled
"""
import argparse
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone

HOME = os.path.expanduser("~")
DEFAULT_LOG = os.path.join(HOME, ".local/share/opencode/log/opencode.log")
STATE_DIR = os.path.join(HOME, ".local/state/opencode-watchdog")
DEFAULT_STATE = os.path.join(STATE_DIR, "state.json")
DISABLE_FLAG = os.path.join(STATE_DIR, "disabled")
DEFAULT_ACTION_LOG = os.path.join(HOME, "llm-stack/opencode-watchdog.log")

WINDOW_S = 600            # ventana deslizante (10 min)
ERR_THRESHOLD = 15        # stream error en la ventana
CMP_THRESHOLD = 12        # compactaciones en la ventana
STALE_S = 900             # no actuar sobre eventos de hace más de 15 min
COOLDOWN_S = 600          # una acción por sesión cada 10 min
START_TOL = (-1.0, 10.0)  # primer_ts(run) - lstart admitido, en segundos
KILL_GRACE_S = 10.0       # SIGTERM -> espera -> SIGKILL
MAX_READ_BYTES = 64 * 1024 * 1024
ACTED_TTL_S = 86400

FIELD_RE = re.compile(r'([A-Za-z0-9_.]+)=("(?:\\.|[^"\\])*"|\S*)')


# ---------------------------------------------------------------- parseo del log
def parse_line(line):
    """key=value (valores entre comillas con escapes). Gana la PRIMERA aparición de
    cada clave, así el texto de un error no pisa los campos reales."""
    fields = {}
    for m in FIELD_RE.finditer(line):
        key, val = m.group(1), m.group(2)
        if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
            val = re.sub(r'\\(.)', r'\1', val[1:-1])
        fields.setdefault(key, val)
    return fields


def parse_ts(s):
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return None


def classify(fields):
    msg = fields.get("message")
    if msg == "stream error":
        return "err"
    if msg == "stream" and fields.get("agent") == "compaction":
        return "cmp"
    return None


# ---------------------------------------------------------------- procesos (macOS)
def list_processes():
    """[(pid, lstart_epoch, comm)] vía ps. Solo pid/lstart/comm: nunca argv (hay
    procesos con tokens en la línea de comandos)."""
    env = dict(os.environ, LC_ALL="C", LANG="C")
    out = subprocess.run(["/bin/ps", "-axo", "pid=,lstart=,comm="], capture_output=True,
                         text=True, env=env, timeout=15).stdout
    procs = []
    for ln in out.splitlines():
        parts = ln.split()
        if len(parts) < 7:
            continue
        try:
            pid = int(parts[0])
            lstart = time.mktime(time.strptime(" ".join(parts[1:6]), "%a %b %d %H:%M:%S %Y"))
        except ValueError:
            continue
        procs.append((pid, lstart, " ".join(parts[6:])))
    return procs


def is_opencode(comm):
    return os.path.basename(comm.strip()) == "opencode"


def holds_log_lsof(pid, log_path):
    try:
        out = subprocess.run(["/usr/sbin/lsof", "-a", "-p", str(pid), "-Fn"],
                             capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    target = os.path.realpath(log_path)
    return any(ln[1:] == target or os.path.realpath(ln[1:]) == target
               for ln in out.splitlines() if ln.startswith("n"))


def _alive_same(proc, proc_lister):
    return any(p[0] == proc[0] and abs(p[1] - proc[1]) < 1.5 and is_opencode(p[2])
               for p in proc_lister())


def make_real_killer(proc_lister=list_processes, grace=KILL_GRACE_S):
    def kill(proc):
        pid = proc[0]
        if not _alive_same(proc, proc_lister):
            return "ya no existe"
        os.kill(pid, signal.SIGTERM)
        deadline = time.time() + grace
        while time.time() < deadline:
            time.sleep(0.5)
            if not _alive_same(proc, proc_lister):
                return "SIGTERM"
        if _alive_same(proc, proc_lister):     # misma identidad: no es un pid reutilizado
            os.kill(pid, signal.SIGKILL)
            return "SIGTERM+SIGKILL"
        return "SIGTERM"
    return kill


def notify_macos(text):
    esc = text.replace("\\", "\\\\").replace('"', '\\"')
    try:
        subprocess.run(["/usr/bin/osascript", "-e",
                        'display notification "%s" with title "opencode-watchdog"' % esc],
                       capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


# ---------------------------------------------------------------- mapeo run -> pid
def first_ts_of_run(log_path, run):
    """Primer timestamp con ese run= en el log actual (lectura binaria, rara: solo al
    actuar)."""
    needle = (" run=%s " % run).encode()
    try:
        with open(log_path, "rb") as f:
            for raw in f:
                if needle in raw:
                    return parse_ts(parse_line(raw.decode("utf-8", "replace")).get("timestamp"))
    except OSError:
        pass
    return None


def resolve_process(run, run_first, procs, holds_log, log_path):
    """Devuelve (proc, None) o (None, motivo)."""
    if run_first is None:
        return None, "sin timestamp de arranque para run=%s" % run
    cands = [p for p in procs if is_opencode(p[2])
             and START_TOL[0] <= run_first - p[1] <= START_TOL[1]]
    cands = [p for p in cands if holds_log(p[0], log_path)]
    if len(cands) == 1:
        return cands[0], None
    if not cands:
        return None, "ningún proceso opencode arrancó con run=%s" % run
    return None, "ambiguo: %d procesos opencode encajan" % len(cands)


# ---------------------------------------------------------------- estado
def load_state(path):
    try:
        with open(path) as f:
            st = json.load(f)
        if isinstance(st, dict) and "offset" in st and "inode" in st:
            return st
    except (OSError, ValueError):
        pass
    return None


def save_state(path, st):
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f)
    os.replace(tmp, path)


def append_action(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a") as f:
        f.write(text + "\n")


def _local_iso(t):
    return datetime.fromtimestamp(t).astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------- una pasada
def run_once(log_path=DEFAULT_LOG, state_path=DEFAULT_STATE, action_log_path=DEFAULT_ACTION_LOG,
             dry_run=False, now=None, killer=None, notifier=None, proc_lister=None,
             holds_log=None, out=None):
    now = time.time() if now is None else now
    proc_lister = proc_lister or list_processes
    holds_log = holds_log or holds_log_lsof
    killer = killer or make_real_killer(proc_lister)
    notifier = notifier or notify_macos
    out = out or sys.stdout

    try:
        st_log = os.stat(log_path)
    except OSError:
        print("log no encontrado: %s (nada que hacer)" % log_path, file=out)
        return 0

    state = load_state(state_path)
    if state is None:
        save_state(state_path, {"inode": st_log.st_ino, "offset": st_log.st_size,
                                "last_ts": None, "sessions": {}, "acted": {}, "runs": {}})
        print("%s inicio: posicionado al final del log (offset %d), sin tocar el histórico"
              % (_local_iso(now), st_log.st_size), file=out)
        return 0

    offset = int(state.get("offset", 0))
    min_ts = None
    if st_log.st_ino != state.get("inode") or st_log.st_size < offset:
        print("%s log rotado/encogido: releo desde 0 descartando ts <= %s"
              % (_local_iso(now), state.get("last_ts")), file=out)
        offset = 0
        min_ts = state.get("last_ts")
    if st_log.st_size - offset > MAX_READ_BYTES:
        print("%s %d bytes pendientes (> tope): salto al final"
              % (_local_iso(now), st_log.st_size - offset), file=out)
        offset = st_log.st_size

    with open(log_path, "rb") as f:
        f.seek(offset)
        data = f.read(st_log.st_size - offset)
    cut = data.rfind(b"\n")
    chunk = data[:cut + 1] if cut >= 0 else b""
    new_offset = offset + len(chunk)

    sessions = state.get("sessions", {})
    acted = state.get("acted", {})
    runs = state.get("runs", {})
    last_ts = state.get("last_ts")
    killed_runs = {}
    triggers = []

    for raw in chunk.splitlines():
        line = raw.decode("utf-8", "replace")
        if "timestamp=" not in line:
            continue
        fields = parse_line(line)
        ts = parse_ts(fields.get("timestamp"))
        if ts is None:
            continue
        if min_ts is not None and ts <= min_ts:
            continue
        last_ts = ts if last_ts is None else max(last_ts, ts)
        run = fields.get("run")
        if run and run not in runs:
            runs[run] = ts
        kind = classify(fields)
        sid = fields.get("session.id")
        if kind is None or not sid:
            continue
        s = sessions.setdefault(sid, {"err": [], "cmp": [], "run": run})
        s["run"] = run or s.get("run")
        s[kind].append(ts)
        for k in ("err", "cmp"):
            s[k] = [t for t in s[k] if t > ts - WINDOW_S]
        n_err, n_cmp = len(s["err"]), len(s["cmp"])
        if n_err >= ERR_THRESHOLD:
            reason = "%d stream error en %d min" % (n_err, WINDOW_S // 60)
        elif n_cmp >= CMP_THRESHOLD:
            reason = "%d agent=compaction en %d min" % (n_cmp, WINDOW_S // 60)
        else:
            continue
        if ts < now - STALE_S:
            continue                       # evento antiguo: nunca se actúa sobre él
        if sid in acted and ts - acted[sid] < COOLDOWN_S:
            continue
        acted[sid] = ts
        s["err"], s["cmp"] = [], []
        triggers.append((sid, s["run"], reason, ts))

    for sid, run, reason, ev_ts in triggers:
        result = act(sid, run, reason, ev_ts, log_path, runs, dry_run, now, killer, notifier,
                     proc_lister, holds_log, killed_runs)
        append_action(action_log_path, result)
        print(result, file=out)

    # Poda del estado
    ref = max(last_ts or now, now)
    sessions = {k: v for k, v in sessions.items()
                if any(t > ref - WINDOW_S for t in v.get("err", []) + v.get("cmp", []))}
    acted = {k: v for k, v in acted.items() if v > ref - ACTED_TTL_S}
    live_runs = {v.get("run") for v in sessions.values()}
    runs = {k: v for k, v in runs.items() if k in live_runs or v > ref - 7 * 86400}

    save_state(state_path, {"inode": st_log.st_ino, "offset": new_offset, "last_ts": last_ts,
                            "sessions": sessions, "acted": acted, "runs": runs})
    return 0


def act(sid, run, reason, ev_ts, log_path, runs, dry_run, now, killer, notifier, proc_lister,
        holds_log, killed_runs):
    head = "fecha=%s ts_log=%s session.id=%s run=%s motivo=\"%s\"" % (
        _local_iso(now), _local_iso(ev_ts), sid, run, reason)
    if run in killed_runs:
        return "%s pid=%s accion=\"ya cortado en esta pasada\"" % (head, killed_runs[run])
    candidates = [t for t in (first_ts_of_run(log_path, run), runs.get(run)) if t is not None]
    run_first = min(candidates) if candidates else None
    try:
        proc, why = resolve_process(run, run_first, proc_lister(), holds_log, log_path)
    except Exception as e:  # noqa: BLE001 - un fallo de ps/lsof no debe tumbar la pasada
        proc, why = None, "error resolviendo pid: %s" % e
    if proc is None:
        if not dry_run:
            notifier("Bucle en %s (%s) — pid no identificado, NO se ha matado nada"
                     % (sid, reason))
        return "%s pid=? accion=\"ninguna (%s)%s\"" % (head, why, " dry-run" if dry_run else "")
    if dry_run:
        return "%s pid=%d accion=\"dry-run: se habría enviado SIGTERM\"" % (head, proc[0])
    try:
        res = killer(proc)
    except Exception as e:  # noqa: BLE001
        res = "fallo al matar: %s" % e
    killed_runs[run] = proc[0]
    notifier("Cortado opencode pid %d: %s (%s)" % (proc[0], reason, sid))
    return "%s pid=%d accion=\"%s\"" % (head, proc[0], res)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Vigilante externo de bucles de opencode")
    ap.add_argument("--dry-run", action="store_true", help="solo registra, no mata ni notifica")
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--state", default=DEFAULT_STATE)
    ap.add_argument("--action-log", default=DEFAULT_ACTION_LOG)
    args = ap.parse_args(argv)
    if os.path.exists(DISABLE_FLAG):
        return 0
    os.makedirs(os.path.dirname(args.state), exist_ok=True)
    with open(args.state + ".lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("otra instancia en curso; salgo")
            return 0
        try:
            return run_once(args.log, args.state, args.action_log, dry_run=args.dry_run)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            return 1


if __name__ == "__main__":
    sys.exit(main())
