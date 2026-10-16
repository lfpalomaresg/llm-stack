#!/bin/zsh
# Test del perfil VOZ (Voicebox, 2026-10-17, OK operador: excepción ACOTADA a la Regla nº1).
# Voicebox carga sus propios modelos de voz (MLX) fuera de LM Studio. Solo se permite así:
#   · `stack.sh voz` se NIEGA (exit 6) si Nex (GENERAL) está cargado, y (exit 7) si no puede
#     leer `lms ps` — un fallo de lectura no es "no hay nada cargado".
#   · `voz` deja el explorador RESIDENTE: con él cargado, LM Studio rechaza el JIT de Nex por
#     guardarraíl (medido 16/09), que es la única vía a Nex que no pasa por stack.sh.
#   · `stack.sh general` se NIEGA (exit 6) si Voicebox está corriendo.
#   · Un PID solo cuenta como Voicebox/altavoz si su línea de comando lo es (PID reciclado).
#   · `voz-stop` descarga los modelos (POST /models/unload) y para SOLO sus procesos.
#   · Sin /health sano, `voz` no se da por activo: para el backend y sale con 1.
# Careo Codex 17/10, ronda 1: casos 1b, 2 (nube, explorador), 3b, 5 (unload), 8 y 9.
# Uso: zsh ~/llm-stack/test-perfil-voz.sh   (lms, backend y altavoz FALSOS; no toca la RAM)
set -u
TMP=$(mktemp -d) || { print "ROJO: mktemp falló, el test no puede montarse"; exit 99; }
[[ -n "$TMP" && -d "$TMP" ]] || { print "ROJO: sin directorio temporal"; exit 99; }
AJENO=""
trap 'for f in "$TMP"/*.pid(N); do kill "$(cat "$f")" 2>/dev/null; done; [ -n "$AJENO" ] && kill "$AJENO" 2>/dev/null; rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" || exit 99
cat > "$TMP/bin/lms" <<'EOF'
#!/usr/bin/env python3
import json, os, sys
st, log = os.environ["FAKE_LMS_STATE"], os.environ["FAKE_LMS_LOG"]
models = json.load(open(st)) if os.path.exists(st) else []
a = sys.argv[1:]
open(log, "a").write(" ".join(a) + "\n")
def save(): json.dump(models, open(st, "w"))
if a[:2] == ["ps", "--json"]:
    n = int(open(log).read().count("ps --json"))   # nº de lecturas, contando esta
    falla_desde = int(os.environ.get("FAKE_LMS_PS_FAIL_DESDE", "0"))
    if os.environ.get("FAKE_LMS_PS_FAIL") or (falla_desde and n >= falla_desde):
        print("daemon not running", file=sys.stderr); sys.exit(1)
    print(json.dumps(models))
elif a[:1] == ["unload"]:
    models = [m for m in models if m["identifier"] != a[1]]; save()
elif a[:1] == ["load"]:
    name = a[1]; ctx = int(a[a.index("--context-length") + 1])
    ttl = int(a[a.index("--ttl") + 1]) * 1000 if "--ttl" in a else None
    models.append({"type": "llm", "identifier": name, "modelKey": name,
                   "sizeBytes": 6 * 1024**3, "contextLength": ctx, "ttlMs": ttl}); save()
EOF
# Backend falso por HTTP: /health (200, o FAKE_HEALTH), POST /models/unload; apunta args y nube
cat > "$TMP/bin/voicebox-falso" <<'EOF'
#!/usr/bin/env python3
import os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
log = os.environ["FAKE_VOZ_LOG"]
open(log, "a").write("args " + " ".join(sys.argv[1:]) + "\n")
open(log, "a").write("nube=" + os.environ.get("VOICEBOX_CLOUD_ENABLED", "<sin definir>") + "\n")
port = int(sys.argv[sys.argv.index("--port") + 1])
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(int(os.environ.get("FAKE_HEALTH", "200")) if self.path == "/health" else 404); self.end_headers()
    def do_POST(self):
        open(log, "a").write("POST " + self.path + "\n"); self.send_response(200); self.end_headers()
HTTPServer(("127.0.0.1", port), H).serve_forever()
EOF
cat > "$TMP/bin/altavoz-falso" <<'EOF'
#!/bin/zsh
print -r -- "altavoz backend_pid=${VOICEBOX_PID:-}" >> "$FAKE_VOZ_LOG"
[[ -n "${FAKE_ALTAVOZ_MUDO:-}" ]] && exit 1   # muere sin llegar a conectarse
[[ -z "${FAKE_ALTAVOZ_CALLADO:-}" ]] && print "conectado a /events/speak"   # callado: vivo y sin confirmar
while true; do sleep 1; done
EOF
chmod +x "$TMP/bin/lms" "$TMP/bin/voicebox-falso" "$TMP/bin/altavoz-falso" || exit 99
PORT=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')
[[ -n "$PORT" ]] || { print "ROJO: sin puerto libre"; exit 99; }

eval "$(grep -E '^(WORKER|GENERAL|FAST)=' ~/llm-stack/stack.sh)"
[[ -n "${GENERAL:-}" && -n "${FAST:-}" ]] || { print "ROJO: no leí GENERAL/FAST de stack.sh"; exit 99; }
fallos=0
_m() { print -r -- "{\"type\":\"llm\",\"identifier\":\"$1\",\"modelKey\":\"$1\",\"sizeBytes\":$(( $2 * 1073741824 )),\"contextLength\":$3,\"ttlMs\":$4,\"status\":\"idle\"}"; }
EXP=$(_m "$FAST" 6 32768 null)
NEX=$(_m "$GENERAL" 20 32768 1800000)
_estado() { print -r -- "$1" > "$TMP/state.json"; : > "$TMP/lms.log"; : > "$TMP/voz.log"; }
_ids() { python3 -c 'import json,sys; print(" ".join(sorted(m["identifier"] for m in json.load(open(sys.argv[1])))))' "$TMP/state.json"; }
_esperado() { python3 -c 'import sys; print(" ".join(sorted(sys.argv[1:])))' "$@"; }
_run() {  # $1 = subcomando; resto = VAR=valor extra
  local sub="$1"; shift
  env PATH="$TMP/bin:$PATH" FAKE_LMS_STATE="$TMP/state.json" FAKE_LMS_LOG="$TMP/lms.log" \
      FAKE_VOZ_LOG="$TMP/voz.log" LLM_STACK_LOCKDIR="$TMP/lock" \
      VOICEBOX_CMD="$TMP/bin/voicebox-falso" VOICEBOX_PATRON="voicebox-falso" \
      VOICEBOX_PIDFILE="$TMP/voz.pid" VOICEBOX_LOGDIR="$TMP" \
      VOICEBOX_URL="http://127.0.0.1:$PORT" VOICEBOX_ESPERA=10 \
      VOICEBOX_ALTAVOZ_CMD="$TMP/bin/altavoz-falso" VOICEBOX_ALTAVOZ_PATRON="altavoz-falso" \
      VOICEBOX_ALTAVOZ_PIDFILE="$TMP/altavoz.pid" \
      "$@" zsh ~/llm-stack/stack.sh "$sub" > "$TMP/out" 2>&1
  print $?
}
_vivo() { [ -f "$TMP/$1.pid" ] && kill -0 "$(cat "$TMP/$1.pid")" 2>/dev/null && print si || print no; }
_check() {
  if [[ "$2" == "$3" ]]; then print "  ✅ $1"
  else print "  ❌ $1 — esperado [$3], obtenido [$2]"; fallos=$((fallos + 1)); fi
}

print "1) voz con Nex cargado: se niega y no arranca Voicebox"
_estado "[$EXP,$NEX]"; rc=$(_run voz)
_check "exit 6" "$rc" "6"
_check "Voicebox no arrancado" "$(_vivo voz)" "no"
_check "no toca LM Studio" "$(_ids)" "$(_esperado "$FAST" "$GENERAL")"
_check "el aviso nombra a Nex" "$(grep -c "$GENERAL" "$TMP/out")" "1"

print "1b) voz con 'lms ps' fallando: se niega (no lo lee como 'nada cargado')"
_estado "[$NEX]"; rc=$(_run voz FAKE_LMS_PS_FAIL=1)
_check "exit 7" "$rc" "7"
_check "Voicebox no arrancado" "$(_vivo voz)" "no"

print "2) voz con la RAM vacía: arranca en 127.0.0.1, sin nube, con altavoz y explorador residente"
_estado "[]"; rc=$(_run voz VOICEBOX_CLOUD_ENABLED=1)
_check "exit 0" "$rc" "0"
_check "Voicebox vivo" "$(_vivo voz)" "si"
_check "escucha solo en loopback" "$(grep -c -- '--host 127.0.0.1' "$TMP/voz.log")" "1"
_check "nube desactivada aunque el entorno la pidiera" "$(grep -c 'nube=<sin definir>' "$TMP/voz.log")" "1"
_check "altavoz vivo" "$(_vivo altavoz)" "si"
_check "el altavoz conoce el PID del backend" "$(grep -c "backend_pid=$(cat "$TMP/voz.pid" 2>/dev/null)\$" "$TMP/voz.log")" "1"
_check "explorador residente (bloquea el JIT de Nex)" "$(_ids)" "$FAST"

print "3) voz otra vez: idempotente (ni segundo backend ni segundo altavoz)"
pid1=$(cat "$TMP/voz.pid" 2>/dev/null); alt1=$(cat "$TMP/altavoz.pid" 2>/dev/null); : > "$TMP/voz.log"; rc=$(_run voz)
_check "había PIDs" "$([ -n "$pid1" ] && [ -n "$alt1" ] && print si || print no)" "si"
_check "exit 0" "$rc" "0"
_check "mismo backend" "$(cat "$TMP/voz.pid")" "$pid1"
_check "mismo altavoz" "$(cat "$TMP/altavoz.pid")" "$alt1"
_check "0 arranques nuevos" "$(grep -c . "$TMP/voz.log")" "0"

print "3b) voz con el backend vivo y el altavoz muerto: relanza solo el altavoz"
kill "$alt1" 2>/dev/null; for _ in {1..20}; do kill -0 "$alt1" 2>/dev/null || break; sleep 0.1; done
rc=$(_run voz)
_check "exit 0" "$rc" "0"
_check "altavoz vivo otra vez" "$(_vivo altavoz)" "si"
_check "altavoz nuevo" "$([ "$(cat "$TMP/altavoz.pid")" != "$alt1" ] && print nuevo || print viejo)" "nuevo"
_check "mismo backend" "$(cat "$TMP/voz.pid")" "$pid1"

print "4) general con Voicebox vivo: se niega y no carga Nex"
: > "$TMP/lms.log"; rc=$(_run general)
_check "exit 6" "$rc" "6"
_check "Nex no cargado" "$(grep -c "^load $GENERAL" "$TMP/lms.log")" "0"
_check "Voicebox sigue vivo" "$(_vivo voz)" "si"

print "5) voz-stop: descarga modelos y para backend y altavoz"
pid=$(cat "$TMP/voz.pid"); alt=$(cat "$TMP/altavoz.pid"); : > "$TMP/voz.log"; rc=$(_run voz-stop)
_check "exit 0" "$rc" "0"
_check "pidió /models/unload" "$(grep -c 'POST /models/unload' "$TMP/voz.log")" "1"
_check "backend muerto" "$(kill -0 "$pid" 2>/dev/null && print vivo || print muerto)" "muerto"
_check "altavoz muerto" "$(kill -0 "$alt" 2>/dev/null && print vivo || print muerto)" "muerto"
_check "pidfiles borrados" "$(print -l -- "$TMP"/*.pid(N) | grep -c .)" "0"
_check "explorador intacto" "$(_ids)" "$FAST"

print "6) Tras voz-stop, general ya puede cargar Nex"
rc=$(_run general)
_check "exit 0" "$rc" "0"
_check "Nex cargado" "$(_ids)" "$GENERAL"

print "7) Un pidfile con un PID muerto no cuenta como Voicebox vivo"
_estado "[$EXP]"; print 999999 > "$TMP/voz.pid"; rc=$(_run general)
_check "general exit 0" "$rc" "0"
rm -f "$TMP/voz.pid"

print "8) PID reciclado: el pidfile apunta a un proceso AJENO vivo"
sleep 300 & AJENO=$!
_estado "[$EXP]"; print "$AJENO" > "$TMP/voz.pid"; print "$AJENO" > "$TMP/altavoz.pid"
rc=$(_run general)
_check "general no lo toma por Voicebox (exit 0)" "$rc" "0"
_estado "[]"; print "$AJENO" > "$TMP/voz.pid"; print "$AJENO" > "$TMP/altavoz.pid"; rc=$(_run voz-stop)
_check "voz-stop no mata al ajeno" "$(kill -0 "$AJENO" 2>/dev/null && print vivo || print muerto)" "vivo"
kill "$AJENO" 2>/dev/null; AJENO=""

print "9) /health responde 500: voz no se da por activo"
_estado "[]"; rc=$(_run voz FAKE_HEALTH=500 VOICEBOX_ESPERA=3)
_check "exit 1" "$rc" "1"
_check "backend no queda vivo" "$(pgrep -f "voicebox-falso.*--port $PORT" >/dev/null && print vivo || print muerto)" "muerto"
_check "sin altavoz" "$(_vivo altavoz)" "no"
_check "sin pidfile" "$([ -f "$TMP/voz.pid" ] && print existe || print no)" "no"

print "10) 'lms ps' sana la 1ª vez y falla después (TOCTOU): Nex cargado no se cuela"
_estado "[$NEX]"; rc=$(_run voz FAKE_LMS_PS_FAIL_DESDE=2)
_check "exit 6: decidió con la 1ª lectura (que sí veía a Nex)" "$rc" "6"
_check "una sola lectura de 'lms ps' antes de decidir" "$(grep -c '^ps --json' "$TMP/lms.log")" "1"
_check "Voicebox no arrancado" "$(_vivo voz)" "no"

print "10b) 'lms ps' devuelve JSON válido pero malformado ([null]): falla cerrado"
_estado "[null]"; rc=$(_run voz)
_check "exit 7" "$rc" "7"
_check "Voicebox no arrancado" "$(_vivo voz)" "no"

print "11b) El altavoz vive pero nunca confirma la conexión: no se anuncia 'activo'"
_estado "[]"; rc=$(_run voz FAKE_ALTAVOZ_CALLADO=1)
_check "exit 8 (voz sin altavoz)" "$rc" "8"
_check "el altavoz callado se para" "$(_vivo altavoz)" "no"
_run voz-stop > /dev/null

print "11) El altavoz no llega a conectarse: no se anuncia 'activo'"
_estado "[]"; rc=$(_run voz FAKE_ALTAVOZ_MUDO=1)
_check "exit 8 (voz sin altavoz)" "$rc" "8"
_check "lo dice" "$(grep -c 'SIN altavoz' "$TMP/out")" "1"
_check "no dice 'Perfil VOZ activo'" "$(grep -c 'Perfil VOZ activo' "$TMP/out")" "0"
_run voz-stop > /dev/null

(( fallos == 0 )) && print "\nVERDE: 0 fallos" || print "\nROJO: $fallos fallo(s)"
exit $fallos
