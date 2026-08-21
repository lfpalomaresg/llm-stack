# LLM Stack v5 — MacBook Pro M4 Max 36 GB

> Implementado el 2026-08-02. Sustituye a `llm-stack-conversation.md` (v3/v4), que queda como histórico.
> Diseño: multiagente ≠ multimodelo — un grande caliente + un pequeño + embeddings; cloud solo por señal objetiva con techo de gasto físico.

## Arquitectura

```
opencode ─┐
hermes  ──┤──► LiteLLM proxy (localhost:4000/v1)
scripts ──┘         │
          ┌─────────┴──────────────┐
          ▼                        ▼
   LM Studio (localhost:1234)   OpenRouter (prepago SIN auto-recarga)
   único host de modelos        z-ai/glm-5.2 · moonshotai/kimi-k3 · minimax/minimax-m3
```

**Regla nº1: nadie carga modelos excepto LM Studio.** hermes desktop/CLI y opencode son clientes finos. (El desktop de hermes petaba justo por hospedar el 35B él mismo encima de la GUI.)

## Modelos

| Alias (LiteLLM) | Modelo real | RAM | Ctx cap | Rol |
|---|---|---|---|---|
| `local-coder` | Qwen3-Coder-30B-A3B MLX 4bit | ~17 GB | 80k | Coding agent (default opencode) |
| `local-general` | Qwen3.6-35B-A3B MLX 4bit (symlink a caché HF) | ~19 GB | 64k | Orquestador, chat, visión, tools (default hermes) |
| `local-fast` | Qwen3-8B MLX 4bit | ~5 GB | 32k | Utility: resúmenes, commits, clasificar |
| `local-embed` | Qwen3-Embedding-0.6B GGUF | ~0.6 GB | — | RAG |
| `cloud-coder` | GLM-5.2 ($0.42/$1.32 · 1M ctx · MIT) | — | — | Escalado: local falla tests 2× o tarea crítica |
| `cloud-coder-next` | Qwen3-Coder-Next 80B ($0.12/$0.80 · 262k) | — | — | Escalado barato (el 80B que no cabe local) |
| `cloud-megacontext` | Kimi K3 ($3/$15 · 1M ctx) | — | — | Repo entero + logs → diagnóstico |
| `cloud-vision` | MiniMax-M3 ($0.30/$1.20 · 1M ctx) | — | — | Vídeo / docs visuales pesados |

Precios verificados contra la API de OpenRouter el 2026-08-02.

## Perfiles de RAM (nunca 2 grandes a la vez)

| Perfil | Cargado | RAM aprox (con macOS ~7GB + KV) |
|---|---|---|
| **CODE** (default) | coder + fast + embed | ~33 / 36 GB |
| **GENERAL** | 35B + fast + embed | ~35 / 36 GB |
| **LIGERO** | fast + embed | ~13 / 36 GB |

## Operación diaria

**El stack arranca solo al iniciar sesión** (LaunchAgent `com.luisfran.llm-stack`,
plist en `~/Library/LaunchAgents/`, log en `~/llm-stack/launchagent.log`).
Abrir hermes/opencode directamente; estos comandos son para control manual:

```bash
~/llm-stack/stack.sh start     # arranca LM Studio + LiteLLM + perfil CODE (el LaunchAgent lo hace solo al login)
~/llm-stack/stack.sh general   # cambia a 35B multimodal (descarga el coder)
~/llm-stack/stack.sh code      # vuelta a coding
~/llm-stack/stack.sh ligero    # solo el 8B (batería / background)
~/llm-stack/stack.sh status    # qué hay cargado + salud de LiteLLM
~/llm-stack/stack.sh stop      # parar todo
```

Los TTL de 2h descargan solos los modelos inactivos (JIT). El swap CODE↔GENERAL tarda ~10-20 s.

## Archivos del stack

- `~/llm-stack/litellm.config.yaml` — alias y enrutado. **Cambiar un modelo = editar aquí, cero cambios en clientes.**
- `~/llm-stack/stack.sh` — control (arriba).
- `~/llm-stack/.venv/` — LiteLLM 1.94.1.
- `~/llm-stack/litellm.log` — log del proxy.
- `~/.config/opencode/opencode.json` — provider `llm-stack`, default `local-coder`. Backup: `.bak.20260802-005820`.
- `~/.hermes/config.yaml` — provider `llm-stack`, default `local-general`. Backup: `.bak.20260802-005820`.
- Symlink modelo 35B: `~/.lmstudio/models/mlx-community/Qwen3.6-35B-A3B-4bit → caché HF` (no duplica 18 GB; **no borrar la caché HF de este modelo**).

## Presupuesto (mecanismo anti-susto, 3 capas)

1. **OpenRouter: crédito prepagado con auto-recarga OFF** ← el techo físico real (se configura en openrouter.ai/settings/credits).
2. LiteLLM registra cada llamada en `litellm.log`.
3. Los alias `cloud-*` solo se usan por decisión explícita (nunca fallback automático desde local).

## Clave de OpenRouter (resuelto — fuente única)

`stack.sh start` lee la clave automáticamente del almacén de opencode
(`~/.local/share/opencode/auth.json`, entrada `openrouter`). No hay que exportar
nada en `.zshrc` ni duplicar la clave. Si algún día se rota la clave, basta
re-autenticar opencode (`opencode auth login`) y reiniciar el stack.

Validado 2026-08-02: ping a GLM-5.2 vía LiteLLM → "CLOUD OK" (23 in / 129 out tokens).

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

**Disciplina de perfiles (la regla de oro del usuario):**
- Sesión opencode → perfil CODE (el default del arranque).
- Sesión hermes → antes: `~/llm-stack/stack.sh general`.
- Si un agente da "insufficient system resources" → no es avería: es el guardarraíl
  diciendo que cambies de perfil con stack.sh.

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
