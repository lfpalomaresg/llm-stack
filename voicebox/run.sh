#!/bin/zsh
# Lanzador del backend de Voicebox. Lo invoca `stack.sh voz` (no lanzar a mano en paralelo).
# Datos (BD, perfiles de voz, audio generado) en ./data; modelos en la caché de HuggingFace.
cd "${0:A:h}/src" || exit 1
exec "${0:A:h}/venv/bin/python" -m backend.main --data-dir "${0:A:h}/data" "$@"
