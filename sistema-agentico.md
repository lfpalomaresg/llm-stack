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
| 2026-08-21 (noche) | **Kernel panic ×2 al validar `@auditor-local` de opencode en real** (22:22 y 22:49, `IOGPUFamily`/`IOGPUGroupMemory`, proceso panicado WindowServer) | ✅ **RESUELTO 22/08 por rediseño** — causa raíz: harness de opencode > gemma@8k → tormenta de reintentos y cargas JIT sobre la GPU al techo, pisando un bug conocido de `IOGPU.kext`. `@auditor-local` retirado de opencode; sensible solo por `enrutar.sh` (relevo endurecido). Historia completa: `incidente-panic-gpu.md` |

## 6. Inventario en disco (nada borrado — decisión operador 21/08)

qwen3.6-35b-a3b (20,4 GB) · qwen3-coder-30b-a3b (17,2 GB) · deepseek-r1-0528-qwen3-8b (4,6 GB) ·
qwen3-8b (4,6 GB) · gemma-4-e4b-it-OptiQ-4bit (~5 GB) · embeds (0,7 GB) ≈ **52 GB** (disco: 295 GB libres)

## 6.b Auto-delegación configurada (2026-08-21, noche)

Los tres orquestadores-software saben ya delegar solos en la escala v5.4:

| Orquestador | Mecanismo | Estado |
|---|---|---|
| **Claude Code** | skill `enrutador-ia` (`enrutar.sh`) con destinos nuevos `local-worker` y `local-auditor` | ✅ **Testado end-to-end**: worker razonó bien (180 ✓) y el auditor cazó el bug del IVA (0.21→1.21) con relevo automático |
| **opencode** | Subagente `@worker` (+ doctrina en AGENTS.md). `@auditor-local` **RETIRADO el 22/08** (causa raíz de los panics hallada y resuelta: el harness de opencode no cabe en gemma@8k → tormenta de reintentos y cargas JIT — ver `incidente-panic-gpu.md` §9). Material sensible: SOLO por `enrutar.sh`. Los alias del bridge (`gpt-oss-free`/`gemini-free`/`auditor-free`, cloud vía agy, 0 GPU) se quedan | ✅ Resuelto por rediseño: incidente cerrado sin repetir la prueba peligrosa |
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
- [x] 🔴 Investigar y resolver el kernel panic de GPU ✅ 22/08 — causa raíz hallada (escalera de 5 peldaños, sin repetir la condición peligrosa) y resuelta por rediseño: `@auditor-local` fuera de opencode, relevo endurecido en `enrutar.sh`, tapa anti-tormenta en LiteLLM. Ver `incidente-panic-gpu.md`.
- [ ] `llmfit bench` contra los modelos cargados (números medidos para contribuir/comparar) — opcional
- [ ] Una semana de rodaje del perfil AGENTE antes de plantear cualquier borrado (el 27B NO se descargó: descartado con datos antes de gastar disco)

## 8. v5.4.1 (2026-08-22) — afinado del worker + rebalanceo de papeles

**Contexto:** en las pruebas del 22/08 el R1-worker falló aritmética con el
muestreo por defecto de LM Studio (~0.8): RevPAR 93€ donde tocaba 102€, «97 no
es primo». Decisión del operador: afinar antes de sustituir (a) + rebalancear (b).

**a) Afinado aplicado y MEDIDO:**
- `temperature 0.6` + `top_p 0.95` fijados en `litellm.config.yaml` (recomendación
  DeepSeek para destilados R1; backup `.bak.20260822-r1temp`).
- Pensar POR DEFECTO para `local-worker` (exento del `/no_think` de enrutar.sh) y
  techo propio de 14k tokens (con 8k se quedaba sin espacio para la respuesta).
- **Bench 8 tareas verificables (en serie, perfil AGENTE): 7/8 de contenido
  correcto** (antes: 2 pifias en 4). Único fallo real: un modus ponens (T6).
  Debilidad que PERSISTE: no respeta formatos de salida pedidos («Concluye con
  RESPUESTA: X») — para automatizar sobre su salida, parsear con tolerancia.
  Tiempos: 9-200 s/tarea (mediana ~80 s).

**b) Rebalanceo de papeles (doctrina en 4 documentos):**
Razonar acotado NO sensible → **`gpt-oss-free`** (120B vía agy: mejor modelo,
~10 s, 0 €, **0 GPU local** — no puede tumbar el Mac). El R1 queda de titular
para material SENSIBLE y para trabajar sin red. Actualizados: JERARQUIA_IA.md
(tabla de reparto), REGLAS_ENRUTAMIENTO.md, SOUL.md de hermes (escalón nuevo,
armonizada la línea antigua que lo contradecía), AGENTS.md de opencode (con el
límite honesto: `tool_call:false` en el bridge — análisis puro sí, leer ficheros no).

**c) Sustituir el R1: SEMILLA DORMIDA.** Disparador: que falle tareas sensibles
reales durante el rodaje (las no sensibles ya no le tocan). Si dispara: candidatos
solo de editores serios, aritmética de llmfit sí / ranking no, y este mismo bench.
