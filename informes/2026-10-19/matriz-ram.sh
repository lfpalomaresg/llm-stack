#!/bin/zsh
# Matriz de cargas medida (2026-10-19). Carga cada combinación real del stack, registra si el guardarraíl
# de LM Studio la admite y la memoria libre. Al final restaura el perfil AGENTE.
export PATH="$HOME/.lmstudio/bin:$PATH"
EXP=qwen3.5-9b-mlx; WRK=mimo-v2.6-distill-qwen-9b-optiq; NEX=nex-n2-mini-local
GOSS=openai/gpt-oss-20b; PHI=phi-4-reasoning-plus-mlx; GEM=gemma-4-e4b-it-optiq; JOS=josiefied-qwen3-30b-a3b-abliterated-v2
libre() { memory_pressure 2>/dev/null | grep -oE '[0-9]+%' | tail -1; }
swap() { sysctl -n vm.swapusage | grep -oE 'used = [0-9.]+M' | grep -oE '[0-9.]+'; }
combo() { # nombre, luego pares modelo:ctx
  local name=$1; shift; lms unload --all >/dev/null 2>&1; sleep 4; local ok=1 det=""
  for mc in "$@"; do m=${mc%:*}; c=${mc##*:}
    if lms load "$m" -c "$c" --ttl 600 -y >/dev/null 2>&1; then det="$det ✓${m##*/}"; else det="$det ✗${m##*/}"; ok=0; fi; sleep 2; done
  local gb=$(lms ps --json | python3 -c "import sys,json;print(round(sum(m['sizeBytes'] for m in json.load(sys.stdin))/1e9,1))")
  print -r -- "$name|$([ $ok = 1 ] && echo CABE || echo NO_CABE)|${gb} GB pesos|libre $(libre)|swap $(swap) MB|$det"
}
echo "inicio: libre $(libre) · swap $(swap) MB"
combo "AGENTE: explorador + worker"            $EXP:32768 $WRK:32768
combo "GENERAL: Nex solo"                      $NEX:32768
combo "Nex + worker (@nexn2 y @worker)"        $NEX:32768 $WRK:32768
combo "Nex + explorador"                       $NEX:32768 $EXP:32768
combo "Careo capa 1: explorador + gpt-oss + Phi" $EXP:32768 $GOSS:16384 $PHI:16384
combo "Auditor sensible: explorador + Gemma"   $EXP:32768 $GEM:8192
combo "Red team: explorador + Josie"           $EXP:32768 $JOS:16384
combo "Explorador + worker + gpt-oss"          $EXP:32768 $WRK:32768 $GOSS:16384
lms unload --all >/dev/null 2>&1; sleep 3; ~/llm-stack/stack.sh agente 2>&1 | tail -1
echo "fin: $(lms ps --json | python3 -c "import sys,json;print([(m['identifier'],m['contextLength']) for m in json.load(sys.stdin)])") · libre $(libre)"
