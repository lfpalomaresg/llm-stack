#!/bin/bash
# lock.sh — lock de exclusión mutua compartido para los modelos en RAM.
# Lo usan stack.sh y enrutar.sh (sourced). Sin dependencias externas: macOS no
# trae flock ni shlock aquí.
#
# Nace del RE-CAREO del 2026-08-05: la primera versión recuperaba locks huérfanos
# con `rm -rf` a secas, y dos procesos podían borrar el lock recién creado por un
# tercero — rompiendo la exclusión mutua justo en el arreglo que la garantizaba.
#
# Diseño: el directorio es la primitiva atómica (mkdir). La propiedad se confirma
# RELEYENDO el token tras escribirlo (si otro nos pisó, no somos dueños). La
# recuperación de huérfanos exige que el PID muerto siga siendo el mismo tras una
# pausa, y se hace por `mv` a un nombre temporal propio antes de borrar, de modo
# que dos recuperadores simultáneos no borren trabajo ajeno: solo uno gana el mv.
#
# API:  llm_lock_adquirir <lockdir> <segundos_max>   → 0 si lo tienes, 1 si no
#       llm_lock_soltar   <lockdir>                  → libera solo si eres dueño
#       llm_lock_soy_dueno <lockdir>                 → 0 si el lock es tuyo

llm_lock_token() { echo "$$-$(date +%s)"; }

llm_lock_soy_dueno() {
  local d="$1"
  [ -f "$d/token" ] && [ "$(cat "$d/token" 2>/dev/null)" = "${LLM_LOCK_TOKEN:-}" ]
}

llm_lock_adquirir() {
  local d="$1" max="${2:-60}" t=0 pid_visto token
  token="$(llm_lock_token)"
  while [ "$t" -lt "$max" ]; do
    if mkdir "$d" 2>/dev/null; then
      printf '%s\n' "$token" > "$d/token"
      printf '%s\n' "$$"     > "$d/pid"
      # Confirmar propiedad releyendo: si otro proceso pisó el token, no somos dueños.
      if [ "$(cat "$d/token" 2>/dev/null)" = "$token" ]; then
        export LLM_LOCK_TOKEN="$token"
        return 0
      fi
    else
      # ¿huérfano? Exigir que el MISMO pid muerto siga ahí tras una pausa, y
      # apropiarse por `mv` (atómico): si dos lo intentan, solo uno consigue el mv.
      pid_visto="$(cat "$d/pid" 2>/dev/null)"
      if [ -n "$pid_visto" ] && ! kill -0 "$pid_visto" 2>/dev/null; then
        sleep 1; t=$((t+1))
        if [ "$(cat "$d/pid" 2>/dev/null)" = "$pid_visto" ] && ! kill -0 "$pid_visto" 2>/dev/null; then
          mv "$d" "$d.huerfano.$$" 2>/dev/null && rm -rf "$d.huerfano.$$"
        fi
        continue
      fi
    fi
    sleep 1; t=$((t+1))
  done
  return 1
}

llm_lock_soltar() {
  local d="$1"
  llm_lock_soy_dueno "$d" && rm -rf "$d"
  return 0
}
