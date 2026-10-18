#!/bin/zsh
export PATH="$HOME/.lmstudio/bin:$PATH"; cd ~/llm-stack/bench-mimo
W='{"temperature":0.6,"top_p":0.95}'
run() { # id etiqueta fichero ctx extra maxtok descargar
  lms load "$1" -c "$4" --ttl 900 -y >/dev/null 2>&1 || { echo "NO CARGA $1"; return; }
  BENCH_EXTRA_JSON="$5" BENCH_MAXTOK="$6" python3 ~/llm-stack/bench-coder.py "$1" "$2" "$3"
  [ "$7" = "si" ] && lms unload "$1" >/dev/null 2>&1; sleep 2
}
run deepseek/deepseek-r1-0528-qwen3-8b        "WORKER · R1-8B (actual)"     r1.md            24576 "$W" 8000 si
run mimo-v2.6-distill-qwen-9b-optiq           "WORKER · MiMo-9B pensando"   mimo-think.md    24576 "$W" 8000 si
run qwen3.5-9b-mlx                            "EXPLORADOR · Qwen3.5-9B (actual)" qwen-nothink.md 32768 '{}' 3000 no
run mimo-v2.6-distill-qwen-9b-optiq-nothink   "EXPLORADOR · MiMo-9B sin pensar" mimo-nothink.md 32768 '{}' 3000 si
echo FIN
