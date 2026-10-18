#!/bin/zsh
export PATH="$HOME/.lmstudio/bin:$PATH"; cd ~/llm-stack/bench-mimo
for spec in "deepseek/deepseek-r1-0528-qwen3-8b|R1-8B (worker hasta hoy)|raz-r1.md" \
            "mimo-v2.6-distill-qwen-9b-optiq|MiMo-9B adaptativo|raz-mimo.md" \
            "mimo-v2.6-distill-qwen-9b-optiq-think|MiMo-9B razonamiento forzado|raz-mimo-think.md"; do
  id=${spec%%|*}; rest=${spec#*|}; lab=${rest%%|*}; out=${rest#*|}
  lms unload "$id" >/dev/null 2>&1; lms load "$id" -c 24576 --ttl 900 -y >/dev/null 2>&1 || { echo "NO CARGA $id"; continue; }
  python3 ~/llm-stack/bench-razonar.py "$id" "$lab" "$out"; lms unload "$id" >/dev/null 2>&1; sleep 2
done; echo FIN
