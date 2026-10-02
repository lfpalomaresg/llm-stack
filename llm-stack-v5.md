# LLM Stack v5 — MacBook Pro M4 Max 36 GB

> Implementado el 2026-08-02. Sustituye a `llm-stack-conversation.md` (v3/v4), que queda como histórico.
> Diseño: multiagente ≠ multimodelo — un grande caliente + un pequeño + embeddings; cloud solo por señal objetiva con techo de gasto físico.
> **Última actualización: 2026-10-02 (v5.6).** Historial completo de versiones al final del fichero.
> El detalle agéntico (decisiones, incidentes, §§ 1-22) vive en `~/llm-stack/sistema-agentico.md`.

## Arquitectura (v5.6 — DOS PLANOS, 2026-09-10)

```
Claude Code ─┐
opencode   ──┤──► LiteLLM proxy (localhost:4000/v1)
hermes     ──┤         │
scripts    ──┘         ├── PLANO LOCAL (sensible — dato nunca sale del Mac)
                       │   LM Studio (localhost:1234): Nex-N2-mini · R1-8B · Qwen3.5-9B
                       │                               gpt-oss-20b · Phi-4 · Gemma-E4B
                       │   Antigravity (localhost:4010): gpt-oss-120B · gpt-oss-20B (0 GPU)
                       │
                       └── PLANO CLOUD (NO sensible — por decisión consciente del operador)
                           OpenRouter (prepago SIN auto-recarga):
                           cloud-agentic (V4.1-Flash) · cloud-coder-value (V4-Pro)
                           cloud-coder (GLM-5.3) · cloud-megacontext (V4-Pro 1M)
                           cloud-reasoning (V3.2) · cloud-vision (MiniMax-M3) · …
```

**Regla nº1: nadie carga modelos excepto LM Studio.** hermes desktop/CLI y opencode son clientes finos.
**Ley de frontera (v5.6):** Claude Code, opencode y hermes son orquestadores de NUBE — el dato sensible (Soho/cliente/personal) lo procesa Nex en local, nunca pegado en el contexto de la nube. El salto a cloud sobre datos sensibles es DECISIÓN CONSCIENTE del operador, jamás automático.

## Modelos (v5.6 — 2026-10-02, 19 alias LiteLLM)

### Local (LM Studio, localhost:1234)

| Alias | Modelo real | RAM | Ctx | Rol |
|---|---|---|---|---|
| `local-general` / `local-coder` | **Nex-N2-mini** (Qwen3.5-35B-A3B, agentic-tuned) | ~20 GB | 32k | Orquestador sensible · código local JIT; ÚNICO grande local |
| `local-worker` | DeepSeek-R1-0528-Qwen3-8B MLX | ~5 GB | 24k | Workers ×4 con razonamiento (temp 0.6, top_p 0.95) |
| `local-fast` | **Qwen3.5-9B MLX** (no-think template) | ~6 GB | 32k | Explorador RESIDENTE — lookups, commits, bot Telegram |
| `local-embed` | Qwen3-Embedding-0.6B | ~0.6 GB | — | RAG |
| `local-reasoner` | gpt-oss-20b (OpenAI) | ~12 GB | — | Razonamiento pesado local JIT |
| `local-reviewer-ms` | Phi-4-reasoning-plus MLX | ~8 GB | — | Revisor capa 1 careo (linaje Microsoft ≠ Qwen) |
| `local-auditor` | Gemma-4-E4B-IT MLX | ~3 GB | 8k | Auditor sensible JIT (linaje Google ≠ Qwen) |
| `local-uncensored` | Josiefied-Qwen3-30B-A3B abliterado | ~18 GB | — | Red-team / brainstorm; JIT, NUNCA residente |

### Gratis vía Antigravity CLI (agy-bridge, localhost:4010, 0 GPU local)

| Alias | Modelo | Rol |
|---|---|---|
| `gpt-oss-free` | gpt-oss-120b | Razonamiento acotado NO sensible (~10 s, 0 €) |
| `auditor-free` | gpt-oss-20b | Auditor capa 1 del careo (alternativo, 0 coste) |

### Cloud (OpenRouter, prepago sin auto-recarga — solo NO sensible)

| Alias | Modelo real | Precio aprox* | Ctx | Rol |
|---|---|---|---|---|
| `cloud-agentic` | DeepSeek-V4.1-Flash | $0.14-0.30/$0.56-1.20/M | 1M | **Primario opencode** (agéntico rápido; 2-3× más rápido que V4-Pro) |
| `cloud-coder-value` | DeepSeek-V4-Pro | ~$1.5-1.7/$0.42/M* | 1M | Escalado valor · default hermes (`dpsk`) |
| `cloud-megacontext` | DeepSeek-V4-Pro | ~$1.5-1.7/$0.42/M* | 1M | Repo entero + logs (alias semántico hermes) |
| `cloud-coder` | GLM-5.3 (Z-AI) | $1.40/$4.40/M | 1.3M | Código duro (5× menos verboso que GLM-5.2) |
| `cloud-coder-flash` | GLM-5.3-Flash | $0.075/$0.25/M | — | Código valor (38× más barato que GLM-5.2 por tarea) |
| `cloud-reasoning` | DeepSeek-V3.2 | $0.27/$0.40/M | 164k | Razonamiento barato |
| `cloud-megacontext-max` | Kimi-K3 | $3/$15/M | 1M | Techo multimodal duro |
| `cloud-vision` | MiniMax-M3 | $0.30/$1.20/M | 1M | Vídeo / docs visuales pesados |

*Con `data_collection: deny` (todos los aliases desde 2026-10-02): OpenRouter excluye proveedores baratos de alto riesgo (Baidu, StreamLake) → V4-Pro sube de ~$0.21 a ~$1.5-1.7/M entrada. La ganancia es privacidad garantizada.

## Perfiles de RAM (nunca 2 grandes a la vez)

| Perfil | Cargado | RAM aprox | Cuándo usarlo |
|---|---|---|---|
| **AGENTE** (default desde 2026-09-15) | Qwen3.5-9B residente; Nex y R1-8B JIT | ~6 GB + JIT | Opencode (orquestador = V4.1-Flash en cloud) |
| **GENERAL** | Nex-N2-mini 32k TTL 30 min (descarga el explorador) | ~20 GB | Tareas locales grandes, dato sensible, hermes local |
| **LIGERO** | solo explorador | ~6 GB | Batería / background |

> **CODE retirado** (2026-09-10): el Coder-30B se borró del disco. `stack.sh code` redirige a GENERAL.

## Operación diaria

**El stack arranca solo al iniciar sesión** (LaunchAgent `com.luisfran.llm-stack`,
plist en `~/Library/LaunchAgents/`, log en `~/llm-stack/launchagent.log`).
Abrir hermes/opencode directamente; estos comandos son para control manual:

```bash
~/llm-stack/stack.sh start     # arranca LM Studio + LiteLLM + perfil AGENTE (LaunchAgent lo hace al login)
~/llm-stack/stack.sh general   # carga Nex 32k TTL 30 min (descarga explorador)
~/llm-stack/stack.sh agente    # vuelve a AGENTE (explorador residente, Nex JIT)
~/llm-stack/stack.sh ligero    # solo explorador (batería / background)
~/llm-stack/stack.sh status    # qué hay cargado + salud de LiteLLM
~/llm-stack/stack.sh stop      # parar todo
```

Los JIT (Nex, R1-8B) entran bajo demanda vía LiteLLM y salen solos por TTL. El swap AGENTE↔GENERAL tarda ~10-20 s.

## Archivos del stack

- `~/llm-stack/litellm.config.yaml` — 19 alias, enrutado. **Cambiar un modelo = editar aquí, cero cambios en clientes.**
- `~/llm-stack/stack.sh` — control de perfiles (v5.6).
- `~/llm-stack/sistema-agentico.md` — historial completo de versiones §1-§22, decisiones, incidentes.
- `~/llm-stack/.venv/` — LiteLLM (última versión estable instalada).
- `~/llm-stack/litellm.log` — log del proxy.
- `~/.config/opencode/` — config de opencode (usa cloud-agentic como modelo primario desde 01/10).
- `~/.hermes/config.yaml` — provider `llm-stack`, default `local-general` (Nex) / hermes usa cloud-megacontext.
- ~~Symlink modelo 35B~~ **RETIRADO** 2026-09-10: Qwen3.6-35B-A3B y Coder-30B borrados del disco. No re-descargar sin caso concreto nuevo.

## Presupuesto (mecanismo anti-susto, 3 capas)

1. **OpenRouter: crédito prepagado con auto-recarga OFF** ← el techo físico real (se configura en openrouter.ai/settings/credits).
2. LiteLLM registra cada llamada en `litellm.log`.
3. Los alias `cloud-*` solo se usan por decisión explícita (nunca fallback automático desde local).

## Clave de OpenRouter (resuelto — fuente única)

`stack.sh start` lee la clave automáticamente del almacén de opencode
(`~/.local/share/opencode/auth.json`, entrada `openrouter`). No hay que exportar
nada en `.zshrc` ni duplicar la clave. Si algún día se rota la clave, basta
re-autenticar opencode (`opencode auth login`) y reiniciar el stack.

Validado 2026-08-02: ping a GLM-5.2 vía LiteLLM → "CLOUD OK". Validado 2026-10-01: cloud-agentic (V4.1-Flash) con data_collection:deny.

## Test de estrés pendiente (antes de fiarse en sesiones largas)

1. `stack.sh general` → prompts de ~8k → ~32k → ~64k mirando presión de memoria en Monitor de Actividad.
2. Donde se ponga amarilla, restar 20% y fijar ese contexto en `stack.sh`.
3. Ronda final: 35B cargado + petición simultánea a `local-fast`. Verde/amarillo estable = stack validado.

## Limpieza ejecutada (2026-08-02)

- LM Studio: borrados gemma-4-31B, Qwen3-VL-32B, Qwen2.5-Coder-32B, Qwen3-32B (**71 GB**).
- Ollama: borrados qwen3, qwen3:32b, gpt-oss:20b, gemma4 ×2 (**62 GB**). Conservado `minimax-m3:cloud` (alias, 0 disco) y el binario de Ollama.
- Total liberado: **~133 GB**. Todo re-descargable con un comando.

## Incidente 2026-08-02 y endurecimiento (v5.1)

- **Apagón con opencode (02/08 madrugada):** sin kernel panic registrado → congelón por
  RAM (KV cache) + apagado forzado. Causa: techos de contexto demasiado generosos
  (coder 80k). **Fix: techos conservadores 48k/48k/24k** — subir solo tras pasar el
  test de estrés con Monitor de Actividad.
- **LiteLLM muerto tras reiniciar:** launchd mata los hijos en background al terminar
  el script del agente (el nohup no protege). **Fix: modo `daemon`** — LiteLLM es el
  proceso principal del LaunchAgent con `KeepAlive` (si muere, resucita solo; probado
  matándolo a propósito).
- **Fallbacks silenciosos eliminados:** si pides un grande que no cabe (guardarraíl de
  LM Studio con el otro grande cargado), el error es VISIBLE y dice qué pasa — antes
  LiteLLM te colaba el 8B en silencio.

**Disciplina de perfiles (v5.6):**
- Sesión opencode → perfil AGENTE (el default). El orquestador es cloud-agentic (V4.1-Flash); los modelos locales entran JIT solo para tareas sensibles o sin red.
- Sesión hermes (contexto gigante) → `stack.sh general` (Nex residente 32k).
- Si un agente da "insufficient system resources" → guardarraíl de LM Studio. Cambia de perfil con stack.sh; no es avería.

## Claude Code conectado directo al stack (MCP, 2026-08-21)

Además de `opencode`/`hermes`/`scripts` (incluida la skill `enrutador-ia`),
Claude Code ahora tiene una **puerta de entrada adicional** a proveedores que
`enrutador-ia` ya usa, vía un MCP server propio (`local-models`, registrado a
nivel de usuario con `claude mcp add local-models -s user -- ...`):

- `~/llm-stack/mcp-local-models/server.py` — 3 tools:
  - `list_local_models()` — catálogo de alias locales.
  - `ask_local_model(model, prompt, system)` — habla con `localhost:4000/v1/chat/completions`
    (LiteLLM, misma API que ya usa `enrutador-ia`). Restringido a los 6 alias
    `local-*`. Nunca sale de la máquina.
  - `ask_openrouter_model(model, prompt, system)` — **catálogo libre de
    OpenRouter** (cualquier id de openrouter.ai/models, no solo los 4 alias
    `cloud-*` fijos). Reutiliza la misma clave del almacén de opencode
    (`~/.local/share/opencode/auth.json`, entrada `openrouter`) — sin clave
    nueva, sin centralizar nada. **Sale de la máquina hacia un proveedor
    externo**: la regla de no mandar datos sensibles (trabajo o personales)
    por aquí es una convención (no está forzada en código, a diferencia de
    `enrutador-ia`).
- `claude mcp get local-models` para comprobar estado (debe decir `✔ Connected`).
- No sustituye a `enrutador-ia` — es para consultas puntuales sin pasar por su
  pipeline de logging/aprendizaje ni sus guardarraíles de datos sensibles.
  Codex y Gemini siguen conectados aparte (subagentes `codex:codex-rescue` /
  `gemini:gemini-rescue`, OAuth de sus CLIs respectivas), no vía este MCP.

## Historia y racional

La auditoría completa (por qué estos modelos y no los de la conversación con MiniMax-M3, verificaciones HF/OpenRouter, riesgos) está en la conversación de Claude Code del 2026-08-01/02. Resumen: el catálogo local de v3 era de la era Qwen2.5 (2024); GLM-5.2 y MiniMax-M3 cloud eran correctos; Kimi "2M ctx" era falso (K3 = 1M); la orquestación multiagente la hace opencode/hermes + LiteLLM, no LangGraph/CrewAI.

## Historial de versiones

| Versión | Fecha | Cambio principal |
|---|---|---|
| **v5.0** | 2026-08-02 | Stack inicial: Coder-30B + 35B + 8B local; GLM-5.2 + Kimi K3 cloud; 3 perfiles (CODE/GENERAL/LIGERO) |
| **v5.1** | 2026-08-02 | Techos conservadores post-congelón; daemon LiteLLM con KeepAlive; fallbacks silenciosos eliminados |
| **v5.2** | 2026-08-05 | Careo de 3 revisores: lock atómico, daemon no fuerza perfil, lms ps fix; privacidad del log a local |
| **v5.3** | 2026-08-21/28 | MCP local-models para Claude Code; GLM-5.3 (5× menos verboso); workers R1-8B ×4; agy-bridge |
| **v5.4** | 2026-09-07 | Revisores: local-reasoner (gpt-oss-20b), local-reviewer-ms (Phi-4), local-auditor (Gemma); cloud-reasoning |
| **v5.5** | 2026-09-08/09 | Orquestador local Qwen3.6-35B → **Nex-N2-mini**; Coder-30B reemplazado por Nex en local-coder |
| **v5.6** | 2026-09-10/27 | **DOS PLANOS**: cloud orquesta, Nex protege sensible. Tripwire steps:40. Opción b RAM: solo explorador residente; Nex y R1-8B JIT. cloud-agentic = V4.1-Flash (primario opencode 01/10). data_collection:deny en todos los aliases cloud (02/10) |

El detalle de incidentes, decisiones y §§ concretos: `~/llm-stack/sistema-agentico.md`.
