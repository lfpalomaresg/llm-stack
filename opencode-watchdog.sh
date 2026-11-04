#!/bin/bash
# opencode-watchdog — punto de entrada del vigilante anti-bucles de opencode.
#
# Lo ejecuta el LaunchAgent com.luisfran.opencode-watchdog cada 60 s. La lógica
# (stream error, compactaciones, tope de pasos y bloqueo por inactividad) vive en
# opencode-watchdog.py para poder testearla; este lanzador fija los umbrales del
# stack y propaga argumentos (p. ej. --dry-run).
#
# Umbrales (sobrescribibles por entorno):
#   OPENCODE_WATCHDOG_MAX_STEPS   40   pasos máximos en un subagente
#   OPENCODE_WATCHDOG_STALL_MIN   60   minutos sin actividad en un subagente activo
#
# Desactivar sin desinstalar:  touch ~/.local/state/opencode-watchdog/disabled
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 2026-11-04 (OK operador): sin ningún proceso opencode no hay nada que vigilar ⇒ salir
# sin arrancar Python. Solo en la pasada automática (sin argumentos): --dry-run y los
# tests siguen corriendo siempre. Las líneas de log pendientes se leen en la siguiente
# pasada con opencode vivo (el offset no avanza mientras tanto).
if [ "$#" -eq 0 ] && ! /usr/bin/pgrep -x opencode >/dev/null 2>&1; then
    exit 0
fi
PY="/usr/bin/python3"
if [ ! -x "$PY" ]; then
    PY="$(command -v python3 || true)"
fi
if [ -z "${PY:-}" ]; then
    echo "agy-watchdog: no se encontró python3" >&2
    exit 1
fi

export OPENCODE_WATCHDOG_MAX_STEPS="${OPENCODE_WATCHDOG_MAX_STEPS:-40}"
export OPENCODE_WATCHDOG_STALL_MIN="${OPENCODE_WATCHDOG_STALL_MIN:-60}"

exec "$PY" "$ROOT/opencode-watchdog.py" "$@"
