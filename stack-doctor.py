#!/usr/bin/env python3
"""stack-doctor — chequeo de salud del stack antes de una sesión larga.

Detecta las regresiones que ya han costado tiempo o panics (10 comprobaciones):
  1. LiteLLM responde en :4000
  2. LM Studio responde en :1234
  3. drift de alias entre LiteLLM y opencode
  4. MCP de más (esquemas que se pagan en cada turno)
  5. harness inflado (tokens fijos por turno)
  6. RAM sin sitio para el siguiente modelo
  7. watchdog instalado (script + LaunchAgent)
  8. watchdog cargado en launchd
  9. agy-bridge responde en :4010 (auditor-free / gpt-oss-free)
 10. higiene de la config (git, .bak, skills huérfanas)

No arranca ni para nada: solo mide e informa.

Uso:
  ~/llm-stack/.venv/bin/python3 ~/llm-stack/stack-doctor.py
  ... --quiet      solo problemas (para colgar del «arranca»)

Salida: OK / AVISO / FALLO por comprobación. Exit 1 si hay algún FALLO.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

HOME = Path.home()
OPENCODE_DIR = HOME / ".config" / "opencode"
OPENCODE_JSON = OPENCODE_DIR / "opencode.json"
AGENTS_MD = OPENCODE_DIR / "AGENTS.md"
STACK = HOME / "llm-stack"
GEN_MODELS = STACK / "gen-opencode-models.py"
SKILLS_DIR = HOME / ".agents" / "skills"
WATCHDOG = "com.luisfran.opencode-watchdog"
WATCHDOG_SH = STACK / "opencode-watchdog.sh"
WATCHDOG_PLIST = HOME / "Library" / "LaunchAgents" / f"{WATCHDOG}.plist"
LITELLM = "http://localhost:4000"
LMSTUDIO = "http://localhost:1234"
AGY_BRIDGE = "http://localhost:4010"

OK, WARN, FAIL = "OK", "AVISO", "FALLO"
results: list[tuple[str, str, str]] = []


def add(level: str, name: str, msg: str) -> None:
    results.append((level, name, msg))


def http_ok(url: str, timeout: float = 4.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def check_litellm() -> None:
    if http_ok(f"{LITELLM}/health/liveliness"):
        add(OK, "LiteLLM", "responde en :4000")
    else:
        add(FAIL, "LiteLLM", "no responde en :4000 — opencode no tendrá modelos")


def check_lmstudio() -> None:
    if http_ok(f"{LMSTUDIO}/api/v0/models"):
        add(OK, "LM Studio", "responde en :1234")
    else:
        add(WARN, "LM Studio", "no responde en :1234 — los alias locales fallarán")


def check_agy_bridge() -> None:
    if http_ok(f"{AGY_BRIDGE}/v1/models"):
        add(OK, "agy-bridge", "responde en :4010 · SSE para auditor-free/gpt-oss-free")
    else:
        add(WARN, "agy-bridge", "no responde en :4010 — auditor-free y gpt-oss-free caerán")


def check_alias_parity() -> None:
    if not GEN_MODELS.exists():
        add(WARN, "alias", "falta gen-opencode-models.py — sin validador")
        return
    venv_py = STACK / ".venv" / "bin" / "python3"
    interp = str(venv_py) if venv_py.exists() else sys.executable
    proc = subprocess.run(
        [interp, str(GEN_MODELS), "--check"],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        add(OK, "alias", proc.stdout.strip() or "en sincronía")
    else:
        detail = (proc.stdout + proc.stderr).strip().splitlines()
        first = detail[-1] if detail else "drift"
        add(FAIL, "alias", f"drift LiteLLM↔opencode: {first}")


def check_mcp() -> None:
    try:
        cfg = json.loads(OPENCODE_JSON.read_text(encoding="utf-8"))
    except Exception as exc:
        add(FAIL, "MCP", f"opencode.json ilegible: {exc}")
        return

    mcp = cfg.get("mcp", {})
    enabled = [k for k, v in mcp.items() if v.get("enabled")]
    denied = {
        k.split("_*")[0]
        for k in cfg.get("permission", {})
        if k.endswith("_*") and cfg["permission"][k] == "deny"
    }
    # Un MCP denegado globalmente puede habilitarse SOLO dentro de un agente
    # (frontmatter `agent/*.md` con "<server>_*: allow"). Eso no es contradicción.
    def allow_in_agent(prefix: str) -> bool:
        agent_dir = OPENCODE_DIR / "agent"
        if not agent_dir.is_dir():
            return False
        pat = re.compile(r'["\']?' + re.escape(prefix) + r'_\*["\']?\s*:\s*allow')
        for f in agent_dir.glob("*.md"):
            try:
                if pat.search(f.read_text(encoding="utf-8")):
                    return True
            except OSError:
                continue
        return False

    contradictory = [
        k for k in enabled
        if (k in denied or k.replace("-", "_") in denied) and not allow_in_agent(k)
    ]

    if contradictory:
        add(FAIL, "MCP", f"activos y denegados a la vez: {', '.join(contradictory)}")
    elif len(enabled) > 6:
        add(WARN, "MCP", f"{len(enabled)} activos ({', '.join(enabled)}) — cada uno cuesta esquemas")
    else:
        add(OK, "MCP", f"{len(enabled)} activos ({', '.join(enabled)})")


def check_harness() -> None:
    if not AGENTS_MD.exists():
        add(FAIL, "harness", "no existe AGENTS.md")
        return
    size = AGENTS_MD.stat().st_size
    ref = OPENCODE_DIR / "ref"
    extra = ""
    if ref.is_dir():
        extra = f" · {len(list(ref.glob('*.md')))} refs bajo demanda"
    if size > 12288:
        add(FAIL, "harness", f"AGENTS.md {size} B — inflado, riesgo de livelock de compactación{extra}")
    elif size > 8192:
        add(WARN, "harness", f"AGENTS.md {size} B — por encima del objetivo (~5 KB){extra}")
    else:
        add(OK, "harness", f"AGENTS.md {size} B (~{size // 4} tokens/turno){extra}")


def check_ram() -> None:
    try:
        total = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout)
    except Exception:
        add(WARN, "RAM", "no se pudo leer hw.memsize")
        return

    loaded: list[tuple[str, float]] = []
    try:
        out = subprocess.run(["lms", "ps"], capture_output=True, text=True).stdout
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 4:
                continue
            try:
                size_gb = float(parts[3])
            except ValueError:
                continue
            loaded.append((parts[0], size_gb))
    except Exception:
        pass

    free_pct = None
    try:
        out = subprocess.run(["memory_pressure", "-Q"], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if "free percentage" in line:
                free_pct = int(line.rsplit(":", 1)[1].strip().rstrip("%"))
    except Exception:
        pass

    gb = 1024**3
    used = sum(s for _, s in loaded)
    names = ", ".join(f"{n} ({s:.1f} GB)" for n, s in loaded) if loaded else "ninguno"
    msg = f"{len(loaded)} cargado(s): {names}"
    if free_pct is not None:
        msg += f" · sistema al {free_pct}% libre de {total / gb:.0f} GB"

    if free_pct is not None and free_pct < 10:
        add(FAIL, "RAM", msg + " — sin sitio para otro modelo")
    elif free_pct is not None and free_pct < 25:
        add(WARN, "RAM", msg + " — solo cabe un modelo pequeño")
    elif used + 17 > total / gb * 0.9:
        add(WARN, "RAM", msg + " — un grande más (17 GB) no cabría")
    else:
        add(OK, "RAM", msg)


def check_watchdog_install() -> None:
    problemas = []
    if not WATCHDOG_SH.is_file():
        problemas.append("falta opencode-watchdog.sh")
    elif not os.access(WATCHDOG_SH, os.X_OK):
        problemas.append("opencode-watchdog.sh no es ejecutable")
    if not WATCHDOG_PLIST.is_file():
        problemas.append("falta el LaunchAgent")
    if problemas:
        add(FAIL, "watchdog-install", "instalación incompleta: " + ", ".join(problemas))
    else:
        add(OK, "watchdog-install", "script + LaunchAgent presentes")


def check_watchdog_loaded() -> None:
    try:
        out = subprocess.run(["launchctl", "list"], capture_output=True, text=True).stdout
    except Exception:
        add(WARN, "watchdog-load", "launchctl no disponible")
        return
    if WATCHDOG in out:
        add(OK, "watchdog-load", f"{WATCHDOG} cargado (freno anti-bucle activo)")
    else:
        add(WARN, "watchdog-load", f"{WATCHDOG} no está cargado — sin freno anti-bucle")


def check_higiene() -> None:
    problems: list[str] = []
    level = WARN

    baks = list(OPENCODE_DIR.glob("*.bak.*")) + list((OPENCODE_DIR / "agent").glob("*.bak.*"))
    if baks:
        problems.append(f"{len(baks)} .bak en la config (el git ya los hace innecesarios)")

    if (OPENCODE_DIR / ".git").is_dir():
        proc = subprocess.run(
            ["git", "-C", str(OPENCODE_DIR), "status", "--porcelain"],
            capture_output=True,
            text=True,
        )
        dirty = [l for l in proc.stdout.splitlines() if l.strip()]
        if dirty:
            problems.append(f"config con {len(dirty)} cambio(s) sin commitear")
    else:
        problems.append("~/.config/opencode sin git — sin red de seguridad")
        level = FAIL

    if SKILLS_DIR.exists():
        problems.append(f"{SKILLS_DIR} existe y no se usa — archivar")

    if problems:
        add(level, "higiene", "; ".join(problems))
    else:
        add(OK, "higiene", "config versionada y limpia")


def main() -> int:
    quiet = "--quiet" in sys.argv
    for fn in (
        check_litellm,
        check_lmstudio,
        check_alias_parity,
        check_mcp,
        check_harness,
        check_ram,
        check_watchdog_install,
        check_watchdog_loaded,
        check_agy_bridge,
        check_higiene,
    ):
        fn()

    icon = {OK: "  ok  ", WARN: " aviso", FAIL: " FALLO"}
    width = max(len(n) for _, n, _ in results)
    for level, name, msg in results:
        if quiet and level == OK:
            continue
        print(f"[{icon[level]}] {name.ljust(width)}  {msg}")

    fails = sum(1 for l, _, _ in results if l == FAIL)
    warns = sum(1 for l, _, _ in results if l == WARN)
    if not quiet or fails or warns:
        print(f"\n{len(results)} comprobaciones · {fails} fallo(s) · {warns} aviso(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
