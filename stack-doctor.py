#!/usr/bin/env python3
"""stack-doctor — chequeo de salud del stack antes de una sesión larga.

Detecta las cuatro regresiones que ya han costado tiempo o panics:
  1. drift de alias entre LiteLLM y opencode
  2. MCP de más (procesos y esquemas que se pagan en cada turno)
  3. harness inflado (tokens fijos por turno)
  4. RAM sin sitio para el siguiente modelo, y watchdog muerto

No arranca ni para nada: solo mide e informa.

Uso:
  ~/llm-stack/.venv/bin/python3 ~/llm-stack/stack-doctor.py
  ... --quiet      solo problemas (para colgar del «arranca»)

Salida: OK / AVISO / FALLO por comprobación. Exit 1 si hay algún FALLO.
"""
from __future__ import annotations

import json
import shutil
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
LITELLM = "http://localhost:4000"
LMSTUDIO = "http://localhost:1234"

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


def check_services() -> None:
    if http_ok(f"{LITELLM}/health/liveliness"):
        add(OK, "LiteLLM", "responde en :4000")
    else:
        add(FAIL, "LiteLLM", "no responde en :4000 — opencode no tendrá modelos")

    if http_ok(f"{LMSTUDIO}/api/v0/models"):
        add(OK, "LM Studio", "responde en :1234")
    else:
        add(WARN, "LM Studio", "no responde en :1234 — los alias locales fallarán")


def check_alias_parity() -> None:
    if not GEN_MODELS.exists():
        add(WARN, "alias", "falta gen-opencode-models.py — sin validador")
        return
    proc = subprocess.run(
        [sys.executable, str(GEN_MODELS), "--check"],
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
    contradictory = [k for k in enabled if k.split("-")[0] in denied or k in denied]

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
    if size > 12288:
        add(FAIL, "harness", f"AGENTS.md {size} B — inflado, riesgo de livelock de compactación")
    elif size > 8192:
        add(WARN, "harness", f"AGENTS.md {size} B — por encima del objetivo (~5 KB)")
    else:
        add(OK, "harness", f"AGENTS.md {size} B (~{size // 4} tokens/turno)")

    ref = OPENCODE_DIR / "ref"
    if ref.is_dir():
        n = len(list(ref.glob("*.md")))
        add(OK, "harness", f"{n} referencias bajo demanda en ref/ (no se inyectan)")


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


def check_watchdog() -> None:
    try:
        out = subprocess.run(["launchctl", "list"], capture_output=True, text=True).stdout
    except Exception:
        add(WARN, "watchdog", "launchctl no disponible")
        return
    if WATCHDOG in out:
        add(OK, "watchdog", "LaunchAgent cargado")
    else:
        add(WARN, "watchdog", f"{WATCHDOG} no está cargado — sin freno anti-bucle")


def check_hygiene() -> None:
    baks = list(OPENCODE_DIR.glob("*.bak.*")) + list((OPENCODE_DIR / "agent").glob("*.bak.*"))
    if baks:
        add(WARN, "higiene", f"{len(baks)} .bak en la config — el git ya los hace innecesarios")
    else:
        add(OK, "higiene", "sin .bak en la config")

    if (OPENCODE_DIR / ".git").is_dir():
        proc = subprocess.run(
            ["git", "-C", str(OPENCODE_DIR), "status", "--porcelain"],
            capture_output=True,
            text=True,
        )
        dirty = [l for l in proc.stdout.splitlines() if l.strip()]
        if dirty:
            add(WARN, "higiene", f"config con {len(dirty)} cambio(s) sin commitear")
        else:
            add(OK, "higiene", "config versionada y limpia")
    else:
        add(FAIL, "higiene", "~/.config/opencode sin git — sin red de seguridad")

    if SKILLS_DIR.exists():
        add(WARN, "higiene", f"{SKILLS_DIR} existe y no se usa — archivar")


def main() -> int:
    quiet = "--quiet" in sys.argv
    for fn in (
        check_services,
        check_alias_parity,
        check_mcp,
        check_harness,
        check_ram,
        check_watchdog,
        check_hygiene,
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
