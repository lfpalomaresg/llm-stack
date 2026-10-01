#!/bin/zsh
# bench-vs-nex.sh — Bench VS Nex-N2-mini (actual) vs Nex-N2.5-mini (candidato), 2026-10-01.
# Corre SOLO (LaunchAgent nocturno o a mano). Mismo arnés que el VS del 09/09 (bench-coder.py:
# 6 tareas de código con verificación ejecutable + velocidad) y, para N2.5, dos pasadas:
# su modo por defecto (reasoning_effort adaptativo) y "none" (sin pensar), para medir el coste
# real del razonamiento. Al terminar devuelve el perfil AGENTE y avisa por notificación.
# Regla de la sala: un solo grande en RAM; nunca corre si hay un modelo PROCESSING.
set -u
export PATH="$HOME/.lmstudio/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
OUTDIR=~/llm-stack/bench-vs-nex; mkdir -p "$OUTDIR"
LOG="$OUTDIR/run-$(date +%Y%m%d-%H%M).log"; exec > >(tee -a "$LOG") 2>&1
REPORT="$OUTDIR/REPORT-$(date +%Y%m%d).md"
N2="nex-n2-mini-local"; N25_HF="mlx-community/Nex-N2.5-mini-OptiQ-4bit"
notify() { osascript -e "display notification \"$1\" with title \"Bench Nex N2 vs N2.5\"" 2>/dev/null; }
fail() { echo "❌ $1"; notify "FALLÓ: $1"; echo "# Bench N2 vs N2.5 — FALLÓ: $1 ($(date))" > "$REPORT"; ~/llm-stack/stack.sh agente >/dev/null 2>&1; exit 1; }
echo "== bench-vs-nex $(date) =="
lms ps --json >/dev/null 2>&1 || fail "lms no responde (¿LM Studio cerrado?)"
lms ps --json | grep -q '"status": *"processing"' && fail "hay un modelo PROCESSING; no interrumpo"
# 1) candidato en disco
N25=$(lms ls --json 2>/dev/null | python3 -c 'import sys,json;[print(m.get("modelKey") or m.get("path")) for m in json.load(sys.stdin) if "n2.5" in (m.get("modelKey","")+m.get("path","")).lower()]' | head -1)
if [ -z "$N25" ]; then
  echo "descargando $N25_HF ..."; lms get "$N25_HF" --mlx -y || fail "descarga de N2.5"
  N25=$(lms ls --json | python3 -c 'import sys,json;[print(m.get("modelKey") or m.get("path")) for m in json.load(sys.stdin) if "n2.5" in (m.get("modelKey","")+m.get("path","")).lower()]' | head -1)
  [ -n "$N25" ] || fail "N2.5 no aparece tras la descarga"
fi
echo "N2.5 = $N25"
# 2) bench en serie, un grande cada vez, 32k como en producción
run_one() {  # $1 id · $2 etiqueta · $3 fichero · $4 extra json
  lms unload --all >/dev/null 2>&1; sleep 3
  lms load "$1" --context-length 32768 --ttl 1800 -y >/dev/null 2>&1 || fail "no carga $1"
  sleep 2
  BENCH_EXTRA_JSON="${4:-{\}}" python3 ~/llm-stack/bench-coder.py "$1" "$2" "$3" || echo "(bench $2 devolvió error)"
}
run_one "$N2"  "N2-mini (actual, template no-think)" "$OUTDIR/n2.md"
run_one "$N25" "N2.5-mini (defecto: adaptativo)"      "$OUTDIR/n25-default.md"
run_one "$N25" "N2.5-mini (reasoning_effort=none)"    "$OUTDIR/n25-none.md" '{"reasoning_effort":"none"}'
# 3) latencia con prompt largo (14k tokens, el caso que arrastró a opencode el 10/09)
long() { python3 - "$1" <<'PY'
import sys,json,time,urllib.request
mid=sys.argv[1]; txt=("La ocupación del hotel fue del 85% con ADR 120. "*1400)
body={"model":mid,"max_tokens":60,"temperature":0,"messages":[{"role":"user","content":txt+"\n\nResume en una frase."}]}
req=urllib.request.Request("http://localhost:1234/v1/chat/completions",data=json.dumps(body).encode(),headers={"Content-Type":"application/json"})
for k in ("frío","caliente"):
    t=time.time(); r=json.loads(urllib.request.urlopen(req,timeout=600).read()); dt=time.time()-t
    u=r.get("usage",{}); print(f"  prompt largo {k}: {dt:.1f}s · prompt {u.get('prompt_tokens')} tok · razonamiento {(u.get('completion_tokens_details') or {}).get('reasoning_tokens',0)}")
PY
}
{
  echo "# Bench VS · Nex-N2-mini vs Nex-N2.5-mini — $(date '+%Y-%m-%d %H:%M')"; echo
  echo "Arnés: bench-coder.py (6 tareas verificables + velocidad) · 32k · un grande cada vez · M4 Max 36 GB"; echo
  for f in n2 n25-default n25-none; do echo "## $(head -1 "$OUTDIR/$f.md" | sed 's/^# //')"; sed -n '2,$p' "$OUTDIR/$f.md"; echo; done
  echo "## Latencia prompt largo (14k)"; echo '```'
  lms unload --all >/dev/null 2>&1; sleep 3; lms load "$N2" --context-length 32768 --ttl 1800 -y >/dev/null 2>&1; echo "N2:"; long "$N2"
  lms unload --all >/dev/null 2>&1; sleep 3; lms load "$N25" --context-length 32768 --ttl 1800 -y >/dev/null 2>&1; echo "N2.5:"; long "$N25"
  echo '```'
} > "$REPORT"
# 4) dejar el stack como estaba
lms unload --all >/dev/null 2>&1; ~/llm-stack/stack.sh agente >/dev/null 2>&1
echo "== FIN $(date) → $REPORT =="; notify "Terminado: $REPORT"
