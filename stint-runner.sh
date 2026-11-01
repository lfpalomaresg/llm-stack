#!/usr/bin/env bash
# ============================================================================
# stint-runner.sh — Stint de automejora DESATENDIDO con opencode headless.
#
# Ejecuta `opencode run --auto` sobre uno o varios repos durante N horas (reparte
# el tiempo entre ellos), con guardarríles y registro. Para lanzar y dejar corriendo.
#
# USO:
#   stint-runner.sh --hours 4 --dir ~/MAIN_PROYECTOS/rds-revenue-decision-system
#   stint-runner.sh --hours 4 --dir <repoA> --dir <repoB>          # reparte 2 h/repo
#   stint-runner.sh --hours 4 --dir <repo> --model <provider/model> --brief <fichero>
#   stint-runner.sh --hours 4 --dir <repo> --dry-run               # valida, NO lanza
#
# GUARDARRÍLES (por defecto): NO push · NO recursos externos · NO publicación ·
# Soho/personal → local · careo por loop con Codex+Gemini · parada limpia (watchdog).
#
# NOTA de salud: LiteLLM se comprueba en /health/liveliness (su /health da 404);
# agy-bridge por puerto :4010. El preflight de round-automejora.sh sondea /health
# y da FALSO NEGATIVO — no fiarse de él para esto.
# ============================================================================
set -euo pipefail

# PATH con shims locales (p.ej. `timeout`, que macOS no trae) para que el agente
# headless no tropiece con comandos ausentes y entre en bucles de reintento.
export PATH="$HOME/llm-stack/bin:$PATH"
# Commits de la RAMA LOCAL del stint sin pelear con el gate `conclave` (sello de
# doble OK) — el operador revisará la rama. El escaneo de secretos del hook sigue
# activo (bloquea claves SIEMPRE, incluso con override).
export CONCLAVE_OVERRIDE=1

HOURS=4
DIRS=()
MODEL=""
BRIEF=""
BRANCH=""
DRY_RUN=0
LITELLM_URL="http://localhost:4000"
AGY_URL="http://localhost:4010"
LOGROOT="$HOME/llm-stack/stint-logs"

die() { echo "✗ $*" >&2; exit 1; }
info() { echo "• $*"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hours) HOURS="$2"; shift 2 ;;
    --dir) DIRS+=("$2"); shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --brief) BRIEF="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "argumento no reconocido: $1" ;;
  esac
done

[[ ${#DIRS[@]} -gt 0 ]] || die "--dir es obligatorio (repetible para varios repos)"
[[ "$HOURS" =~ ^[0-9]+([.][0-9]+)?$ ]] || die "--hours debe ser un número: $HOURS"
command -v opencode >/dev/null 2>&1 || die "opencode no está en el PATH"
for d in "${DIRS[@]}"; do
  [[ -d "$d" ]] || die "--dir no existe: $d"
  git -C "$d" rev-parse --git-dir >/dev/null 2>&1 || die "$d no es un repo git"
done

SECONDS_TOTAL=$(python3 -c "print(int(float('$HOURS')*3600))")
SECONDS_PER=$(( SECONDS_TOTAL / ${#DIRS[@]} ))
TS="$(date +%Y%m%d-%H%M%S)"
[[ -n "$BRANCH" ]] || BRANCH="round/stint-$(date +%Y%m%d)"
[[ -n "$BRIEF" ]] || BRIEF="$HOME/llm-stack/stint-brief.md"
[[ -f "$BRIEF" ]] || die "brief no encontrado: $BRIEF"
LOG="$LOGROOT/$TS"
mkdir -p "$LOG"

echo "══════════════════════════════════════════"
echo " STINT headless — $(date '+%F %T')"
echo " repos:  ${DIRS[*]}"
echo " branch: $BRANCH"
echo " dur:    ${HOURS} h total ($(( SECONDS_PER/60 )) min/repo)"
echo " model:  ${MODEL:-(por defecto de opencode)}"
echo " brief:  $BRIEF"
echo " log:    $LOG/"
echo "══════════════════════════════════════════"

# ── 1. Preflight de servicios (endpoints CORRECTOS) ──────────────────────────
info "LiteLLM: $(curl -s --max-time 5 "$LITELLM_URL/health/liveliness" 2>/dev/null || echo '?')"
if curl -s --max-time 5 "$AGY_URL/v1/models" >/dev/null 2>&1; then
  info "agy-bridge :4010 OK"
else
  info "agy-bridge :4010 no responde (careo local gratis no disponible; se sigue con Codex/Gemini)"
fi
if log show --last 2h 2>/dev/null | grep -q "IOGPUFamily"; then
  info "⚠️ GPU panic reciente — evitar modelos locales grandes"
fi

# ── 2. Brief (una copia por repo con su encabezado) ──────────────────────────
for d in "${DIRS[@]}"; do
  { echo "=== STINT $(date '+%F %T') · repo $(basename "$d") · rama $BRANCH · $(( SECONDS_PER/60 )) min ==="; cat "$BRIEF"; } \
    > "$LOG/brief-$(basename "$d").txt"
done

if [[ "$DRY_RUN" = 1 ]]; then
  echo "── DRY-RUN: setup validado (NO se crean ramas ni se lanza). Se lanzaría:"
  for d in "${DIRS[@]}"; do
    echo "   cd $d && opencode run --auto ${MODEL:+--model $MODEL} \"<brief de $LOG/brief-$(basename "$d").txt>\""
  done
  echo "   watchdog: ${SECONDS_PER}s por repo → SIGTERM/SIGKILL · rama $BRANCH"
  exit 0
fi

# ── 3. caffeinate (anti-sueño, con margen) ───────────────────────────────────
caffeinate -i -t $((SECONDS_TOTAL + 600)) &
CAFF=$!
cleanup() { kill "$CAFF" 2>/dev/null || true; }
trap cleanup EXIT

# ── 4. Por repo: rama local → opencode run (watchdog) ────────────────────────
GLOBAL_RC=0
for d in "${DIRS[@]}"; do
  name="$(basename "$d")"
  if git -C "$d" show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git -C "$d" checkout "$BRANCH" >/dev/null; info "[$name] rama $BRANCH (checkout)"
  else
    git -C "$d" checkout -b "$BRANCH" >/dev/null; info "[$name] rama $BRANCH creada"
  fi

  # `opencode run` es UNA sesión autónoma que TERMINA cuando el agente acaba su plan
  # (no dura el budget). Para llenar las horas, RE-LANZAMOS sesiones hasta el deadline
  # (resume con --continue), con corte anti-bucle si una sesión dura muy poco.
  deadline=$(( $(date +%s) + SECONDS_PER ))
  iter=0
  while [ "$(date +%s)" -lt "$deadline" ]; do
    iter=$((iter+1))
    remaining=$(( deadline - $(date +%s) ))
    [ "$remaining" -lt 30 ] && { info "[$name] quedan <30s, paro"; break; }
    CONT=""; [ "$iter" -gt 1 ] && CONT="--continue"
    info "[$name] sesión $iter (quedan $((remaining/60)) min) · log: run-$name.log"
    ( cd "$d" && opencode run --auto $CONT ${MODEL:+--model "$MODEL"} "$(cat "$LOG/brief-$name.txt")" ) \
      >> "$LOG/run-$name.log" 2>&1 &
    OC=$!
    ( sleep "$remaining"; kill -TERM "$OC" 2>/dev/null || true; sleep 15; kill -KILL "$OC" 2>/dev/null || true ) &
    WD=$!
    t0=$(date +%s)
    set +e; wait "$OC"; RC=$?; set -e
    kill "$WD" 2>/dev/null || true
    dur=$(( $(date +%s) - t0 )); GLOBAL_RC=$RC
    info "[$name] sesión $iter terminó (rc=$RC, ${dur}s)"
    [ "$dur" -lt 30 ] && { info "[$name] sesión muy corta — corto el bucle (anti-bucle)"; break; }
  done
done

# ── 5. Resumen ───────────────────────────────────────────────────────────────
{
  echo "══════════════════════════════════════════"
  echo " STINT terminado — $(date '+%F %T') — rc=$GLOBAL_RC"
  for d in "${DIRS[@]}"; do
    echo "── $(basename "$d") · rama $BRANCH · últimos commits:"
    git -C "$d" log --oneline -8 | sed 's/^/   /'
  done
  echo " logs: $LOG/"
  echo "══════════════════════════════════════════"
} | tee "$LOG/resumen.txt"
info "hecho. Nada se ha pusheado (ramas locales)."
