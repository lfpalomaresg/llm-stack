#!/bin/sh
# guard-hermes-crons.sh — avisa si algún cron de hermes está ACTIVO contra la orden
# de pausa (baseline = 0 activos, decisión operador 2026-09-08). Los crons de radar
# Soho pueden reactivarse solos y disparar el 35B a tus espaldas; este guard lo caza.
# Lo dispara un LaunchAgent a diario (~09:30, tras la ventana de las 09:00) + al arrancar.
# Ver [[feedback-hermes-actua-solo-pese-a-pausa]].
set -u
HERMES_PY="$HOME/.hermes/hermes-agent/venv/bin/python"
LOG="$HOME/.hermes/cron-guard.log"
ts=$(date "+%Y-%m-%d %H:%M:%S")

if [ ! -x "$HERMES_PY" ]; then
  echo "$ts SKIP — venv de hermes no encontrado ($HERMES_PY)" >> "$LOG"
  exit 0
fi

# Contamos jobs [active]; si `cron list` falla, no cantamos falso verde (salida vacía != 0).
listado=$("$HERMES_PY" -m hermes_cli.main cron list 2>/dev/null)
if [ -z "$listado" ]; then
  echo "$ts WARN — 'cron list' no devolvió nada (¿gateway/venv?); no se pudo comprobar" >> "$LOG"
  exit 0
fi
activos=$(printf '%s\n' "$listado" | grep -c "\[active\]")

if [ "${activos:-0}" -gt 0 ]; then
  nombres=$(printf '%s\n' "$listado" | grep -A1 "\[active\]" | grep "Name:" | sed 's/.*Name: *//' | paste -sd '; ' -)
  msg="$activos cron(s) hermes ACTIVOS contra la pausa: $nombres"
  echo "$ts ⚠️  $msg" >> "$LOG"
  osascript -e "display notification \"$msg\" with title \"⚠️ Guard crons hermes\" subtitle \"Revisa: hermes cron list\" sound name \"Basso\"" 2>/dev/null
else
  echo "$ts OK — 0 crons activos" >> "$LOG"
fi
