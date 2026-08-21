# Sistema Agéntico Local — Mac M4 Max · v5.4

> Registro canónico de la estructura agéntica sobre el LLM Stack v5.
> Creado 2026-08-21 tras la revisión con llmfit y los tests de estrés.
> Complementa (no sustituye) a `llm-stack-v5.md` (arquitectura) y
> `AI_OS/JERARQUIA_IA.md` (papeles y reglas de delegación).

## 1. Los papeles y quién los ejecuta

| Papel (JERARQUIA_IA) | Alias LiteLLM | Modelo | RAM | Techo ctx | Cuándo |
|---|---|---|---|---|---|
| **Orquestador** | `local-general` | Qwen3.6-35B-A3B (MoE, ~3B activos, visión) | 20,4 GB | **32k** en perfil AGENTE · 48k en GENERAL | Siempre que hay orquestación local |
| **Workers ×N** | `local-worker` | DeepSeek-R1-0528-Qwen3-8B (razonamiento R1) | 4,6 GB | 16k | Tareas acotadas delegadas; hasta 4 en paralelo sobre UNA carga |
| **Utility** | `local-fast` | Qwen3-8B | 4,6 GB | 24k | Commits, resúmenes, clasificar (legado; el worker R1 puede absorberlo) |
| **Coder titular** | `local-coder` | Qwen3-Coder-30B-A3B (MoE) | 17,2 GB | **32k** (bajado de 48k: es el que petó el 02/08) | Sesiones de código — perfil CODE, por swap |
| **Auditor titular** | `auditor-free`† | gpt-oss-120b (agy, gratis) → GLM-5.2 si falla | 0 GB | 1M | Revisión por defecto: gratis primero, GLM de red. Validado 3/3 con bugs sembrados (21/08) |
| **Auditor sensible** | `local-auditor` | gemma-4-E4B-it OptiQ 4bit (Google) | ~4-5 GB | 8k | Datos que no salen del Mac. Familia ≠ Qwen ⇒ cumple "revisor ≠ productor". Carga JIT |
| **RAG** | `local-embed` | Qwen3-Embedding-0.6B | 0,6 GB | — | Siempre residente |
| **Visión local** | `local-general` | (el 35B ES el modelo de visión) | — | — | Visión pesada → `cloud-vision` (MiniMax) |

† `auditor-free` es un destino de `enrutador-ia` (no de `litellm.config.yaml`): prueba
  `agy` (Antigravity CLI, plan gratuito, modelo `gpt-oss-120b-medium`) y si falla —
  no instalado, `exit≠0` o `status≠SUCCESS` — cae a `cloud-coder` (GLM) como red de
  seguridad, **siempre avisando** cuál de los dos respondió. Ver `REGLAS_ENRUTAMIENTO.md`
  de la skill para el detalle completo y la prueba de validación.

**Claves del diseño:**
- *N workers ≠ N modelos*: LM Studio sirve peticiones concurrentes (PARALLEL=4)
  sobre un único modelo cargado. Varios agentes worker golpean el mismo alias.
- El razonamiento del sistema vive en dos sitios: R1 en los workers (se atascan
  menos ⇒ menos escalados a cloud) y el 35B orquestando.
- Se evaluó y DESCARTÓ con datos (21/08): sustituir el 35B por Qwen3.8-27B denso
  — sería hasta 5× más lento (denso vs MoE); el 35B-A3B es el mejor orquestador
  posible en 36 GB. El problema real siempre fue el KV cache, no los pesos.
- **Auditor titular movido a `auditor-free` (21/08):** GLM seguía siendo el mejor
  candidato de red por fiabilidad y coste ya casi nulo, pero probar gratis primero
  no cuesta nada si el fallback queda siempre visible — mismo criterio que ya rige
  todo lo demás en este documento (nada se degrada en silencio).

## 2. Perfiles (marchas de la caja de cambios — `stack.sh`)

| Perfil | Residentes | RAM aprox | Para qué |
|---|---|---|---|
| **AGENTE** (nuevo) | 35B@32k + R1-8B@16k + embed | ~27 GB + KV | Orquestador + workers + GLM auditando: multi-agente real |
| **CODE** | coder@32k + embed (fast JIT) | ~25 GB + KV | Sesiones de código (opencode). El fast ya no es residente fijo |
| **GENERAL** | 35B@48k + fast + embed | ~33 GB | Chat/visión mono-agente (hermes clásico) |
| **LIGERO** | 8B + embed | ~13 GB | Batería / background |

Regla intacta: **nunca dos grandes a la vez** (guardarraíl de LM Studio, error visible).
Swap "por potencia": código serio → CODE · contexto gigante → Kimi · visión pesada → MiniMax.

## 3. Flujo agéntico tipo (perfil AGENTE)

```
Operador
   │
Claude Code / hermes / opencode  (orquestador-software; uno solo a la vez)
   │  GOAL + criterio de "hecho"
   ▼
local-general (35B) ── descompone y delega ──► local-worker ×1..4 (R1-8B, paralelo)
   │                                                │ resultados
   │◄───────────────────────────────────────────────┘
   ├── integra y sintetiza
   ▼
Auditor: cloud-coder (GLM) por defecto · local-auditor (gemma) si el dato es sensible
   │  [CRÍTICO]/[IMPORTANTE]/[MENOR]
   ▼
Orquestador corrige → entrega al operador
```

Escalado (peldaños intactos): local → OpenRouter (GLM/Qwen-Next/Kimi/MiniMax) → Codex/Gemini/Claude.
Solo por señal objetiva (tests en rojo 2-3×, contexto que no cabe, multimodal pesado).

## 4. Resultados del test de estrés (2026-08-21 · log: `test-estres-20260821-0045.log`)

**Escalera de contexto — 35B@32k con R1-8B@16k TAMBIÉN cargado:**

| Prompt real (tokens) | Latencia | RAM libre tras la llamada |
|---|---|---|
| 1.712 | 47 s (incluye warm-up) | 13% |
| 6.783 | 6 s | 14% |
| 13.543 | 8 s | 13% |
| 20.304 | 9 s | 17% |
| 25.374 | 8 s | 19% |

**Concurrencia real** (35B con 13,5k + R1-8B con 9k, a la vez): ambos OK.
35B en 2 s (KV caliente) · R1 en 38 s (warm-up + tokens de razonamiento —
normal en R1: piensa antes de responder). RAM libre durante la prueba: 19-26%.

**Auditor local (gemma-4-E4B OptiQ):** verificado el relevo completo —
con 35B+R1 cargados el guardarraíl de LM Studio le niega la entrada (correcto);
descargando el worker, gemma carga, **caza un bug sembrado a la primera**
(`suma()` que restaba) y devuelve el turno al worker. El relevo es la vía:
auditor local y worker comparten slot, nunca conviven.

**Veredicto: perfil AGENTE APROBADO.** Mínimo de RAM libre observado: **13%**
(~4,7 GB) — sin presión crítica, sin swap, sin congelón en toda la batería.
Los techos 32k/16k quedan FIJADOS; subirlos exige repetir esta batería.

## 5. Incidentes que moldearon este diseño

| Fecha | Qué pasó | Lección aplicada |
|---|---|---|
| 2026-08-02 | Congelón total: coder a 80k ctx → KV cache devoró la RAM | Techos conservadores; el culpable es el KV, no los pesos |
| 2026-08-21 | opencode declaraba ctx 80k/64k con modelos cargados a 48k | ✅ Resuelto la misma noche: `opencode.json` sincronizado (32k/32k/24k/16k), verificado contra el fichero real |
| 2026-08-21 | llmfit: top-10 lleno de fine-tunes de aficionado | Solo modelos con editor serio (Qwen, DeepSeek, Google, lmstudio-community) |
| 2026-08-21 (noche) | **Kernel panic ×2 al validar `@auditor-local` de opencode en real** (22:22 y 22:49, `IOGPUFamily`/`IOGPUGroupMemory`, proceso panicado WindowServer) | 🔴 **No repetir la prueba hasta investigar.** Sospecha: presión de memoria unificada de GPU al añadir `agy-bridge.py` sobre el perfil AGENTE ya cargado entero — el guardarraíl de RAM de LM Studio no cubre esto (saltó tras el 1er panic, no evitó el 2º) |

## 6. Inventario en disco (nada borrado — decisión operador 21/08)

qwen3.6-35b-a3b (20,4 GB) · qwen3-coder-30b-a3b (17,2 GB) · deepseek-r1-0528-qwen3-8b (4,6 GB) ·
qwen3-8b (4,6 GB) · gemma-4-e4b-it-OptiQ-4bit (~5 GB) · embeds (0,7 GB) ≈ **52 GB** (disco: 295 GB libres)

## 6.b Auto-delegación configurada (2026-08-21, noche)

Los tres orquestadores-software saben ya delegar solos en la escala v5.4:

| Orquestador | Mecanismo | Estado |
|---|---|---|
| **Claude Code** | skill `enrutador-ia` (`enrutar.sh`) con destinos nuevos `local-worker` y `local-auditor` | ✅ **Testado end-to-end**: worker razonó bien (180 ✓) y el auditor cazó el bug del IVA (0.21→1.21) con relevo automático |
| **opencode** | Subagentes `@worker` y `@auditor-local` (+ doctrina en AGENTS.md: escala explorador→worker→tú→escalador; revisor cloud vs auditor local). opencode habla DIRECTO con LiteLLM (nunca por `enrutar.sh`) ⇒ necesitó `~/llm-stack/agy-bridge.py` (puente HTTP en `:4010`) para que `@auditor-local` también llegue a `agy` | ✅ Configurado · 🔴 **BLOQUEADO**: la prueba real (invocar `@auditor-local`) causó 2 kernel panics de GPU la noche del 21/08 (ver §5) — no repetir hasta resolver. El smoke por `opencode run` sigue colgándose con modelos pequeños, aparte (limitación documentada el 03/08, no regresión) |
| **hermes** | SOUL.md §Delegación v5.4 (delega vía `enrutar.sh`) + alias en config.yaml | ✅ Configurado (backups .bak.20260821) · ⏳ validar en sesión real |

Hallazgos del test de delegación:
- El **guardarraíl es dinámico**: mide presión real, no cuenta modelos. Con la RAM
  reciclada admitió 35B+R1+gemma+embed a la vez (49% libre); con KV caliente lo negó.
  El relevo del enrutador (descargar pequeños antes de gemma) queda como vía
  conservadora correcta — funciona en ambos escenarios.
- Frenos intactos: cloud jamás automático · sin fallbacks silenciosos · síntesis y
  decisiones no se delegan · BLOQUEADO siempre trae instrucción, no solo error.

## 7. Pendientes

- [x] Rellenar §4 con los números del test ✅ 21/08
- [x] Perfil `agente` en `stack.sh` ✅ 21/08 (además: coder a 32k también en `start`/`daemon`; `stop` descarga el worker; los perfiles con FAST descargan al WORKER y viceversa — nunca 8B+8B)
- [x] Bajar `local-coder` a 32k en `stack.sh` ✅ 21/08
- [x] Alias `local-worker` y `local-auditor` en `litellm.config.yaml` ✅ 21/08 (verificados end-to-end)
- [x] Corregir límites de contexto en `~/.config/opencode/opencode.json` ✅ 21/08 noche (32k/32k/24k/16k, verificado contra el fichero real; backup `.bak.20260821-005635`)
- [ ] 🔴 **PRIORIDAD — investigar y resolver el kernel panic de GPU** (×2, 21/08 noche, `IOGPUFamily`) antes de repetir la prueba real de `@auditor-local` en opencode. No tocar sin plan: la config queda hecha pero sin validar en vivo.
- [ ] `llmfit bench` contra los modelos cargados (números medidos para contribuir/comparar) — opcional
- [ ] Una semana de rodaje del perfil AGENTE antes de plantear cualquier borrado (el 27B NO se descargó: descartado con datos antes de gastar disco)
