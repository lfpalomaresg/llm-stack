#!/bin/zsh
# Test del perfil AGENTE — opción b (2026-09-15, OK operador).
# Residente SOLO el explorador (FAST = Qwen3.5-9B no-think, sin TTL). @worker (R1-8B) y
# @nexn2 (Nex) entran JIT vía LiteLLM y NO son intrusos. Intruso = LLM fuera del stack
# (p.ej. el qwen3.8-27b del bot, 15/09): con FORCE=1 se desaloja; sin FORCE, exit 5 nombrándolo.
# Uso: zsh ~/llm-stack/test-perfil-intrusos.sh   (lms FALSO en PATH, no toca la RAM real)
set -u
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"
cat > "$TMP/bin/lms" <<'EOF'
#!/usr/bin/env python3
import json, os, sys
st, log = os.environ["FAKE_LMS_STATE"], os.environ["FAKE_LMS_LOG"]
models = json.load(open(st)) if os.path.exists(st) else []
a = sys.argv[1:]
open(log, "a").write(" ".join(a) + "\n")
GB = 1024**3
SIZES = {"nex-n2-mini-local": 20.42*GB, "deepseek/deepseek-r1-0528-qwen3-8b": 4.62*GB}
def save(): json.dump(models, open(st, "w"))
if a[:2] == ["ps", "--json"]:
    print(json.dumps(models))
elif a[:1] == ["unload"]:
    models = [m for m in models if m["identifier"] != a[1]]; save()
elif a[:1] == ["load"]:
    name = a[1]
    ctx = int(a[a.index("--context-length") + 1])
    ttl = int(a[a.index("--ttl") + 1]) * 1000 if "--ttl" in a else None   # sin --ttl = sin caducidad
    size = SIZES.get(name, 6*GB)
    if sum(m["sizeBytes"] for m in models) + size > 34*GB:   # guardarraíl simulado
        print("Error: insufficient system resources", file=sys.stderr); sys.exit(1)
    models.append({"type": "llm", "identifier": name, "modelKey": name,
                   "sizeBytes": size, "contextLength": ctx, "ttlMs": ttl}); save()
EOF
chmod +x "$TMP/bin/lms"

# Modelos del stack leídos del propio stack.sh (FAST puede depender de WORKER)
eval "$(grep -E '^(WORKER|GENERAL|FAST)=' ~/llm-stack/stack.sh)"

fallos=0
_m() {  # $1 id · $2 GB · $3 ctx · $4 ttlMs (o null)
  print -r -- "{\"type\":\"llm\",\"identifier\":\"$1\",\"modelKey\":\"$1\",\"sizeBytes\":$(( $2 * 1073741824 )),\"contextLength\":$3,\"ttlMs\":$4}"
}
BOT=$(_m qwen/qwen3.8-27b 16 24576 3600000)
EMB='{"type":"embedding","identifier":"text-embedding-nomic","modelKey":"text-embedding-nomic","sizeBytes":100000000,"contextLength":2048,"ttlMs":3600000}'
WRK=$(_m "$WORKER" 5 24576 1800000)
NEX=$(_m "$GENERAL" 20 32768 1800000)

_estado() { print -r -- "$1" > "$TMP/state.json"; : > "$TMP/lms.log"; }
_ids() { python3 -c 'import json,sys; print(" ".join(sorted(m["identifier"] for m in json.load(open(sys.argv[1])))))' "$TMP/state.json"; }
_esperado() { python3 -c 'import sys; print(" ".join(sorted(sys.argv[1:])))' "$@"; }
_run() {  # $@ = asignaciones de entorno extra (p.ej. FORCE=1)
  env PATH="$TMP/bin:$PATH" FAKE_LMS_STATE="$TMP/state.json" FAKE_LMS_LOG="$TMP/lms.log" \
      LLM_STACK_LOCKDIR="$TMP/lock" "$@" zsh ~/llm-stack/stack.sh agente > "$TMP/out" 2>&1
  print $?
}
_check() {  # $1 descripción · $2 obtenido · $3 esperado
  if [[ "$2" == "$3" ]]; then print "  ✅ $1"
  else print "  ❌ $1 — esperado [$3], obtenido [$2]"; fallos=$((fallos + 1)); fi
}

print "0) Opción b: el explorador (FAST) es un modelo propio, no el R1-8B del worker"
_check "FAST != WORKER" "$([[ "$FAST" != "$WORKER" ]] && print distinto || print igual)" "distinto"

print "1) FORCE=1 con el 27B del bot + un embedding cargados"
_estado "[$BOT,$EMB]"; rc=$(_run FORCE=1)
_check "exit 0" "$rc" "0"
_check "27B desalojado, solo explorador residente, embedding intacto" "$(_ids)" "$(_esperado "$FAST" text-embedding-nomic)"

print "2) Sin FORCE con el 27B del bot cargado"
_estado "[$BOT]"; rc=$(_run)
_check "exit 5 (se niega)" "$rc" "5"
_check "no toca nada" "$(_ids)" "qwen/qwen3.8-27b"
_check "el aviso nombra al intruso" "$(grep -c 'qwen/qwen3.8-27b' "$TMP/out")" "1"

print "3) RAM vacía, sin FORCE: carga SOLO el explorador (ni Nex ni worker)"
_estado "[]"; rc=$(_run)
_check "exit 0" "$rc" "0"
_check "solo explorador" "$(_ids)" "$FAST"
_check "explorador sin caducidad (residente)" "$(python3 -c 'import json,sys; print([m["ttlMs"] for m in json.load(open(sys.argv[1]))])' "$TMP/state.json")" "[None]"

print "4) @worker y @nexn2 cargados JIT, sin FORCE: NO son intrusos, no se tocan"
_estado "[$WRK,$NEX]"; rc=$(_run)
_check "exit 0" "$rc" "0"
_check "worker y Nex intactos + explorador" "$(_ids)" "$(_esperado "$FAST" "$WORKER" "$GENERAL")"

print "5) Idempotente: con el explorador ya residente no recarga"
_estado "[]"; _run > /dev/null; : > "$TMP/lms.log"; rc=$(_run)
_check "exit 0" "$rc" "0"
_check "0 cargas en la 2ª pasada" "$(grep -c '^load ' "$TMP/lms.log")" "0"

print "6) Perfil GENERAL con el explorador residente: libera su RAM antes de cargar Nex"
# 2026-09-16, medido: con el explorador (5,6 GB) residente, LM Studio RECHAZA Nex (20,4 GB)
# por guardarraíl ("insufficient system resources"). El relevo automático solo ocurre entre
# modelos JIT; el explorador lo carga stack.sh, así que hay que desalojarlo a propósito.
_estado "[]"; _run FORCE=1 > /dev/null          # deja el explorador residente
_run_general() {
  env PATH="$TMP/bin:$PATH" FAKE_LMS_STATE="$TMP/state.json" FAKE_LMS_LOG="$TMP/lms.log" \
      LLM_STACK_LOCKDIR="$TMP/lock" "$@" zsh ~/llm-stack/stack.sh general > "$TMP/out" 2>&1
  print $?
}
: > "$TMP/lms.log"; rc=$(_run_general)
_check "exit 0" "$rc" "0"
_check "Nex cargado y explorador fuera" "$(_ids)" "$GENERAL"
_check "se descargó el explorador explícitamente" "$(grep -c "^unload $FAST" "$TMP/lms.log")" "1"

print "7) Volver a AGENTE con Nex OCIOSO: lo descarga (si no, quedan 26 GB ocupados)"
NEX_IDLE='{"type":"llm","identifier":"'$GENERAL'","modelKey":"'$GENERAL'","sizeBytes":21930000000,"contextLength":32768,"ttlMs":1800000,"status":"idle"}'
NEX_BUSY='{"type":"llm","identifier":"'$GENERAL'","modelKey":"'$GENERAL'","sizeBytes":21930000000,"contextLength":32768,"ttlMs":1800000,"status":"processing"}'
_estado "[$NEX_IDLE]"; rc=$(_run)
_check "exit 0" "$rc" "0"
_check "Nex fuera, explorador dentro" "$(_ids)" "$FAST"

print "8) Volver a AGENTE con Nex OCUPADO: no se toca (puede estar sirviendo a @nexn2)"
_estado "[$NEX_BUSY]"; rc=$(_run)
_check "exit 0" "$rc" "0"
_check "Nex intacto + explorador" "$(_ids)" "$(_esperado "$FAST" "$GENERAL")"

(( fallos == 0 )) && print "\nVERDE: 0 fallos" || print "\nROJO: $fallos fallo(s)"
exit $fallos
