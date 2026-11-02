#!/bin/zsh
# Lanzador del backend de Voicebox. Lo invoca `stack.sh voz` (no lanzar a mano en paralelo).
# Datos (BD, perfiles de voz, audio generado) en ./data; modelos en la caché de HuggingFace.
BASE="${0:A:h}"
cd "$BASE/src" || exit 1
# Voz de Mía ajustada (fine-tune LoRA 02/11) como voz «mia» del motor qwen_custom_voice
# (parches/qwen_cv_local.patch). El perfil clonado «Mía Serena» (motor qwen) no depende de esto.
MIA_CV="$BASE/data/modelos/mia-qwen3tts-cv-e1"
[ -d "$MIA_CV" ] && export VOICEBOX_QWEN_CV_1_7B="${VOICEBOX_QWEN_CV_1_7B:-$MIA_CV}"
exec "$BASE/venv/bin/python" -m backend.main --data-dir "$BASE/data" "$@"
