#!/bin/zsh
# LLM Stack v5.3 — control del stack local
# Uso: stack.sh start | stop | code | general | agente | ligero | status | daemon
#      Variables: FORCE=1 → permite desalojar un grande en uso (uso consciente)
#
# Perfiles (nunca 2 grandes a la vez — regla anti-cuelgue):
#   code    → Qwen3-Coder-30B (ctx 32k) + Qwen3-8B (ctx 24k)   [default]
#   general → Qwen3.6-35B multimodal (ctx 48k) + Qwen3-8B
#   agente  → 35B orquestador (32k) + DeepSeek-R1-8B workers (16k)  [v5.4, 2026-08-21]
#   ligero  → solo Qwen3-8B
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
LOCKDIR=/tmp/llm-stack.lock

CODER="qwen3-coder-30b-a3b-instruct-mlx"
GENERAL="qwen3.6-35b-a3b"
FAST="qwen3-8b"
WORKER="deepseek/deepseek-r1-0528-qwen3-8b"   # workers ×N con razonamiento R1 (v5.4)

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

_loaded() { lms ps 2>/dev/null | awk 'NR>1 && NF>3 {print $1}' | grep -qx "$1"; }

_otro_grande_en_ram() {  # $1 = el grande que quiero; 0 si HAY otro distinto cargado
  local otro
  for otro in "$CODER" "$GENERAL"; do
    [ "$otro" != "$1" ] && _loaded "$otro" && return 0
  done
  return 1
}

# Carga verificada: si falla, lo dice y devuelve error (antes cantaba éxito igual)
_cargar() {  # $1 = modelo, $2 = contexto
  _loaded "$1" && return 0
  lms load "$1" --context-length "$2" --ttl 7200 -y >/dev/null 2>&1
  if _loaded "$1"; then return 0; fi
  echo "ERROR: no se pudo cargar '$1' (¿RAM insuficiente? ¿otro modelo grande cargado?)" >&2
  return 1
}

# Cambio de perfil protegido: no desaloja un grande en uso salvo FORCE=1
# $3 = ctx del grande (def. 49152) · $4 = modelo pequeño (def. $FAST) · $5 = su ctx (def. 24576)
_perfil() {  # $1 = grande a cargar (o "" para ligero)
  local grande="$1" ctx_g="${3:-49152}" peque="${4:-$FAST}" ctx_p="${5:-24576}"
  if [ -n "$grande" ] && _otro_grande_en_ram "$grande" && [ "${FORCE:-0}" != "1" ]; then
    echo "⚠️  Hay otro modelo grande cargado (posible sesión de opencode/hermes en curso)."
    echo "   No lo desalojo. Si de verdad quieres cambiar de perfil: FORCE=1 stack.sh $2"
    return 5
  fi
  case "$grande" in
    "$CODER")   lms unload "$GENERAL" 2>/dev/null ;;
    "$GENERAL") lms unload "$CODER"   2>/dev/null ;;
    "")         lms unload "$CODER" 2>/dev/null; lms unload "$GENERAL" 2>/dev/null ;;
  esac
  # El pequeño que NO toca en este perfil se descarga (evita sumar 8B+8B)
  case "$peque" in
    "$FAST")   lms unload "$WORKER" 2>/dev/null ;;
    "$WORKER") lms unload "$FAST"   2>/dev/null ;;
  esac
  [ -n "$grande" ] && { _cargar "$grande" "$ctx_g" || return 1; }
  _cargar "$peque" "$ctx_p" || return 1
  return 0
}

_arranca_litellm() {
  if ! curl -s -m 2 http://localhost:4000/health/liveliness >/dev/null 2>&1; then
    nohup "$LITELLM" --config "$CFG" --port 4000 >> "$LOG" 2>&1 &
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
    _perfil "$CODER" code 32768 && echo "Perfil CODE activo (coder 32k + fast 24k)"
    ;;
  code)
    _require_lms; _lock 60 || exit 4
    _perfil "$CODER" code 32768 && echo "Perfil CODE activo (coder 32k + fast 24k)"
    ;;
  general)
    _require_lms; _lock 60 || exit 4
    _perfil "$GENERAL" general && echo "Perfil GENERAL activo (35B multimodal 48k + fast 24k)"
    ;;
  agente)
    _require_lms; _lock 60 || exit 4
    _perfil "$GENERAL" agente 32768 "$WORKER" 16384 \
      && echo "Perfil AGENTE activo (35B orquestador 32k + R1-8B workers 16k · auditor: GLM cloud / gemma JIT)"
    ;;
  ligero)
    _require_lms; _lock 60 || exit 4
    _perfil "" ligero && echo "Perfil LIGERO activo (solo 8B)"
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
      if ! _loaded "$CODER" && ! _loaded "$GENERAL"; then
        # 2026-08-22 (§10.b, OK operador): en frío se carga GENERAL, no CODE.
        # El proceso siempre-encendido es el gateway de hermes (Telegram) y su
        # modelo es el 35B; el coder solo hace falta al abrir opencode, cuyo
        # wrapper ya garantiza el swap. Con CODE en frío, hermes-por-Telegram
        # quedaba sin modelo y reintentaba contra el guardarraíl (18 min/resp).
        _perfil "$GENERAL" general && echo "Arranque en frío: perfil GENERAL activo (gateway hermes)"
      else
        echo "Ya hay un modelo grande cargado: no toco la RAM (posible sesión en curso)"
      fi
      _unlock; trap - EXIT INT TERM
    fi
    _para_litellm; sleep 1
    exec "$LITELLM" --config "$CFG" --port 4000 >> "$LOG" 2>&1
    ;;
  stop)
    _require_lms; _lock 60 || exit 4
    lms unload "$CODER" 2>/dev/null; lms unload "$GENERAL" 2>/dev/null; lms unload "$FAST" 2>/dev/null; lms unload "$WORKER" 2>/dev/null
    lms server stop >/dev/null 2>&1
    _para_litellm
    echo "Stack parado"
    ;;
  status)
    echo "── LM Studio (cargados) ──"; lms ps 2>/dev/null || echo "  (lms no disponible)"
    echo "── LiteLLM ──"
    curl -s -m 3 http://localhost:4000/v1/models -H "Authorization: Bearer x" | python3 -m json.tool 2>/dev/null || echo "no responde en :4000"
    [ -d "$LOCKDIR" ] && echo "── ⚠️ lock activo (pid $(cat $LOCKDIR/pid 2>/dev/null)) ──"
    ;;
  *)
    echo "Uso: stack.sh start | stop | code | general | agente | ligero | status | daemon"
    echo "     FORCE=1 stack.sh code|general  → desalojar un grande en uso a propósito" ;;
esac
