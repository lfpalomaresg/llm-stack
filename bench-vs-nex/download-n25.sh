#!/bin/zsh
# Descarga reanudable de Nex-N2.5-mini OptiQ-4bit al directorio de modelos de LM Studio.
export PATH="$HOME/.lmstudio/bin:/opt/homebrew/bin:$PATH"
DEST=~/.lmstudio/models/mlx-community/Nex-N2.5-mini-OptiQ-4bit
for i in $(seq 1 12); do
  if python3 -c "import huggingface_hub" 2>/dev/null; then
    python3 - <<'PY' && exit 0
import os
from huggingface_hub import snapshot_download
d=snapshot_download("mlx-community/Nex-N2.5-mini-OptiQ-4bit", local_dir=os.path.expanduser("~/.lmstudio/models/mlx-community/Nex-N2.5-mini-OptiQ-4bit"), max_workers=4)
print("OK", d)
PY
  else
    lms get "https://huggingface.co/mlx-community/Nex-N2.5-mini-OptiQ-4bit" --mlx -y && exit 0
  fi
  echo "intento $i falló, reintento en 60 s"; sleep 60
done
echo "DESCARGA FALLIDA tras 12 intentos"; exit 1
