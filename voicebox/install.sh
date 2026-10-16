#!/bin/bash
# Instalación reproducible del backend de Voicebox (sin app Tauri), Apple Silicon.
# Réplica de `just setup-python` del repo, en commit fijo. Ver README.md de esta carpeta.
set -euo pipefail
cd "$(dirname "$0")"
SHA=8af7efe62fab8d33e2a5dfbedabaa45f68a5184f
[ "$(git -C src rev-parse HEAD)" = "$SHA" ] || { echo "src no está en $SHA"; exit 1; }
export UV_PYTHON_PREFERENCE=only-managed
uv venv -q --python 3.12 venv
PIP="uv pip install -q --python venv/bin/python"
$PIP -r src/backend/requirements.txt
$PIP --no-deps chatterbox-tts hume-tada omnivoice
$PIP -r src/backend/requirements-mlx.txt
$PIP --no-deps mlx-lm==0.31.1 mlx-audio==0.4.1
$PIP git+https://github.com/QwenLM/Qwen3-TTS.git
venv/bin/python -c "import torch, mlx.core, fastapi, kokoro; print('ok torch', torch.__version__, 'mlx', mlx.core.__version__)"
