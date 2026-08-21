#!/bin/sh
# test-estres-agente.sh — Test de estrés del perfil AGENTE (2026-08-21)
# Mide RAM y latencia con orquestador (35B@32k) + worker (R1-8B@16k) cargados
# a la vez, con prompts de contexto creciente y peticiones concurrentes.
# Salida: tabla por escalón + veredicto. NO carga/descarga modelos: eso se
# hace fuera (el test mide, no gestiona).
#
# Uso: ./test-estres-agente.sh [informe.txt]

OUT="${1:-$HOME/llm-stack/test-estres-$(date +%Y%m%d-%H%M).log}"
API="http://localhost:4000/v1/chat/completions"

_ram() {  # % libre y presión
  memory_pressure -Q 2>/dev/null | awk '/free percentage/{print $NF}'
}

_gen_prompt() {  # $1 = nº aprox de tokens (≈4 chars/token)
  python3 -c "
import sys
n = int(sys.argv[1])
base = 'El sistema hotelero registra ocupacion, tarifas y consumos por centro. '
texto = (base * (n * 4 // len(base) + 1))[:n*4]
print(texto + ' PREGUNTA: resume lo anterior en una frase.')" "$1"
}

_call() {  # $1 = modelo, $2 = tokens de prompt → imprime "latencia_s tok_s status"
  P=$(_gen_prompt "$2")
  T0=$(date +%s)
  R=$(printf '%s' "$P" | python3 -c "
import json,sys,urllib.request
prompt = sys.stdin.read()
req = urllib.request.Request('$API',
  data=json.dumps({'model':'$1','messages':[{'role':'user','content':prompt}],
                   'max_tokens':120}).encode(),
  headers={'Content-Type':'application/json','Authorization':'Bearer llm-stack-local'})
try:
    r = json.load(urllib.request.urlopen(req, timeout=300))
    u = r.get('usage',{})
    print('OK', u.get('prompt_tokens','?'), u.get('completion_tokens','?'))
except Exception as e:
    print('FAIL', type(e).__name__, 0)" 2>&1)
  T1=$(date +%s)
  echo "$((T1-T0)) $R"
}

echo "═══ TEST DE ESTRÉS PERFIL AGENTE — $(date '+%F %T') ═══" | tee "$OUT"
echo "Modelos cargados:" | tee -a "$OUT"
lms ps | tee -a "$OUT"
echo "" | tee -a "$OUT"
echo "RAM libre inicial: $(_ram)%" | tee -a "$OUT"
echo "" | tee -a "$OUT"

# ── Escalera de contexto sobre el orquestador ──
for TOK in 2000 8000 16000 24000 30000; do
  R1=$(_ram)
  RES=$(_call local-general "$TOK")
  R2=$(_ram)
  echo "35B ctx≈${TOK}tok → ${RES} | RAM libre: ${R1}%→${R2}%" | tee -a "$OUT"
done

echo "" | tee -a "$OUT"
echo "── Concurrencia: orquestador (16k) + worker (8k) A LA VEZ ──" | tee -a "$OUT"
R1=$(_ram)
_call local-general 16000 > /tmp/_t35 &
PID1=$!
_call local-worker 8000 > /tmp/_t8 &
PID2=$!
wait $PID1 $PID2
R2=$(_ram)
echo "35B concurrente : $(cat /tmp/_t35)" | tee -a "$OUT"
echo "R1-8B concurrente: $(cat /tmp/_t8)" | tee -a "$OUT"
echo "RAM libre: ${R1}%→${R2}%" | tee -a "$OUT"
echo "" | tee -a "$OUT"
echo "RAM libre final: $(_ram)%" | tee -a "$OUT"
echo "Informe: $OUT"
