#!/bin/zsh
# LLM Stack v5.6 — control del stack local
# Uso: stack.sh start | stop | code | general | agente | ligero | voz | voz-stop | status | daemon
#      Variables: FORCE=1 → permite desalojar un grande en uso (uso consciente)
#
# Perfiles (nunca 2 grandes a la vez — regla anti-cuelgue):
#   agente  → SOLO explorador residente (FAST, 32k, sin TTL)  [default · opción b, 2026-09-15]
#             @worker (MiMo-9B) y @nexn2 (Nex) entran JIT vía LiteLLM al invocarlos.
#   general → Nex 32k (TTL 30 min) + explorador — lo pide enrutar.sh para local-general
#   ligero  → solo explorador (descarga Nex)
#   code    → retirado (redirige a agente)
# Techos de contexto CONSERVADORES tras el congelón del 2026-08-02 (KV cache
# se comió la RAM con 80k). Subir solo tras pasar el test de estrés del doc.
# 2026-08-21: coder bajado 48k→32k (era el perfil que petó; el KV es el culpable).
# Detalle del sistema agéntico: ~/llm-stack/sistema-agentico.md
#
# Endurecido tras el careo a tres del 2026-08-05 (Claude+Codex+Gemini):
#  · daemon YA NO fuerza perfil (antes, un reinicio de LiteLLM por KeepAlive
#    desalojaba el 35B que estuviera usando hermes) — CRÍTICO 2/3 revisores.
#  · lock global: detectar+cargar es atómico (carrera TOCTOU) — CRÍTICO 3/3.
#  · comprueba que `lms` existe: sin él, `_loaded` daba falsos negativos y se
#    cargaban modelos creyendo que la RAM estaba libre — CRÍTICO verificado.
#  · verifica que la carga funcionó antes de cantar éxito — IMPORTANTE.
#  · pkill acotado al proceso propio por PID — IMPORTANTE.

LITELLM=~/llm-stack/.venv/bin/litellm
CFG=~/llm-stack/litellm.config.yaml
LOG=~/llm-stack/litellm.log
PIDFILE=~/llm-stack/litellm.pid
LOCKDIR="${LLM_STACK_LOCKDIR:-/tmp/llm-stack.lock}"   # override solo para tests

# ORQUESTADOR local (único grande). 2026-09-08: Nex-N2-mini (35B-A3B nex-agi, afinado
# agentic) sustituyó al Qwen3.6-35B. 2026-09-10: 35B y Coder-30B RETIRADOS y borrados del
# disco (OK operador); local-coder es un alias a Nex. 2026-09-25: eliminada la variable CODER.
GENERAL="nex-n2-mini-local"
WORKER="mimo-v2.6-distill-qwen-9b-optiq"   # 2026-10-19 (OK operador): MiMo-V2.6-Distill-Qwen-9B sustituye al R1-8B (bench 6/6 vs 3/6)
# EXPLORADOR residente (@explorador · local-fast · bot de Telegram). 2026-09-15 (opción b, OK
# operador): Qwen3.5-9B MLX 4-bit con chat_template NO-THINK por defecto (QWEN35-9B-NOTHINK.md).
# Sustituye al R1-8B que hacía de "fast" desde el 08/09 (razona: mal encaje para un rol sin
# razonamiento). Revertir = FAST="$WORKER".
FAST="qwen3.5-9b-mlx"

# VOZ (2026-10-17, OK operador): Voicebox (backend FastAPI+MCP, ~/llm-stack/voicebox) carga
# sus propios modelos de voz con MLX — EXCEPCIÓN ACOTADA a la Regla nº1 ("solo LM Studio
# carga modelos"): solo vía `stack.sh voz`, nunca con Nex (GENERAL) en RAM y viceversa
# (incidente IOGPU 21/08: churn de memoria de GPU). Test: zsh ~/llm-stack/test-perfil-voz.sh
# Careo Codex 17/10 (ronda 1): identidad de PID, lectura de `lms ps` obligatoria, explorador
# residente (bloquea el JIT de Nex vía LiteLLM), /health con -f, lock en voz-stop.
VOICEBOX_DIR=~/llm-stack/voicebox
VOICEBOX_CMD="${VOICEBOX_CMD:-$VOICEBOX_DIR/run.sh}"            # overrides solo para tests
VOICEBOX_PATRON="${VOICEBOX_PATRON:-backend.main}"              # identidad en `ps` (PID reciclado)
VOICEBOX_PIDFILE="${VOICEBOX_PIDFILE:-$VOICEBOX_DIR/voicebox.pid}"
VOICEBOX_LOGDIR="${VOICEBOX_LOGDIR:-$VOICEBOX_DIR}"
VOICEBOX_URL="${VOICEBOX_URL:-http://127.0.0.1:17493}"
VOICEBOX_ESPERA="${VOICEBOX_ESPERA:-180}"                      # s hasta que /health da 2xx
# Altavoz headless: el backend solo genera; este proceso reproduce (afplay) lo que piden los agentes.
VOICEBOX_ALTAVOZ_CMD="${VOICEBOX_ALTAVOZ_CMD:-/usr/bin/python3 $VOICEBOX_DIR/altavoz.py}"
VOICEBOX_ALTAVOZ_PATRON="${VOICEBOX_ALTAVOZ_PATRON:-altavoz.py}"
VOICEBOX_ALTAVOZ_PIDFILE="${VOICEBOX_ALTAVOZ_PIDFILE:-$VOICEBOX_DIR/altavoz.pid}"
_pid_es() {  # $1 pidfile · $2 patrón: 0 si el PID vive Y su línea de comando contiene el patrón
  local p; [ -f "$1" ] || return 1
  p="$(cat "$1" 2>/dev/null)"; [[ "$p" == <-> ]] || return 1
  kill -0 "$p" 2>/dev/null || return 1
  ps -o command= -p "$p" 2>/dev/null | grep -qF -- "$2"
}
_voz_viva() { _pid_es "$VOICEBOX_PIDFILE" "$VOICEBOX_PATRON"; }
_altavoz_vivo() { _pid_es "$VOICEBOX_ALTAVOZ_PIDFILE" "$VOICEBOX_ALTAVOZ_PATRON"; }
_para_pid() {  # $1 pidfile · $2 patrón: SIGTERM, 10 s, SIGKILL — SOLO si el PID es el nuestro
  local p
  if _pid_es "$1" "$2"; then
    p="$(cat "$1")"; kill "$p" 2>/dev/null
    for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$p" 2>/dev/null || break; sleep 1; done
    kill -0 "$p" 2>/dev/null && kill -9 "$p" 2>/dev/null
  fi
  rm -f "$1"
}
_ps_snapshot() {  # imprime UNA lectura de `lms ps --json` validada como lista; 1 si falla
  # Careo R2: decidir sobre una sola lectura evita el TOCTOU de leer varias veces (una
  # sana y otra fallida tomaban a Nex por ausente). Un fallo NO es "nada cargado".
  local j; j="$(lms ps --json 2>/dev/null)" || return 1
  # Careo R3: cada elemento debe ser un objeto con `identifier` texto ([null] no pasa).
  print -r -- "$j" | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if isinstance(d, list) and all(isinstance(m, dict) and isinstance(m.get("identifier"), str) for m in d) else 1)' 2>/dev/null || return 1
  print -r -- "$j"
}
_en_snapshot() {  # $1 snapshot · $2 identifier: 0 si está cargado
  print -r -- "$1" | python3 -c 'import json,sys; sys.exit(0 if any(m.get("identifier")==sys.argv[1] for m in json.load(sys.stdin)) else 1)' "$2"
}
_arranca_altavoz() {
  _para_pid "$VOICEBOX_ALTAVOZ_PIDFILE" "$VOICEBOX_ALTAVOZ_PATRON"
  local marca; marca=$(wc -l < "$VOICEBOX_LOGDIR/altavoz.log" 2>/dev/null || echo 0)
  nohup env VOICEBOX_URL="$VOICEBOX_URL" VOICEBOX_PID="$(cat "$VOICEBOX_PIDFILE")" VOICEBOX_PATRON="$VOICEBOX_PATRON" \
    ${=VOICEBOX_ALTAVOZ_CMD} >> "$VOICEBOX_LOGDIR/altavoz.log" 2>&1 &
  echo $! > "$VOICEBOX_ALTAVOZ_PIDFILE"
  # Sin esperar, un speak pedido justo después del arranque llega antes de que el altavoz se
  # suscriba a /events/speak y se pierde (visto el 17/10). Hasta 10 s.
  for _ in {1..20}; do
    tail -n +$((marca + 1)) "$VOICEBOX_LOGDIR/altavoz.log" 2>/dev/null | grep -q "conectado a /events/speak" && return 0
    _altavoz_vivo || break
    sleep 0.5
  done
  _para_pid "$VOICEBOX_ALTAVOZ_PIDFILE" "$VOICEBOX_ALTAVOZ_PATRON"
  return 1
}

# ── Guarda: sin `lms` no se toca la RAM (evita falsos "no hay nada cargado") ──
_require_lms() {
  if ! command -v lms >/dev/null 2>&1; then
    echo "ERROR: 'lms' (LM Studio CLI) no está en el PATH. No toco la RAM a ciegas." >&2
    echo "  PATH actual: $PATH" >&2
    exit 3
  fi
}

# ── Lock global: detectar+cargar debe ser atómico entre procesos ──
# Implementación segura en lock.sh (re-careo 2026-08-05: la anterior podía borrar
# el lock de un tercero al recuperar huérfanos).
source ~/llm-stack/lock.sh

# _lock DEVUELVE código, no hace exit: `daemon` debe poder seguir sin RAM si el
# lock está ocupado (antes salía y launchd entraba en bucle de reinicios).
_lock() {
  if llm_lock_adquirir "$LOCKDIR" "${1:-60}"; then
    trap '_unlock' EXIT INT TERM
    return 0
  fi
  echo "AVISO: otro proceso lleva ${1:-60} s manejando modelos; no toco la RAM." >&2
  return 4
}
_unlock() { llm_lock_soltar "$LOCKDIR"; }

# 2026-09-14: `lms ps` (texto) ahora emite códigos ANSI incluso sin TTY ("1h\e[22m")
# → `_ttl_total_cargado` reventaba con "bad math expression" y el wrapper de
# opencode fallaba con "No se pudo preparar el perfil" (dejando Nex descargado
# y un 8B duplicado). Se lee `lms ps --json`, que no lleva colores.
_ps_campo() {  # $1 = identifier, $2 = campo JSON (contextLength | ttlMs); vacío si no está
  lms ps --json 2>/dev/null | python3 -c '
import sys, json
ident, campo = sys.argv[1], sys.argv[2]
for m in json.load(sys.stdin):
    if m.get("identifier") == ident:
        v = m.get(campo); print("" if v is None else v); break
' "$1" "$2" 2>/dev/null
}
_loaded() { [ -n "$(_ps_campo "$1" contextLength)" ]; }
# "idle" | "processing"; vacío si no está cargado. Sirve para no desalojar a un modelo
# que está respondiendo a otra sesión (2026-09-16).
_estado_cargado() { _ps_campo "$1" status; }

# Lee de `lms ps` el contexto y el TTL TOTAL (no el restante) del modelo $1,
# ya cargado. Columnas de `lms ps`: IDENTIFIER MODEL STATUS SIZE_NUM SIZE_UNIT
# CONTEXT PARALLEL DEVICE TTL_restante / TTL_total → $6 y $NF respectivamente.
_ctx_cargado() { _ps_campo "$1" contextLength; }
_ttl_total_cargado() {
  local ms; ms=$(_ps_campo "$1" ttlMs)
  [ -z "$ms" ] && return 1
  echo $(( ms / 1000 ))
}

# LLMs cargados que NO son del perfil pedido ($@ = modelos del perfil), uno por línea.
# 2026-09-15: _perfil solo miraba CODER y GENERAL. Un LLM ajeno al stack (el
# qwen3.8-27b que el bot de Telegram carga por JIT) no contaba → se cargaba Nex
# encima → guardarraíl de LM Studio → wrapper opencode: "No se pudo preparar el perfil".
# Los embeddings no cuentan (pesan poco y los usan otras piezas).
# Test: zsh ~/llm-stack/test-perfil-intrusos.sh
_intrusos() {
  lms ps --json 2>/dev/null | python3 -c '
import sys, json
perfil = set(sys.argv[1:])
for m in json.load(sys.stdin):
    if m.get("type") == "llm" and m.get("identifier") not in perfil:
        print(m.get("identifier"))
' "$@" 2>/dev/null
}

# Intruso = LLM cargado que NO es del stack (FAST · WORKER · GENERAL). Los JIT del stack
# (@worker, @nexn2) nunca cuentan. Sin FORCE: se niega nombrándolo (return 5).
# Con FORCE=1: los descarga. Opción b (2026-09-15).
_desalojar_intrusos() {  # $1 = nombre del perfil (para el mensaje)
  local intrusos m; intrusos=$(_intrusos "$FAST" "$WORKER" "$GENERAL")
  [ -z "$intrusos" ] && return 0
  if [ "${FORCE:-0}" != "1" ]; then
    echo "⚠️  Hay otro modelo cargado fuera del stack: ${intrusos//$'\n'/, } (¿careo, @josiefied o un bot?)."
    echo "   No lo desalojo. Si de verdad quieres cambiar de perfil: FORCE=1 stack.sh $1"
    return 5
  fi
  for m in ${(f)intrusos}; do lms unload "$m" 2>/dev/null; done
  return 0
}

_otro_grande_en_ram() {  # $1 = el grande que quiero; 0 si HAY otro distinto cargado
  local otro
  # 2026-09-25: solo queda UN grande local (GENERAL); CODER retirado el 10/09.
  for otro in "$GENERAL"; do
    [ "$otro" != "$1" ] && _loaded "$otro" && return 0
  done
  return 1
}

# Carga verificada: si falla, lo dice y devuelve error (antes cantaba éxito igual)
# 2026-09-03: si el modelo YA está cargado pero con otro ctx/ttl (venías de
# otro perfil, p.ej. AGENTE→GENERAL), antes se dejaba tal cual — el perfil
# nuevo "mentía" en pantalla. Ahora se compara y, si no coincide, se recarga.
_cargar() {  # $1 = modelo, $2 = contexto, $3 = ttl en segundos (opcional, def. 7200 = 2h)
  # ttl=0 → residente sin caducidad: no se pasa --ttl y `lms ps` devuelve ttlMs null.
  local modelo="$1" ctx="$2" ttl="${3:-7200}"
  local -a ttl_flag=(--ttl "$ttl"); [ "$ttl" = "0" ] && ttl_flag=()
  if _loaded "$modelo"; then
    local ctx_actual ttl_actual
    ctx_actual=$(_ctx_cargado "$modelo")
    ttl_actual=$(_ttl_total_cargado "$modelo"); [ -z "$ttl_actual" ] && ttl_actual=0
    if [ "$ctx_actual" = "$ctx" ] && [ "$ttl_actual" = "$ttl" ]; then
      return 0   # ya está con los parámetros correctos, nada que hacer
    fi
    lms unload "$modelo" 2>/dev/null   # cargado con otro perfil: recargar limpio
  fi
  lms load "$modelo" --context-length "$ctx" "${ttl_flag[@]}" -y >/dev/null 2>&1
  if _loaded "$modelo"; then
    # 2026-10-01 TRIPWIRE: LM Studio 0.4.2x con el runtime MLX 1.10.1/1.11.0 IGNORA el contexto
    # pedido y "auto-ajusta" al máximo que cabe en RAM (bug-tracker #2250/#2318): el explorador
    # cargó a 196k, aceptó un prompt de 88k y el swap subió a 9 GB. Solo el runtime 1.10.0 lo
    # respeta. Si el contexto real no es el pedido, se descarga y se avisa: nunca servir a ciegas.
    local ctx_real; ctx_real=$(_ctx_cargado "$modelo")
    if [ "$ctx_real" != "$ctx" ]; then
      lms unload "$modelo" 2>/dev/null
      echo "ERROR: '$modelo' cargó con contexto $ctx_real en vez de $ctx (auto-fit de LM Studio)." >&2
      echo "   Fija el runtime MLX que lo respeta: lms runtime select mlx-llm-mac-arm64-apple-metal-advsimd@1.10.0" >&2
      return 1
    fi
    return 0
  fi
  echo "ERROR: no se pudo cargar '$modelo' (¿RAM insuficiente? ¿otro modelo grande cargado?)" >&2
  return 1
}

# Cambio de perfil protegido: no desaloja un grande en uso salvo FORCE=1
# $3 = ctx del grande (def. 49152) · $4 = modelo pequeño (def. $FAST) · $5 = su ctx (def. 24576)
# $6 = ttl del grande (def. 7200) · $7 = ttl del pequeño (def. 7200)
# 2026-09-03: TTL más corto para AGENTE (ver caso "agente)" más abajo) — los 3
# modelos de ese perfil (~30GB) dejados IDLE mucho rato empujaron el swap al
# límite (incidente medido: 11,78/12GB de swapfile en <2h). CODE/GENERAL se
# usan a diario y se quedan en 2h a propósito (recargar cada poco penaliza más
# de lo que ahorra en RAM cuando SÍ se están usando).
_perfil() {  # $1 = grande a cargar (o "" para ligero)
  local grande="$1" ctx_g="${3:-49152}" peque="${4:-$FAST}" ctx_p="${5:-24576}" ttl_g="${6:-7200}" ttl_p="${7:-7200}"
  _desalojar_intrusos "$2" || return 5
  # 2026-09-25: un solo grande local → perfil ligero ("") descarga GENERAL; el resto no cruza nada.
  case "$grande" in
    "")         lms unload "$GENERAL" 2>/dev/null ;;
  esac
  # 2026-09-08: ya solo hay UN 8B (FAST==WORKER=R1-8B), no hay riesgo de 8B+8B →
  # el cruce de descarga anterior sobra. _cargar ya no recarga si ya está con sus params.
  [ -n "$grande" ] && { _cargar "$grande" "$ctx_g" "$ttl_g" || return 1; }
  _cargar "$peque" "$ctx_p" "$ttl_p" || return 1
  return 0
}

_arranca_litellm() {
  if ! curl -s -m 2 http://localhost:4000/health/liveliness >/dev/null 2>&1; then
    nohup "$LITELLM" --config "$CFG" --host 127.0.0.1 --port 4000 >> "$LOG" 2>&1 &
    echo $! > "$PIDFILE"
    echo "LiteLLM arrancando en :4000 (log: $LOG)"
  else
    echo "LiteLLM ya estaba en :4000"
  fi
}

_para_litellm() {  # mata SOLO el proceso propio (antes: pkill -f mataba cualquiera)
  if [ -f "$PIDFILE" ]; then
    local p; p="$(cat "$PIDFILE" 2>/dev/null)"
    [ -n "$p" ] && kill "$p" 2>/dev/null
    rm -f "$PIDFILE"
  fi
}

_clave_openrouter() {
  local k; k=$(python3 -c "import json;print(json.load(open('$HOME/.local/share/opencode/auth.json'))['openrouter']['key'])" 2>/dev/null)
  [ -n "$k" ] && export OPENROUTER_API_KEY="$k"
}

case "$1" in
  start)
    _require_lms; _lock 60 || exit 4
    lms server start --port 1234 >/dev/null 2>&1
    _clave_openrouter
    [ -z "${OPENROUTER_API_KEY:-}" ] && echo "⚠️  Sin clave OpenRouter: los alias cloud-* fallarán."
    _arranca_litellm
    _desalojar_intrusos start && _cargar "$FAST" 32768 0 && echo "Stack arrancado: explorador residente (perfil AGENTE)"
    ;;
  code)
    # 2026-09-10 (OK operador): Coder-30B RETIRADO. El código local lo hace Nex.
    # 2026-09-25: en la opción b AGENTE ya no carga Nex (solo el explorador), y el JIT de Nex
    # no cabe con el explorador residente → CODE redirige a GENERAL, que sí lo desaloja.
    echo "ℹ️  Perfil CODE retirado (Coder-30B fuera): el código local lo hace Nex → cargo GENERAL."
    exec "$0" general
    ;;
  general)
    _require_lms; _lock 60 || exit 4
    # 2026-09-16, MEDIDO: el explorador (5,6 GB) y Nex (20,4 GB) NO caben juntos — LM Studio
    # rechaza Nex por guardarraíl ("insufficient system resources", modo high, umbral 4 GiB)
    # incluso con el 65 % de la RAM libre. El relevo automático de LM Studio solo ocurre entre
    # modelos JIT y el explorador lo carga stack.sh, así que hay que desalojarlo a propósito.
    # Al terminar con Nex: `stack.sh agente` devuelve el explorador (lo usan @explorador y el bot).
    if _voz_viva; then
      echo "⛔ Voicebox está corriendo (PID $(cat "$VOICEBOX_PIDFILE")): no cargo Nex encima. Para la voz con 'stack.sh voz-stop'."
      exit 6
    fi
    _desalojar_intrusos general || exit 5
    lms unload "$FAST" 2>/dev/null
    _cargar "$GENERAL" 32768 1800 \
      && echo "Perfil GENERAL activo (Nex 32k TTL 30min · explorador descargado: 'stack.sh agente' lo recupera)"
    ;;
  agente)
    _require_lms; _lock 60 || exit 4
    # 2026-09-15 — OPCIÓN B (OK operador). El orquestador es DeepSeek-V4-Pro (cloud): en RAM
    # fija solo queda el explorador (FAST, no-think @32k, SIN TTL — también lo usa el bot de
    # Telegram). @worker (MiMo-9B) y @nexn2 (Nex) entran JIT vía LiteLLM y salen por TTL; LM Studio
    # releva un JIT por otro (unloadPreviousJITModelOnLoad) → nunca coinciden los tres y Nex
    # siempre cabe. Antes: Nex@32k + R1@24k fijos (~25 GB) en cada arranque de opencode.
    # ⚠️ El JIT carga con el contexto por defecto de LM Studio: R1 fijado a 24k y Nex a 32k en su
    # config por modelo (lección 14/09: R1 recargado por JIT a 8k → bucle de compactación de 8 h).
    # Test: zsh ~/llm-stack/test-perfil-intrusos.sh
    _desalojar_intrusos agente || exit 5
    # 2026-09-16: volver a AGENTE libera Nex si está OCIOSO. Si no, quedan ~26 GB ocupados:
    # el guardarraíl SÍ deja cargar el explorador encima de Nex, pero no al revés, así que
    # la siguiente sesión que pida @nexn2 se lo encuentra bloqueado. Si Nex está respondiendo
    # (status processing) no se toca: puede estar sirviendo a @nexn2 en otra sesión.
    [ "$(_estado_cargado "$GENERAL")" = "idle" ] && lms unload "$GENERAL" 2>/dev/null
    _cargar "$FAST" 32768 0 \
      && echo "Perfil AGENTE activo (explorador residente 32k · @worker MiMo-9B y @nexn2 Nex bajo demanda)"
    ;;
  ligero)
    _require_lms; _lock 60 || exit 4
    _perfil "" ligero 0 "$FAST" 32768 0 0 && echo "Perfil LIGERO activo (solo explorador)"
    ;;
  voz)
    _require_lms; _lock 60 || exit 4
    if ! snap="$(_ps_snapshot)"; then
      echo "⛔ No puedo leer 'lms ps --json': sin saber qué hay en RAM no arranco la voz."; exit 7
    fi
    if _voz_viva; then
      if ! _altavoz_vivo; then
        echo "Altavoz caído: lo relanzo"
        _arranca_altavoz || { echo "⚠️  Voicebox corre pero SIN altavoz: el MCP genera audio y no suena (log: $VOICEBOX_LOGDIR/altavoz.log)"; exit 8; }
      fi
      echo "Voicebox ya está corriendo (PID $(cat "$VOICEBOX_PIDFILE")) en $VOICEBOX_URL"; exit 0
    fi
    if _en_snapshot "$snap" "$GENERAL"; then
      echo "⛔ $GENERAL está cargado: la voz no arranca con el grande en RAM (nunca 2 grandes). Pasa antes a 'stack.sh agente' o 'ligero'."
      exit 6
    fi
    # Explorador RESIDENTE: con él en RAM, LM Studio rechaza el JIT de Nex por guardarraíl
    # (medido 16/09). Es lo único que frena a Nex cuando lo pide un cliente vía LiteLLM
    # (local-general/local-coder) sin pasar por `stack.sh general`.
    _desalojar_intrusos voz || exit 5
    _cargar "$FAST" 32768 0 || exit 1
    rm -f "$VOICEBOX_PIDFILE"
    # Nube de Voicebox fuera (VOICEBOX_CLOUD_ENABLED sin definir) y sin telemetría de HF.
    nohup env -u VOICEBOX_CLOUD_ENABLED HF_HUB_DISABLE_TELEMETRY=1 \
      "$VOICEBOX_CMD" --host 127.0.0.1 --port "${VOICEBOX_URL##*:}" \
      >> "$VOICEBOX_LOGDIR/voicebox.log" 2>&1 &
    echo $! > "$VOICEBOX_PIDFILE"
    sano=0; espera=0
    while (( espera < VOICEBOX_ESPERA )); do
      curl -sf -m 2 "$VOICEBOX_URL/health" >/dev/null 2>&1 && { sano=1; break; }
      _voz_viva || break
      sleep 1; espera=$((espera + 1))
    done
    if (( ! sano )); then
      echo "❌ Voicebox no respondió sano en /health en ${VOICEBOX_ESPERA}s: lo paro (log: $VOICEBOX_LOGDIR/voicebox.log)"
      _para_pid "$VOICEBOX_PIDFILE" "$VOICEBOX_PATRON"; exit 1
    fi
    if ! _arranca_altavoz; then
      echo "⚠️  Voicebox corre pero SIN altavoz: el MCP genera audio y no suena (log: $VOICEBOX_LOGDIR/altavoz.log). 'stack.sh voz' reintenta el altavoz; 'voz-stop' lo para todo."
      exit 8
    fi
    echo "Perfil VOZ activo: Voicebox en $VOICEBOX_URL (MCP en /mcp/) · PID $(cat "$VOICEBOX_PIDFILE") · altavoz PID $(cat "$VOICEBOX_ALTAVOZ_PIDFILE") · 'stack.sh voz-stop' al terminar"
    ;;
  voz-stop)
    _lock 60 || exit 4
    _para_pid "$VOICEBOX_ALTAVOZ_PIDFILE" "$VOICEBOX_ALTAVOZ_PATRON"
    if _voz_viva; then
      p="$(cat "$VOICEBOX_PIDFILE")"
      curl -s -m 10 -X POST "$VOICEBOX_URL/models/unload" >/dev/null 2>&1   # libera la GPU antes de matar
      _para_pid "$VOICEBOX_PIDFILE" "$VOICEBOX_PATRON"
      echo "Voicebox parado (PID $p)"
    else
      echo "Voicebox no estaba corriendo"
    fi
    rm -f "$VOICEBOX_PIDFILE"
    ;;
  daemon)
    # Modo LaunchAgent: LiteLLM en PRIMER PLANO bajo KeepAlive.
    # CRÍTICO (careo 2026-08-05): NO forzar perfil aquí. Un reinicio de LiteLLM
    # no debe tocar la RAM — antes ejecutaba `$0 code` y desalojaba el 35B que
    # estuviera usando hermes. Solo se prepara el perfil si NO hay ningún grande
    # cargado (arranque en frío del equipo).
    _require_lms
    lms server start --port 1234 >/dev/null 2>&1
    _clave_openrouter
    if _lock 30; then
      # 2026-09-15 (opción b): en frío solo se garantiza el explorador residente (lo usan
      # opencode, enrutar y el bot de Telegram). NO se carga Nex: hermes y opencode van en
      # DeepSeek-V4-Pro (cloud). Nunca desaloja nada: un reinicio de LiteLLM no debe tocar
      # lo que esté en uso (careo 2026-08-05).
      if _loaded "$FAST"; then
        echo "Explorador ya residente: no toco la RAM"
      else
        _cargar "$FAST" 32768 0 && echo "Arranque en frío: explorador residente cargado"
      fi
      _unlock; trap - EXIT INT TERM
    fi
    _para_litellm; sleep 1
    exec "$LITELLM" --config "$CFG" --host 127.0.0.1 --port 4000 >> "$LOG" 2>&1
    ;;
  stop)
    _require_lms; _lock 60 || exit 4
    lms unload "$GENERAL" 2>/dev/null; lms unload "$FAST" 2>/dev/null; lms unload "$WORKER" 2>/dev/null
    lms server stop >/dev/null 2>&1
    _para_litellm
    echo "Stack parado"
    ;;
  status)
    echo "── LM Studio (cargados) ──"; lms ps 2>/dev/null || echo "  (lms no disponible)"
    echo "── Runtime MLX (debe ser 1.10.0: 1.10.1/1.11.0 ignoran el contexto) ──"; lms runtime ls 2>/dev/null | grep -E "mlx.*✓" || echo "  (sin runtime MLX seleccionado)"
    echo "── LiteLLM ──"
    curl -s -m 3 http://localhost:4000/v1/models -H "Authorization: Bearer x" | python3 -m json.tool 2>/dev/null || echo "no responde en :4000"
    [ -d "$LOCKDIR" ] && echo "── ⚠️ lock activo (pid $(cat $LOCKDIR/pid 2>/dev/null)) ──"
    ;;
  *)
    echo "Uso: stack.sh start | stop | code | general | agente | ligero | voz | voz-stop | status | daemon"
    echo "     FORCE=1 stack.sh code|general  → desalojar un grande en uso a propósito" ;;
esac
