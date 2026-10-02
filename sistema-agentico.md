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
| ~~**Utility**~~ | ~~`local-fast`~~ | ~~Qwen3-8B~~ | — | — | **JUBILADO 2026-09-08** (OK operador): redundante con `local-worker` (R1-8B, mismo coste de RAM y razona mejor). Ver §15 |
| **Coder titular** | `local-coder` | Qwen3-Coder-30B-A3B (MoE) | 17,2 GB | **32k** (bajado de 48k: es el que petó el 02/08) | Sesiones de código — perfil CODE, por swap |
| **Auditor titular** | `auditor-free`† | gpt-oss-120b (agy, gratis) → GLM-5.3 si falla | 0 GB | 1M | Revisión por defecto: gratis primero, GLM de red. Validado 3/3 con bugs sembrados (21/08) |
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

### §8.b Recableado de `local-coder` (22/08 noche, OK operador) — APLICADO Y MEDIDO

El destino `local-coder` del enrutador despachaba vía `opencode run` (harness
completo) para poder tocar repos — esa vía fue la causa raíz del 4º reinicio.
Recableado a la vía RÁPIDA (curl directo a LiteLLM, mismos resolver/bloqueo/
privacidad que el resto de locales): **16 s con swap de perfil incluido** donde
antes moría a los 4 minutos. Trade-off asumido: el enrutador ya no lee/edita
repos con local-coder (material en el prompt; para repos → `codex` u opencode
como sesión). Guarda nueva en el wrapper de `.zshrc`: `opencode run -m` con
modelos <32k (fast/worker/auditor/embed) se bloquea con error visible (rc=7) —
verificada. Suite test-ram: 10/10 tras ambos cambios. `local-coder` y
`local-worker` quedan exentos del `/no_think` (uno no piensa, el otro debe pensar).

## 9. Batería 2.0 (22/08 noche) — resultado final y el veredicto sobre opencode headless

**12 de 13 escenarios en verde** tras las correcciones v5.4.1 (en serie, regla de la sala):

| Escenario | Resultado |
|---|---|
| Enrutador → 35B / fast / coder(curl) | ✅ 2,7-9,6 s |
| Enrutador → R1 afinado (razonar) | ✅ ADR 120€ correcto, 86 s |
| Workers ×2 en paralelo | ✅ 50 s total, veredictos correctos |
| **Relevo gemma (sensible)** | ✅ 14,9 s, bug IVA cazado — blindaje OK |
| MCP local-models (Claude Desktop) | ✅ |
| **Hermes elige destino por doctrina v5.4.1** | ✅ eligió gpt-oss-free solo y acertó |
| auditor-free · gemini-free · gpt-oss-free · GLM · codex | ✅ 3-47 s |
| Guarda anti-harness del wrapper | ✅ bloquea con rc=7 |
| **opencode `run` headless con primario local** | 🔴 **NO APTO — 3 ejecuciones, 3 espirales de compactación** |

**El veredicto (regla de las 3 cumplida, 3 runs medidos):**
1. `@explorador` (8B): 133 pasos explorador↔compact en 25 min, tarea trivial sin terminar.
2. `@revisor` intento 1: el PRIMARIO (coder@32k) compactó en el paso 2 de una tarea de una línea.
3. `@revisor` intento 2: 5 compactaciones en 13 pasos; @revisor llegó a trabajar (2 turnos) pero el primario vivía compactando.

**Causa estructural:** el harness de opencode (~15-30k tokens) + los límites HONESTOS
declarados en opencode.json (32k, sincronizados el 21/08 por seguridad tras el congelón
del 02/08) = el umbral de compactación se cruza casi de salida. Con límites deshonestos
no compacta… y revienta la RAM (02/08). No hay hueco: es aritmética, no un bug nuestro.
Sin errores en LiteLLM en ningún run — la espiral es invisible a las guardas anti-tormenta;
la señal de detección es `agent=compaction` repetido en su log.

**Doctrina resultante:**
- `opencode run` headless con primario local: NO APTO (el enrutador ya no lo usa para nada).
- opencode interactivo con coder@32k: válido asumiendo compactación temprana, operador mirando.
- 🌱 Semillas: (a) adelgazar el harness (desactivar tools/plugins no usados) y re-medir;
  (b) primario cloud (GLM 1M) para sesiones opencode largas — dinero, decisión operador.
- La faena barata local ya tiene vía sana: enrutar.sh por curl (2-16 s, validada hoy).

### §9.b v5.4.2 (23/08) — el adelgazamiento que revivió opencode headless

Ataque a+b sobre opencode (OK operador). Con una báscula casera (`probe-harness.py`,
endpoint señuelo que pesa el request sin tocar GPU) se midió el harness real:
**79 KB** = 59 KB de system prompt + 22 KB de tools. Dentro del system prompt,
**41 KB eran las descripciones de las 57 skills de Claude** que opencode inyectaba
desde `~/.agents/skills` (copia RANCIA del instalador iAmasters, jul/ago — 71
entradas frente a las 57 canónicas de Drive).

**Fix: `"tools": {"skill": false}` en opencode.json** → harness 79→37 KB (~10k
tokens) → el coder@32k pasa de ~11k a ~22k de aire. Validado con modelo real:

| Escenario (ayer) | Hoy |
|---|---|
| Primario coder: compactaba al paso 2, >4 min | ✅ 14,4 s, 0 compactaciones |
| @revisor: 5 compactaciones/13 pasos, kill | ✅ **REVISOR_DIJO en 15,2 s**, bug IVA + corrección |
| @explorador: 133 pasos de livelock, 25 min | ✅ **EXPLORADOR_DIJO: París en 17,2 s** |

**opencode headless: REHABILITADO** (primario coder + subagentes local y cloud).
La guarda del wrapper (primarios <32k bloqueados) SE MANTIENE — no re-testada esa
vía y el margen del 24k sigue siendo menor. El veredicto del §9 queda superado por
esta vía b); el §9 se conserva como historia del diagnóstico.
Pendiente del operador: decidir qué hacer con `~/.agents/skills` (copia rancia).

## 10. Evaluación Qwen3.8-27B + ¿actualizar la familia? (2026-08-27/28)

Pregunta del operador: ¿merece la pena Qwen3.8/4 en el stack? Evaluado con benches
propios (no blogs). **Conclusión: el stack está en su óptimo; nada que actualizar.**
Los 3 pesos del duelo se BORRARON el 28/08 (OK operador, ~54 GB liberados).

### 10.a Duelo uncensored (A/B/C) — bench idéntico, en serie
| Modelo | Calidad | Velocidad | Refusals negocio |
|---|---|---|---|
| A · JonathanColetti Q5 GGUF (Heretic) | 8/8 | 13,2 tok/s | 5/5 responde |
| B · orcarouter 6-bit MLX | 8/8 | 14,1 tok/s | 5/5 responde |
| **C · oficial mlx-community 4-bit** | 8/8 | **19,4 tok/s** | 5/5 responde |

**Hallazgos:** (1) Qwen3.8 base es **muy poco censor** — el oficial respondió a los 5
casos de negocio Y a un test discriminante (insultos de rap). El uncensored NO desbloquea
nada para uso hotelero legítimo. (2) La abliteración **cuesta ~30% de velocidad** (pesos
modificados razonan peor). (3) El oficial C gana a A y B en TODO lo medido. Provenance:
JonathanColetti (Heretic+PPL honesta) > orcarouter (marketing) > huihui. **Ninguno se
integró.** El descarte del 21/08 (denso = lento) queda reforzado: 13-19 tok/s vs los MoE.

### 10.b Nicho de C (oficial) — medido, NO integrado (semilla)
- **Contexto largo**: RAM CUMPLE (32-37% libre a 27k tokens → KV híbrido barato real,
  cabría 64-128k), pero prompt-processing **160 tok/s = lento** (128k ≈ 13 min de ingesta).
  Único nicho real = contexto largo de material SENSIBLE (que no puede ir a Kimi cloud).
  El operador lo despriorizó.
- **Visión imagen**: EMPATA con el 35B (ambos leyeron un gráfico con los 3 % exactos).
  No aporta. **Vídeo**: LM Studio no lo sirve por API → no viable en el stack.
- Veredicto: C no justifica integración. Semilla con disparador (si aparece necesidad
  real de contexto-largo-sensible, los pesos se rebajan en 5 min).

### 10.c ¿Actualizar la familia Qwen? Censo oficial (HF, namespace Qwen)
- **NO existe Qwen4** (solo experimentales `qwen4_exp`: Flash-Next **180B** — no cabe).
- **Serie 3.8 no tiene MoE de talla 36 GB**: solo el 27B denso (lento, descartado) y
  gigantes cloud (2.4T-A95B). Alibaba no sacó un «3.8-35B-A3B».
- **Orquestador Qwen3.6-35B-A3B (abril 2026)**: lo mejor que existe para 36 GB. No tocar.

### 10.d Bench coder-30B vs 3.6-35B (ambos ya en disco) — LA LECCIÓN
6 tareas de código con **verificación ejecutable** (`bench-coder.py`, reusable):
| | Coder-30B (2025) | 3.6-35B (2026) |
|---|---|---|
| Corrección | **6/6 PASS** | **6/6 PASS** |
| Tokens/tarea | **81** | **1.809** |
| Tiempo/tarea | **~1 s** | **9-23 s** |

Empatan en inteligencia, pero el coder-30B entrega el código **~15-20× más rápido** porque
es *instruct puro sin cadena de pensamiento* — va directo. El 35B «razona» 1.809 tokens
para una función de 5 líneas. **El coder viejo es INSUSTITUIBLE por diseño**: actualizarlo
al 35B empeoraría la experiencia de código (mismo resultado, 20× más lento). La antigüedad
no importa cuando el diseño (instruct directo) es el correcto para el papel.

**Veredicto global:** stack en punto óptimo. Cada modelo está donde debe (el orquestador
piensa, el coder ejecuta directo). El próximo salto real será Qwen4 estable — reevaluar
entonces. Hasta ahí, no actualizar nada.

## 11. v5.4.3 (2026-08-28) — cloud-coder: GLM-5.2 → GLM-5.3 (duelo cloud a 4)

Traído por el operador: Nex-N2-Pro (397B, nex-agi, derivado de Qwen3.5) y GLM-5.3.
Ninguno cabe local (397B/743B) — son de la capa cloud. Bench propio de código con
**verificación ejecutable** (`bench-coder-or.py`, vía OpenRouter, 6 tareas):

| Modelo | Calidad | tok/tarea | vel | Precio out/M | **Coste/tarea** |
|---|---|---|---|---|---|
| GLM-5.2 (era el titular) | 6/6 | 691 | 121 t/s | $3,74 | **2,584 m$** (el peor) |
| **GLM-5.3** ← nuevo titular | 6/6 | **145** | 90 t/s | $4,40 | 0,638 m$ |
| **GLM-5.3-Flash** ← nuevo `cloud-coder-flash` | 6/6 | 271 | 61 t/s | $0,25 | **0,068 m$** (rey del valor) |
| Nex-N2-Pro | 6/6 | 197 | 93 t/s | $1,00 | 0,197 m$ |

**Hallazgos:** (1) Todos 6/6 en tareas medias → el bench no discrimina CALIDAD aquí;
la ventaja de GLM-5.3 en código duro (81 Terminal-Bench) no se ve, solo su eficiencia.
(2) **El precio/token engaña; manda el coste/tarea = precio × tokens usados.** GLM-5.3
cobra más por token pero es ~5× menos verboso (145 vs 691) → **4× MÁS BARATO por tarea
que GLM-5.2** Y más potente. (3) GLM-5.2 era el PEOR de los cuatro (precio alto +
verboso). Corrige mi afirmación previa «GLM-5.3 es 3× más caro» — medido, es 4× más barato.
(4) Nex-N2-Pro no gana en ningún eje (Flash lo bate en coste, GLM-5.3 en potencia).

**Aplicado:** `cloud-coder` → `openrouter/z-ai/glm-5.3`; nuevo alias `cloud-coder-flash`
→ `glm-5.3-flash` (escalón ligero, 38× más barato que el viejo GLM-5.2). Backup
`litellm.config.yaml.bak.20260828-glm53`. Doctrina actualizada en opencode.json,
JERARQUIA_IA.md, REGLAS_ENRUTAMIENTO.md. Ambos aliases verificados con llamada real.
Frontera de datos intacta: cloud = solo escalado NO sensible. Báscula: `bench-coder-or.py`.

## 12. Visión local sin atranques — vision-local.py (2026-08-30)

hermes entró en bucle de reintentos analizando imágenes. **Causa real: el NÚMERO de
imágenes, no el tamaño** — pasar ~8 capturas (pequeñas, 1008×511) en una sola petición
satura el contexto del 35B (cada imagen se trocea en tiles → decenas de miles de tokens →
rebasa 32k → timeout → reintenta). Una imagen sola se lee en ~6 s. Diagnóstico inicial
(imágenes «grandes») refutado al medir las dimensiones reales.

**Fix: `~/llm-stack/vision-local.py`** — procesa DE UNA EN UNA (una petición por imagen) +
redimensiona a MAXPX (1568) antes de enviar. Default `local-general` (35B, LOCAL → apto para
revenue/datos sensibles). Validado con 2 tablas de revenue reales: leídas bien, 10,9 s, sin
atranque. hermes aprende la vía en su SOUL.md (§Imágenes): nunca mandar imágenes crudas al
modelo. Nota operativa: pausar el gateway de hermes exige `launchctl disable`+`bootout` (tiene
KeepAlive; matar el PID no basta) — reactivar con `enable`+`bootstrap`.

## 13. Evaluación de vídeo/agénticos (LTX-2.5, MiniMax H3, Muse Glimmer) — 2026-08-30

Tres modelos evaluados con puerta de viabilidad ANTES de descargar (M4 Max 36 GB, ~59 GB disco).
Solo uno era testable en local; los otros dos, descartados por hardware/licencia sin bajar nada.

### 13.a LTX-2.5 (vídeo, Lightricks) — NO VIABLE EN LOCAL
22B DiT vídeo+audio, open-weights. En Mac: pico ~50 GB RAM (tienes 36), bf16 ni cabe en disco,
**sin port MLX para 2.5** (solo 2.3), y **bugs graves de MPS** (falla por nº de frames >65536 out
channels; VAE de audio da NaN/Inf). Gratis = solo la LICENCIA (comercial libre si facturas <10 M$),
NO la ejecución: habría que pagar GPU alquilada (Runpod) o API. Veredicto: solo cloud, no Mac.

### 13.b MiniMax H3 / Hailuo 3.0 (vídeo) — NO-GO (hardware + LICENCIA)
33B denso difusión, 15 s 2K + audio. Combo mínimo ~37 GB pesos → desborda 36 GB; ComfyUI, no
LM Studio, sin MLX. 🚨 **Su licencia de pesos abiertos EXCLUYE la UE** (y UK/Corea/EEUU) → en
España, descargar los pesos queda fuera de licencia. Única vía limpia: API (`minimax/hailuo-3`
en OpenRouter, ~$0,13/s a 2K → ~1,30$/10 s). No compite con el stack de texto.

### 13.c Muse Glimmer (Meta, agéntico) — TESTADO, semilla (bloqueo de ecosistema)
~29,6B denso, multimodal entrada (texto+imagen), Apache-2.0. GGUF Q4_K_M 16,8 GB + mmproj visión
(`lmstudio-community/Muse-Glimmer-30B-GGUF`). Cargó bien (8,4 s, 16,9 GB, 16K ctx, ~20 tok/s).
**El modelo es capaz:** silogismo correcto, JSON exacto, y en tool-calling **eligió la función y
args correctos**. PERO usa protocolo propio **ATEM** (canales `to=self`/`to=<tool>`) y el runtime
de LM Studio (llama.cpp 2.29.1) **NO lo parsea** → por la API estándar el razonamiento se filtra
como texto y las tool_calls NO salen en el campo `tool_calls` (quedan como `<atem:invoke>` crudo).
Como TODO el stack consume por la API OpenAI (LiteLLM→enrutador→hermes), su función estrella es
inservible hoy sin un shim ATEM→OpenAI. Extra: "piensa mucho" (razonamiento largo tipo R1).
**Veredicto: NO integrar; 🌱 SEMILLA.** Disparador: cuando LM Studio (llama.cpp/MLX) añada parseo
ATEM (como pasó con gpt-oss "harmony"). Pesos BORRADOS (17 GB liberados; re-descarga en ~5 min).

## 14. Revisión de entorno agéntico con el operador — 2026-09-06

### 14.a Fix aplicado: orquestador restaurado
`local-general` apuntaba a `qwen3-8b` (drift de una edición intermedia); el 35B orquestador
quedó huérfano sin alias. **Restaurado a `qwen3.6-35b-a3b`** y verificado por `/model/info`.
Backup `litellm.config.yaml.bak.20260906-general35b`. Commit `f782ceb`.
Nota: el 35B tiene modo *thinking* activo (razona ~500 tokens antes de responder).

### 14.b Roster local — confirmado ÓPTIMO para 36 GB (investigación sept-2026)
Nada bate al 35B-A3B (orquestador+visión) ni al Coder-30B-A3B dentro de 36 GB. Los sucesores
reales no caben: Qwen3-Coder-Next (44,8 GB @4bit + ~2× lento), GLM-4.6/5 (357-744B server),
MiniMax-M2/Ling/Ring (server). **Qwen4 NO ha salido** (solo preview 125B-A6B, pide 256 GB).
El próximo salto real = Qwen4 estable. Mantener el núcleo.

### 14.c Altas locales APROBADAS (pendiente descargar + medir)
- **gpt-oss-20b** (MXFP4 ~12 GB, MLX+GGUF): 2º worker de razonamiento agéntico/tool-use (clase
  o3-mini, GPQA/AIME fuertes). **NO reemplaza al R1-8B** — R1 sigue para el fan-out ×4 matemático
  (4,6 GB, mejor para paralelo); gpt-oss para razonamiento pesado. Coexisten.
- **local-uncensored** = `mlx-community/Josiefied-Qwen3-30B-A3B-abliterated-v2-4bit` (MLX ~17 GB,
  MoE): abliterado, carga JIT bajo demanda (nunca residente). Uso local sin freno (frontera intacta).
  Alternativas: mlabonne (GGUF, provenance de referencia) · huihui-2507 (GGUF, base más nueva).

### 14.d Mejoras CLOUD APROBADAS (pendiente editar litellm.config.yaml)
Precios verificados en vivo (API OpenRouter, sept-2026). El campo chino corre 3-20× más barato
que Claude/GPT/Gemini para capacidad comparable.
1. 🔴 **cloud-megacontext: Kimi-K3 ($3/$15) → `deepseek/deepseek-v4-pro` ($0.627/$1.254, 1M ctx)**
   — ~12× más barato, razona+codifica. Kimi-K3 es la opción de 1M MÁS CARA del tablero; queda solo
   como techo multimodal duro (alias aparte o nota).
2. 🟢 **Añadir `cloud-reasoning` = `deepseek/deepseek-v3.2` ($0.269/$0.40)** — hueco de razonamiento/
   mates, valor brutal. Tier pesado = deepseek-v4-pro o qwen3-max-thinking.
3. 🟢 **Añadir coder de valor = `deepseek/deepseek-v4-pro`** como default barato de escalado; GLM-5.3
   (`cloud-coder`) queda solo para lo más duro. cloud-coder-flash / -next / -vision se MANTIENEN.
4. 🇪🇺 **Europeos: NO por OpenRouter** (pierde en precio/calidad vs chinos, y la soberanía UE —único
   argumento— OpenRouter no la da: enruta a terceros USA). **Semilla:** Mistral La Plateforme UE
   directo (DPA, residencia UE) como capa intermedia para dato SEMI-sensible, alias aparte NO-OpenRouter.

**Estado:** aprobado por el operador 2026-09-06. Pendiente de aplicar (local: descargar+medir; cloud:
editar config) — se hace al cierre de la revisión, tras el Bloque D (diseño careo dos capas).

### 14.e IMPLEMENTADO — 2026-09-07 (modo autónomo, OK operador)
- **Cloud aplicado** (litellm.config): cloud-megacontext→deepseek-v4-pro · +cloud-megacontext-max
  (kimi techo) · +cloud-coder-value (v4-pro) · +cloud-reasoning (deepseek-v3.2). Verificado /model/info.
- **Modelos locales bajados y validados en vivo:** gpt-oss-20b (`local-reasoner`), Phi-4-reasoning-plus
  (`local-reviewer-ms`), Josiefied-Qwen3-30B-A3B abliterado (`local-uncensored`). Los 3 cargan y
  responden por su alias. Granite-4-h-tiny SALTADO (se atascaba en HF; opcional, Gemma cubre el rol).
- **Careo dos capas IMPLEMENTADO:** `careo-local.py` + Paso 0.5 en la skill. **Validado con dogfood**:
  gpt-oss(13s)+Phi(45s) cazaron 2/2 un ZeroDivisionError plantado + el test vacío. Capa 1 funciona.
- Backups: litellm.config.yaml.bak.20260907-{deepseek,reviewers} · .bak.20260906-general35b.
- Pendiente menor: subir max_tokens de Phi en careo-local.py (es muy verboso). Bench formal gpt-oss
  vs R1 como 2o worker (validado cualitativo: responde y revisa bien; falta el número).

## 15. Consolidación del entorno + arquitectura del orquestador — 2026-09-08 (OK operador)

**Problema raíz diagnosticado:** hermes arrancaba en `local-general` (35B, 20,4 GB) y opencode en
`local-coder` (Coder-30B, 17,2 GB). 20,4+17,2 = **37,6 GB > 36** → nunca caben juntos; cambiar de
herramienta forzaba un swap de un modelo grande (1-2 min) y rozaba la regla de la sala.

**Arquitectura decidida — UN solo cerebro local compartido:**
- **Orquestador único = 35B** (`local-general`), compartido por hermes **y** opencode. opencode
  recableado de `local-coder`→`local-general` (`~/.config/opencode/opencode.json`). Así solo hay
  **un grande residente a la vez** sea cual sea la herramienta; el swap ocurre al cambiar de *tarea*
  (orquestar↔codear duro local), no de *herramienta*.
- **Coder-30B pasa a swap JIT bajo demanda** (como los revisores), no residente por defecto.
- **"Segundo coder en paralelo" = CLOUD** (`cloud-coder-value` = DeepSeek-V4-Pro, 0 GB RAM local,
  ~$0.62/$1.23 M). Ningún coder local grande cabe junto al 35B → el paralelo real es cloud, salvo
  **código sensible** (frontera): ahí se acepta el swap al Coder-30B local.
- **Descartado** Claude/obliterated como orquestador permanente: Claude rompe la frontera con dato
  sensible Soho; Josiefied (17,2 GB, mismo problema de RAM y peor seguimiento de instrucciones por
  la abliteración) se queda en su papel de uncensored/red-team bajo demanda.

**Mito corregido:** montar el 35B permanentemente NO preserva "el hilo" de las tareas — el contexto
se reenvía entero en cada petición; el hilo vive en el CLIENTE (historial de hermes/opencode/Claude
Code), no en la RAM del modelo. Montar solo ahorra latencia de recarga.

**Cambios aplicados:**
- **`local-fast` (Qwen3-8B) JUBILADO** de litellm + opencode + hermes; descargado de RAM (−4,6 GB).
  Redundante con `local-worker` (R1-8B). 19 aliases activos (antes 20). Backup `.bak.20260908-retire8b`.
- **Careo dos VELOCIDADES + grupos de carga** (`careo-local.py` reescrito). Verdad de RAM medida:
  dos revisores medianos (~20 GB) NO caben con el 35B residente → el careo **evicta el 35B**
  (`lms unload --all`) antes de la pasada. `rutina` = gpt-oss+Gemma (16 GB) · `duro` = gpt-oss+Phi
  (20 GB) · `--red-team` = Josiefied en pasada SERIE (evicta el par antes). El 35B sale del rol de
  revisor rutinario. **Verificado en vivo** (2:04, `--duro --red-team`): gpt-oss 20s + Phi 85s = 2/2
  + Josiefied 13s ✅; el HTTP 400 de RAM que salía antes con el 35B residente DESAPARECIÓ. max_tokens
  de Phi subido a 3000 (ya no se corta). Bug `\n` literal corregido.

**hermes — limpieza (mantenido por decisión del operador, unificado al 35B):**
- **WhatsApp desactivado** (`.env WHATSAPP_ENABLED=false`): estaba activado-sin-emparejar y metía al
  gateway en bucle de caída (`non-retryable startup conflict`). Gateway ahora ESTABLE.
- **Telegram auto-responder desactivado** (`config.yaml platforms.telegram.enabled=false`): cada
  mensaje entrante disparaba el 35B (era parte del "auto-disparo" sorpresa). Reactivar poniendo true.
- **3 crons de radar de competencia Soho re-PAUSADOS** (Málaga/Granada/Ronda): estaban ACTIVOS y
  disparándose a diario a las 09:00 **contra la orden** de crons pausados desde 22/08. Eran la ráfaga
  que martilleaba el 35B. Pendiente decisión del operador: reactivarlos (revenue management) o dejar.
- ⚠️ Token del bot de Telegram en plaintext en `~/.hermes/gateway_state.json` — revocar en @BotFather
  si el bot ya no se usa.
- Backups: `config.yaml.bak.20260908-unify-notelegram` · `.env.bak.20260908` · `opencode.json.bak.20260908-unify35b`.

### §15.a Simplificaciones + accionables 360 (misma sesión 08/09, OK operador)
- **qwen3-8b BORRADO del disco** (4,3 GB liberados) y `stack.sh` `FAST="$WORKER"` → un solo 8B en
  todo el stack (R1-8B) en CODE/GENERAL/LIGERO. Cruce anti-8B+8B retirado (ya no aplica). test-ram 10/10.
- **cloud-coder-next (Qwen3-Coder-Next 80B) RETIRADO** (apenas usado; V4-Pro cubre el escalado barato).
- **gemini-free RETIRADO** (fiabilidad 25% en el log; auditor-free+gpt-oss-free bastan). → **17 aliases**.
- Etiqueta `cloud-megacontext` corregida en opencode.json (Kimi→V4-Pro).
- **Guard de crons de hermes** (`guard-hermes-crons.sh` + LaunchAgent `com.luisfran.hermes-cron-guard`,
  diario 09:30 + al arrancar): avisa por notificación si algún cron aparece ACTIVO contra la pausa.
- **careo-local.py RECALIENTA** el grande previo (35B o Coder-30B) al terminar, en background —
  vuelves al trabajo sin esperar la recarga. `--no-rewarm` para desactivarlo.
- **mejora stack.sh 09-03 (TTL por perfil + recarga si ctx/ttl no coinciden) es GENÉRICA** (aplica al
  35B/Coder/R1-8B, no al 8b jubilado) → commiteada aquí. Backups `.bak.20260908-simplify` (litellm).

### §15.b Escaneo de orquestadores (2026-09-08) — un único candidato a batir el 35B
Regla: ≤ ~22 GB de pesos 4-bit + holgura ⇒ total ≤ ~40-44B. Toda la ola 2026 potente (Qwen4-preview
= Qwen3.8-Flash-Next 125B-A6B ~90 GB, GLM-4.5-Air 106B ~53 GB, MiniMax/Ling/Ring flash >100B, Kimi
frontier) **NO CABE**. Qwen4 estable **no existe** aún. La franja 30-40B-MoE que cabe la monopoliza
la propia familia `qwen3_5_moe`. **Único candidato con expectativa real de mejorar el orquestador:
`Nex-N2-mini` (35B-A3B, `nex-agi`, jun-2026)** — MISMA arquitectura y footprint que el 35B (~20 GB,
multimodal, MLX 4-bit + MTP disponible) pero **post-entrenado para AGENTES** (SWE-Bench 74,4 ·
Terminal-Bench 60,7 · tool-use en bucle). Es un upgrade de *fineup*, no de talla → coste RAM idéntico.
Ya estaba anotado como semilla el 28/08; ahora priorizado a benchar cara a cara vs el baseline. Si no
mejora en careo real, el 35B sigue siendo el óptimo (resultado válido).

## 16. Nex-N2-mini SUSTITUYE al 35B como orquestador + principio CANÓNICO — 2026-09-09 (OK operador)

**PRINCIPIO CANÓNICO (nuevo, rector del stack):** lo que define este stack NO son los modelos, es el
**reparto de ROLES** (orquestador, coder, workers, revisores, red-team, RAG). Cada rol se sirve por un
**alias LiteLLM**; el MODELO que lo cumple es **ENCHUFABLE** — cualquier frontera (local o cloud: Claude,
GPT, Gemini, DeepSeek, o un local nuevo) entra repuntando su alias, cero cambios en los clientes. La
arquitectura no depende de ningún modelo concreto. Esto se demostró cambiando el orquestador con una línea.

**Bench VS (Nex-N2-mini vs Qwen3.6-35B), mismos prompts de orquestación:**
- **Descomposición/delegación:** Nex da lista limpia con agente por paso (5,5s); el 35B **volcó "thinking
  process"** y se quedó sin presupuesto sin dar la respuesta.
- **JSON estricto:** Nex JSON válido sin preámbulo (2,2s); el 35B thinking-dump, no produjo el JSON (2/3
  fallos, incluso con `/no_think` — este build MLX lo ignora).
- **Razonamiento (RevPAR):** ambos correctos; Nex directo, 35B verboso.
- **Velocidad ~90 t/s ambos · RAM 20,4 GB ambos** (misma arquitectura qwen3_5_moe, mismo footprint).
- **Veredicto:** Nex gana como orquestador (salida directa, obediente, formato estricto, agentic-tuned:
  SWE-Bench 74,4 · Terminal-Bench 60,7). El thinking-dump del 35B era la fricción real del operador.

**Sustitución aplicada (todo lo que apuntaba al 35B → Nex):**
- `litellm.config.yaml`: `local-general` → `openai/nex-n2-mini-local`. **+alias `local-35b`** (→ el 35B,
  conservado en disco para revertir/comparar). Revertir = repuntar local-general a qwen3.6-35b-a3b.
- `stack.sh`: `GENERAL="nex-n2-mini-local"` + textos de perfil. test-ram **10/10**.
- `careo-local.py`: `GRANDES` incluye `nex-n2-mini-local` (el recalentado post-careo lo repone).
- `enrutar.sh` (scripts/): `GENERAL_ID` → nex · `FAST_ID` → R1-8B (arreglado: apuntaba al qwen3-8b borrado)
  · nombres cloud stale corregidos (glm-5.2→5.3, kimi-k3→deepseek-v4-pro en el fallback directo).
- `opencode.json`: etiqueta del orquestador. hermes/opencode/enrutar **siguen automáticamente** por usar el
  alias `local-general` (la indirección de alias ES lo que hace el stack model-agnostic).
- `local-fast` RE-AÑADIDO como alias → **mismo R1-8B** (un solo 8B físico; enrutar.sh lo usa de degradado).
  → 19 aliases.
- **Descarga de Nex:** HF rate-limitó vía `lms get` (atasco en 1 shard). Resuelto: bajado el shard con
  curl directo al CDN (30 MB/s vs 1), y como `lms get` no reconoce el shard curl (Xet), se **registró
  renombrando la carpeta** (rompe el estado "downloading" de la DB de LM Studio). Carga en 12,4s, responde.

**#5 — sets de modelos por operación y swapping (medido 09/09, todos caben, cero OOM):**
| Set | Modelos | Carga | RAM libre | Swap |
|---|---|---|---|---|
| AGENTE | Nex@32k + R1-8B | 10,7+6,1s | 35% (el más apretado) | +6 GB |
| CODE | Coder-30B + R1-8B | 5,9+4,7s | 45% | — |
| CAREO duro | gpt-oss + Phi | 7,0+4,4s | 52% | — |
| RED-TEAM | Josie sola | 6,5s | **68% (el más holgado)** | 0 |
| unload --all | — | **2,2s** | — | — |
- **Corrección medida:** un swap completo (evicción 2s + cargar grande ~10s) = **~12s, NO 1-2 min** como
  se estimaba. La fluidez real entre operaciones es de segundos. El AGENTE es el techo (TTL-30min lo cubre);
  Josie el suelo (auditoría de seguridad = el uso que MENOS estresa la RAM → el `tool-code-audit` no petará).

## 17. v5.6 — El pivote: dos planos, un solo grande, salto consciente — 2026-09-10 (OK operador)

**Incidente que lo desencadena:** opencode con Nex de primario corrió **17,5 h en una tarea, ~3.000
pasos, `agent=compaction` cada minuto** — espiral de compactación. Cero resultado. **No era Nex** (el
35B haría lo mismo o peor): la tarea desbordó los 32k del modelo local y opencode compactó sin fin.
**Lección de fondo:** un modelo local de 20 GB en 36 GB NO sostiene bucles agénticos sin tope.
Local = tareas ACOTADAS. Lo grande → nube, por decisión.

**Dos hallazgos previos que sí eran Nex, ya resueltos:** (a) Nex razona en voz alta por defecto y
opencode no inyecta `/no_think` → fix CENTRAL en el `chat_template.jinja` del modelo (default
`enable_thinking` → false): prompt 14k de 27s→2,4s caliente, directo (`NEX-NOTHINK-FIX.md`).
(b) Los wrappers `.zshrc` disparaban "¿desalojar el otro?" con `pgrep hermes` (gateway 24/7 → siempre
true): ahora solo preguntan si hay OTRO grande distinto de Nex cargado de verdad.

**Arquitectura resultante (dos planos):**
- **ORQUESTACIÓN** (nube, 0 € al margen): **Claude Code CLI = orquestador formal** (por suscripción,
  no API), Codex, y opencode como UI de código. Conducen; NO ingieren dato sensible.
- **DATOS** (local, frontera): **Nex, único grande residente** (AGENTE: Nex@32k + R1 workers + embed
  ≈ 25 GB fijo); revisores (gpt-oss/Phi/Gemma) y Josie JIT en serie. Ya no hay swaps grande↔grande.
- **Salto consciente a la nube:** en opencode, agente primario **`dpsk`** (Tab, conserva historial) o
  alias de terminal `dpsk` (arranca directo en V4-Pro sin cargar Nex). **Nunca automático** — un salto
  automático filtraría datos sensibles sin que nadie lo decida. Es decisión del operador, por tarea.
- **Ley de frontera para la nube:** Claude/Codex/opencode-cloud orquestan; lo sensible va a Nex vía
  `SENSIBLE=1`, nunca al contexto de la nube.
- **Careo 0 €:** local → gratis nube (`auditor-free`) → Codex (suscripción). Solo Gemini cuesta.

**Retiros:** Qwen3.6-35B (orquestador anterior) y Coder-30B (su hueco, código sensible acotado, lo cubre
Nex agentic-tuned). `local-coder` → alias a Nex (red de seguridad); `stack.sh code` → redirige a agente;
`CODER_ID`→Nex en enrutar; GRANDES y helper `.zshrc` limpios. test-ram **10/10** con 3 tests
reescritos a la realidad de un solo grande. Libera ~35 GB.

**Decisión sobre visión:** Nex (VLM) para visión ligera + `cloud-vision` (MiniMax) para pesada. La visión
de Nex NO está benchada — no se afirma que sea la mejor; mini-bench pendiente si la visión se vuelve diaria.

## 18. Opción b — explorador residente, R1-8B y Nex bajo demanda — 2026-09-15/16 (OK operador)

**Disparo:** `opencode` no abría desde el terminal ("No se pudo preparar el perfil"). Causa medida en
el log de LM Studio (15/09 23:06:09, guardarraíl "insufficient system resources"): el wrapper `.zshrc`
cargaba Nex (20 GB) en cada arranque aunque el primario ya era DeepSeek-V4-Pro, y con el
`qwen/qwen3.8-27b` del bot de Telegram en RAM (16 GB, añadido ese día desde otra sesión) no cabía.
Ni la guarda del `.zshrc` ni `_perfil` conocían ese modelo → ni preguntaban ni lo desalojaban.

**Decisiones del operador:** (1) Nex solo como subagente `@nexn2`: en disco, JIT. (2) Borrar el 27B
(movido a la Papelera). (3) `@explorador` vuelve a tener un modelo SIN razonamiento: desde el 08/09
`local-fast` apuntaba al R1-8B del worker (razona). Elegido **Qwen3.5-9B MLX 4-bit**: familia `qwen3_5`
como Nex (soporte LM Studio probado), mismo formato de tool-call `<function=…>`, 32k, ~6 GB, plantilla
no-think (`QWEN35-9B-NOTHINK.md`, parcheada en `chat_template.jinja` y en `tokenizer_config.json`).
(4) **Opción b de RAM:** residente solo el explorador; R1-8B y Nex JIT (LM Studio releva un JIT por
otro → nunca coinciden los tres y Nex siempre cabe). Descartadas: a) 9B + R1 fijos (Nex no cabe sin
orquestar descargas); c) 9B también como worker con thinking (sin verificar que LiteLLM pase
`enable_thinking`).

**Cambios:** `stack.sh` (`_desalojar_intrusos`: intruso = LLM fuera de FAST/WORKER/GENERAL, con FORCE
se descarga y sin FORCE exit 5 nombrándolo; `_cargar` con ttl=0 = residente; `agente`/`ligero`/
`start`/`daemon` sin Nex; `general` Nex a 32k) + `test-perfil-intrusos.sh` (rojo 5 fallos → verde);
`litellm.config.yaml` local-fast → `qwen3.5-9b-mlx`; `enrutar.sh` FAST_ID + worker 24k/TTL 30 min;
`.zshrc` `_llm_asegura_explorador` (opencode/hermes abren siempre, avisan si el explorador no está);
bot de Telegram → alias `local-fast` vía LiteLLM (`.env`); agentes opencode (`nexn2` ya no invoca a
`@worker`: le desalojaría), `AGENTS.md` v6.1 y `SISTEMA.md` v1.2.

**Lección:** un cliente que llama a LM Studio con un modelo fijo (el bot) se salta el principio
canónico de aliases y rompe el reparto de RAM. Todo cliente local → alias LiteLLM, nunca modelo.

**Addendum 2026-09-16 — medido en caliente, no estimado.** (1) **El relevo JIT funciona**: al pedir
`local-general` por LiteLLM, LM Studio desalojó solo el R1-8B que había entrado JIT
(`unloadPreviousJITModelOnLoad`). (2) **Nex NO cabe con el explorador residente**: con solo el 9B
cargado (5,6 GB) y el **65 % de la RAM libre**, el guardarraíl (modo `high`, umbral 4 GiB) rechazó
Nex (20,4 GB) — «Model loading was stopped due to insufficient system resources». El relevo
automático solo ocurre entre modelos JIT y el explorador lo carga `stack.sh`, así que nadie lo
desalojaba. **Fix:** `stack.sh general` descarga el explorador antes de cargar Nex y lo dice en su
mensaje (`stack.sh agente` lo recupera); test 6 de `test-perfil-intrusos.sh`, rojo visto primero.
Documentado en `SISTEMA.md` §1.3/§2.3/§5.2/§8.3, `AGENTS.md` y `agent/nexn2.md` para que
DeepSeek no lo lea como avería. (3) **Contexto por modelo de los JIT** fijado en
`~/.lmstudio/.internal/user-concrete-model-default-config/` (Nex 32k, R1 24k, 9B 32k): antes todos
caían al default global de LM Studio (24k). Ese directorio vive fuera de git — re-crear si se
reinstala LM Studio.

**Addendum 2026-09-25 — limpieza de referencias muertas y deriva de la opción b (OK operador).**
(1) `stack.sh`: eliminada la variable `CODER` (Coder-30B borrado el 10/09) y sus cuatro usos;
`careo-local.py`: `GRANDES` solo con Nex (35B borrado). (2) **Bug real de la opción b:**
`stack.sh code` redirigía a AGENTE, que desde el 15/09 ya no carga Nex, y `enrutar local-coder`
devolvía un Nex que el JIT no podía cargar con el explorador residente (guardarraíl). Ahora
`code` → GENERAL y `enrutar local-coder|local-general` llaman a `stack.sh general` directo.
(3) `enrutar.sh` y `careo-local.py` leían `lms ps` en texto por columnas — el mismo parseo
que rompió `stack.sh` el 14/09 por los códigos ANSI — y pasan a `lms ps --json`.
(4) `careo-local.py`: tras `unload --all`, si no había grande repone el explorador residente
con `stack.sh agente` (antes lo dejaba muerto para @explorador y el bot). (5) `test-ram.sh`
(enrutador) llevaba 10 días con 4 FAIL de deriva: mock de `lms` sin `--json`, `FAST` copiado a
mano (R1-8B) y tests que esperaban AGENTE con Nex. Ahora el mock habla JSON con ctx/ttl/status,
los ids se leen del propio `stack.sh` y los casos 1-3 codifican la opción b. **11/11** y
`test-perfil-intrusos.sh` **8/8**. Backups `.bak.20260925-*` junto a cada fichero.

## 19. Evaluación Qwen-Image-2.1 (7B + encoder Qwen3-VL-8B) — 2026-09-25 · NO ENTRA (licencia)

**Qué es:** sucesor del Qwen-Image 20B (20/09/2026). DiT de **7B / 32 capas de flujo único** que unifica
generación y edición; **RGBA nativo**, 2048² nativo, hasta 10 imágenes de referencia, edición por máscara.
**Encoder obligatorio: Qwen3-VL-8B** (el DiT está entrenado contra sus embeddings; no se cambia). Pesa más
que el generador: bf16 17,5 GB (DiT 14,2 · VAE 0,7 → 33 GB, no cabe en 36 GB); int8 9,4 GB; w4a8 6,3 GB.
DiT en GGUF (unsloth) Q8 7,6 GB · Q4_K_M 4,2 GB. Reescritores PE-T2I/PE-I2I (Qwen3.5-9B, 9,5 GB int8) opcionales.

**En un Mac de 36 GB (bench ajeno, M5 Max 36 GB, ComfyUI ≥0.36 + ComfyUI-GGUF sobre MPS):** Q8+int8 → pico
14 GB a 1024px, **156 s/imagen a 40 pasos**, ~18 min a 2048²; Q4+w4a8 → 11 GB, 218 s. Calidad Q8 44/50 vs Q4
40/50 (logos y contraste de texto). Edición con 2 referencias: hasta 31 GB. **Sin ruta oficial Apple Silicon**
(ni MLX ni Metal en la ficha; mflux/CoreML son comunidad).

**Veredicto:** **no entra**. (1) **Licencia Qwen Research, solo investigación/evaluación**: uso comercial
(Blindbeds, Mía, clientes) requiere acuerdo con Alibaba → descalifica antes de medir; los Qwen-Image
2511/2512 siguen en Apache 2.0. (2) 2,5-4 min/imagen frente a segundos en FAL.ai (ya conectado): la ganancia
sería solo privacidad + 0 €. Si entrara alguna vez: JIT en serie como Josie, nunca junto a Nex ni al explorador.
**Disparador para reabrir:** licencia Apache o acuerdo comercial, o necesidad real de RGBA/edición por
referencia en local con material sensible. Fuentes: HF Qwen/Comfy-Org/unsloth, kgptalkie (bench 36 GB),
modelfit.io (Apple Silicon), locallyuncensored (arquitectura/licencia).

## 20. Tripwire anti-bucle, LM Studio 0.4.25 y bench N2 vs N2.5 — 2026-10-01 (OK operador)

**Incidencia 29-30/09 (3er bucle, el peor):** el orquestador cloud (V4-Pro) lanzó a `@worker` (R1-8B, 24k) la
"MISIÓN C: SOHO_OPS, 5 rondas de refactor, MODELO LOCAL" (material Soho → local, correcto; alcance, no).
**3.123 pasos y 1.562 errores idénticos en 17 h**, en bucle desde la PRIMERA petición (7 s tras arrancar):
`tokens to keep > context length`. El 24k del fix del 14/09 estaba bien cargado; lo que desbordó fue el
harness: **64 definiciones de herramienta MCP por petición** (supabase 29, github 26, playwright 25, m365 13,
claude_workspace 14, imessage 4, context7 2) heredadas por el subagente local, más compactación con el
mismo modelo que falla y sin tope de pasos. Los dos sprints hermanos en nube (`@general`) acabaron en 12 min.

**Capa a (opencode):** `steps: 40` + `permission: "<mcp>_*": deny` en `worker.md`, `nexn2.md`,
`explorador.md` (validado contra `opencode.ai/config.json`: `AgentConfig.steps`, `PermissionConfig`);
`compaction.prune: true` en `opencode.json`. **Capa b (AGENTS.md v6.2):** "un subagente local = UNA ronda,
nunca un sprint"; sensible y grande → `@nexn2` ronda a ronda o parar y preguntar; mismo error dos veces =
cancelar. Capa c (vigilante externo) queda opcional.

**LM Studio 0.4.16 → 0.4.25 (brew cask --force, app adoptada).** Tres trampas, las tres resueltas:
(1) el proceso 0.4.16 seguía vivo tras `pkill` y `open -a` solo lo traía al frente → "Invalid load message";
hay que matar app + `~/.lmstudio/.internal/utils/node` y relanzar. (2) `~/.lmstudio/bin/lms` era una COPIA
del CLI viejo; copiar el nuevo fuera del bundle lo mata Gatekeeper (rc 137) → **symlink** al binario del
bundle (`Contents/Resources/app/.webpack/lms`). (3) **El runtime MLX 1.10.1/1.11.0 ignora el contexto
pedido** y auto-ajusta al máximo que cabe (bug-tracker #2250/#2318, sin fix): el explorador cargó a 196k,
aceptó 88k tokens y el swap subió a 9 GB. **Medido: solo `mlx-llm@1.10.0` respeta `-c`** → fijado con
`lms runtime select`, y `stack.sh _cargar` ahora verifica ctx real == pedido (si no, descarga y avisa);
`status` muestra el runtime. Parches no-think y `defaultContextLength` sobrevivieron a la actualización.

**Bench N2 vs N2.5:** `mlx-community/Nex-N2.5-mini-OptiQ-4bit` descargado (23,1 GB, id
`nex-n2.5-mini-optiq`, carga a 32k y responde con `reasoning_effort: none`). Runner `bench-vs-nex.sh`
(bench-coder.py ×3 pasadas: N2 · N2.5 defecto · N2.5 none, + latencia prompt 14k) programado por LaunchAgent
`com.luisfran.bench-vs-nex` para el **02/10 03:00**, informe en `bench-vs-nex/REPORT-*.md` + notificación;
deja el perfil AGENTE al terminar. Criterio: entra solo si iguala o mejora código, latencia y disciplina
no-think (sin parche de template, que N2.5 trae nativo).

**Resultado del bench N2 vs N2.5 (01/10 08:17, lanzado a mano; el LaunchAgent de las 03:00 se retiró):**

| | N2-mini (actual) | N2.5 adaptativo | N2.5 `reasoning_effort: none` |
|---|---|---|---|
| Código (6 verificables) | **6/6** | 5/6 | 5/6 |
| Tokens por tarea | **68** | 127 | 164 |
| Razonamiento total | **0** | 372 | 580 |
| Velocidad | **82,5 t/s** | 76,1 | 77,3 |
| Prompt 26,6k frío / caliente | 25,5 s / 0,9 s | 26,9 s / 1,0 s | — |
| RAM | **20,4 GB** | 23,1 GB | 23,1 GB |

**Veredicto: N2.5 NO entra.** Falla la misma tarea en ambos modos (C6, merge de dicts), piensa aunque se pida
`none` (LM Studio no pasa `reasoning_effort` al template: 580 tokens de razonamiento) y pesa 2,7 GB más en un
equipo donde Nex ya no cabe con el explorador. Sus mejoras publicadas son de computer-use/browsing/visual
grounding (OSWorld), que el stack no usa en local. Bench pequeño: la diferencia de código es 1 tarea, así que
la lectura es "no mejora", no "es peor"; lo decisivo es el razonamiento no desactivable y el peso.
Los 23 GB de `nex-n2.5-mini-optiq` siguen en disco pendientes de OK para borrar.

## 21. Reparto DeepSeek: V4.1-Flash primario agéntico, V4-Pro para conocimiento y contexto largo — 2026-10-01 (OK operador)

**Reparto (un alias nuevo, nada más):** `cloud-agentic` → `deepseek/deepseek-v4.1-flash` con
`provider.data_collection: deny`, primario de opencode. `cloud-coder-value` (V4-Pro) sigue de primario en
**hermes** y como agente **`dpsk`** en opencode, ahora el salto consciente (Tab) para conocimiento factual sin
búsqueda, contexto muy largo o razonamiento difícil. `cloud-megacontext` sigue en V4-Pro. 19 alias.
Motivo (paper DeepSeek, tabla 1): Flash gana en agente (DeepSWE 74,2 vs 62,7; Terminal-Bench 3.0 30 vs 11,8)
y pierde en conocimiento (SimpleQA 42,3 vs 55,2), contexto largo (LongBench-V2 45,2 vs 51,5) y multilingüe.

**A/B en opencode headless (`--dir`, sin subagentes, carpetas aisladas):**

| | V4.1-Flash | V4-Pro |
|---|---|---|
| T1 arreglar 5 fallos en 2 ficheros (tests intactos) | ✅ 8,6 s · 5 pasos | ✅ 30,0 s · 9 pasos |
| T1 tokens entrada / salida+razonamiento / caché | 40,6k / 1,6k / 170k | 42,3k / 3,4k / 352k |
| T2 análisis de cobertura de stack.sh (verdad conocida) | ✅ 6,4 s · 3 pasos | ✅ 11,9 s · 2 pasos |

Los dos aciertan todo; Flash es **2-3,5× más rápido** y gasta la mitad de salida y caché. Coste real de las
cuatro ejecuciones juntas: 0,185 $ (OpenRouter asienta el coste con retraso; el reparto por ejecución
no es fiable, opencode no calcula coste con proveedor propio).

**Corrección de la estimación de precio:** con `data_collection: deny` OpenRouter excluye a los proveedores
baratos de Flash (0,016 $/M) y sirve desde Together/StreamLake/Fireworks a 0,14-0,30 $/M entrada y
0,56-1,20 $/M salida. Por tarea, Flash cuesta **lo mismo o algo menos** que V4-Pro, no 5-15× menos:
la ganancia es velocidad y calidad agéntica, no precio. **Incoherencia pendiente:** el alias de V4-Pro NO
lleva el filtro y hoy se sirve desde Baidu y StreamLake (sede en China) a 0,23 $/M; con el filtro subiría a
~1,5-1,7 $/M entrada. Decisión del operador: filtro en todos los alias cloud o en ninguno.

**Nex-N2.5 borrado** (22 GB) con OK del operador tras el bench. Libre: 285 GB.

---

## §23 — Segundo round de automejora (2026-10-02, segundo ciclo)

> Ciclo autónomo ejecutado en la misma sesión que §22, a continuación. Pedido del operador:
> "Realiza otro round de tres loops para implementar mejoras y desarrollo de nuestro sistema agéntico."

### Auditoría previa: hallazgos nuevos

| Archivo | Problema detectado |
|---|---|
| `llm-stack/llm-stack-v5.md` | **CRÍTICO**: completamente desactualizado (v5.0/08-08-02). Tabla de modelos con todos los modelos retirados (Coder-30B, 35B, GLM-5.2, cloud-coder-next). Perfiles CODE/GENERAL/LIGERO obsoletos. Sin cloud-agentic, sin dual-plane, sin data_collection:deny, sin historial de versiones |
| `llm-stack/stack.sh` | Comentario de versión "v5.3" en la cabecera (el código real es v5.6) |
| `AI_OS/ROADMAP.md` | Fase 2 dice "Ollama" (retirado); Fase 5 marcada como "⏳" con "laboratorio Ollama" (completada con LM Studio) |
| `AI_OS/SISTEMA.md` | Lista de alias para Claude Code incompleta: 13 alias v5.3 vs 19 alias v5.6 reales; faltan cloud-agentic, cloud-coder-flash, cloud-reasoning, etc. |

### Loop 1 — llm-stack-v5.md reescrito

Secciones actualizadas:
- **Header**: añadido "Última actualización: 2026-10-02 (v5.6)" y referencia a sistema-agentico.md
- **Arquitectura**: diagrama reescrito con dos planos (local/cloud) y modelos reales; ley de frontera v5.6
- **Tabla de modelos**: completa reescritura — 8 locales (Nex, R1-8B, Qwen3.5-9B, embed, gpt-oss-20b, Phi-4, Gemma, uncensored), 2 gratis via agy-bridge, 8 cloud con precios actualizados y nota de data_collection:deny
- **Perfiles de RAM**: CODE retirado → AGENTE (default), GENERAL, LIGERO con descripciones de cuándo usar cada uno
- **Operación diaria**: `stack.sh code` → `stack.sh agente`; JIT explicado
- **Archivos del stack**: simlink 35B marcado como RETIRADO; sistema-agentico.md añadido
- **Disciplina de perfiles**: actualizada a v5.6 (opencode → AGENTE, hermes → GENERAL)
- **Historial de versiones**: tabla completa v5.0 → v5.6 añadida al final

### Loop 2 — Ficheros menores AI_OS + stack.sh

- **ROADMAP.md**: Fase 2 "Ollama" → LM Studio; Fase 5 ⏳ → ✅ completada
- **SISTEMA.md**: lista de alias ampliada a 19 (v5.6) con referencia al litellm.config.yaml
- **stack.sh**: comentario de versión v5.3 → v5.6

### Loop 3 — Commits + push

- `llm-stack`: `llm-stack-v5.md`, `stack.sh`, `sistema-agentico.md` (§23) → commit + push
- `AI_OS`: `ROADMAP.md`, `SISTEMA.md`, nota de sesión, PENDING_MAC → commit + push

---

## §22 — Snapshot de estado del sistema agentico (2026-10-02)

> Fotografía del estado real del stack. La toma Claude (Dispatch/Cowork) tras el ciclo de 3
> loops de automejora autónoma sobre el sistema agentico completo (Mac + HP + iPhone).
> Leer antes de proponer cambios de arquitectura en futuros ciclos.

### Estado hardware
| Equipo | Rol agentico | Stack IA local |
|---|---|---|
| MacBook Pro M4 Max | Orquestador principal; laboratorio IA | LM Studio v5.6: Nex-N2-mini (Qwen3.5-14B Q4 8 GB), R1-8B (workers ×4), Qwen3.5-9B (explorador residente 6 GB), gpt-oss-20b (razonador), Phi-4 (revisor), Gemma-E4B (auditor). LiteLLM proxea 19 alias. |
| HP ProBook 440 14" | Trabajo Soho; orquestación cloud (sin IA local) | **Cero LLM local** (decisión 02/08 + medición 14/08). Solo cloud-* y hermes |
| iPhone 14 Pro Max | Cliente ligero; captura y consulta | Sin IA local. Claude.ai app + Drive. Sin acceso a BD sensible |

### Estado del stack Mac (v5.6)
- **Plano de orquestación:** Claude Code (CLI, suscripción), opencode (sprints agénticos), Codex
- **Plano de datos sensibles:** Nex-N2-mini única local grande (Soho/cliente/personal nunca salen del Mac)
- **LiteLLM:** 19 alias activos (ver `~/llm-stack/litellm.config.yaml`). Supervisado por launchd (KeepAlive)
- **Tripwire anti-bucle:** `steps: 40` + MCP `deny` en workers de opencode (§20, 2026-09-27)
- **data_collection:deny:** aplicado en `cloud-agentic` (V4.1-Flash). NO aplicado en `cloud-coder-value` (V4-Pro/dpsk). Decisión pendiente del operador (uniformizar o dejar así)
- **RAM opción b:** solo Qwen3.5-9B reside permanentemente (6 GB); Nex y R1-8B son JIT. Libre ~285 GB tras borrar Nex-N2.5

### Orquestadores por equipo (2026-10-02)
| Orquestador | Equipo | Primario para | Modelo(s) |
|---|---|---|---|
| Claude Code CLI | Mac + HP | Todo el desarrollo; tareas largas | claude-sonnet-4-6 (suscripción) |
| opencode | Mac | Sprints agénticos autónomos | cloud-agentic (V4.1-Flash) primario; local-general (Nex) para sensibles |
| hermes | Mac | Contexto gigante (repo entero + logs) | cloud-megacontext (V4-Pro 1M) |
| Codex | Mac + HP | Segunda opinión; código duro | ChatGPT (suscripción) |
| iPhone (Claude app) | iPhone | Consulta conversacional | claude-sonnet-4-6 cloud |

### Mejoras aplicadas en este ciclo (2026-10-02)
1. **JERARQUIA_IA.md → v5.7**: header corregido, local-fast = explorador residente, §2 con 19 alias completos, §3 con cloud-agentic como primario agéntico, regla tripwire documentada
2. **WORKFLOWS.md**: Ollama → LM Studio, opencode añadido a la tabla de IAs y al flujo, dual-plane v5.6 documentado, iPhone workflow añadido como sección propia
3. **STACK_AND_TOOLS.md**: Ollama → LM Studio con modelos reales, opencode añadido, iPhone "Consulta" → descripción de cliente ligero con frontera de datos

### Pendientes del operador (no automatizables)
- Decidir: `data_collection:deny` en todos los alias cloud o solo en cloud-agentic (§21)
- PR #1 radar-fricciones (opencode watchlog vs priorizacion.md): revisar y cerrar
- git push radar-fricciones tras revisar `docs/radar.html`

## §24 — Tercer round de 5 loops de automejora (2026-10-02)

**Pedido:** "Otro round de 5 loops incluyendo skills, hooks, loops y grafos, apps y programas"  
**Modelo:** claude-sonnet-4-6 (Dispatch/Cowork)

### Auditoría previa

| Archivo | Problema encontrado |
|---|---|
| `llm-stack/stack-agentico.html` | "18 alias" × 3 ocurrencias (real: 19 desde v5.6) + "CODE" en hint de swap (perfil retirado 10/09) |
| `enrutador-ia/SKILL.md` | Tabla de reparto sin `cloud-agentic`; Two-way opencode apuntaba a `local-general` |
| `REGLAS_ENRUTAMIENTO.md` | Sin sección para `cloud-agentic` (añadido a enrutar.sh el 01/10 sin documentar) |
| `skill-sistema-status` | No existía — diagnóstico de salud del stack tenía que hacerse manual |
| `ciclo-automejora.sh` | OK — no tocar |
| `enrutar.sh` | Ya tenía `cloud-agentic` (línea 344, añadido 01/10) — correcto |

### Loop 1 — Grafo (stack-agentico.html)

- Fecha: `2026-09-10` → `2026-10-02`
- 3× `18 alias` → `19 alias` (lede, SVG, cabecera §02)
- Hint de swap: `código serio→CODE` → `código serio→V4-Pro (cloud-coder-value)` + `Perfil CODE retirado 10/09`

### Loop 2 — Skill (enrutador-ia/SKILL.md)

- Destinos list: añadido `cloud-agentic`
- Tabla de reparto: nueva fila `cloud-agentic` (DeepSeek-V4.1-Flash, primario opencode, steps:40, MCP deny, NO sensible)
- Two-way §opencode: `local-general` → `cloud-agentic` (primario v5.6) con fallback `local-general` si sensible

### Loop 3 — Reglas (REGLAS_ENRUTAMIENTO.md)

- Nueva sección `## cloud-agentic — primario opencode v5.6 (2026-10-01)` con:
  modelo, comparativa V4.1-Flash vs V4-Pro, guardarrailes (steps:40, MCP deny), frontera de datos, escalado, data_collection

### Loop 4 — Nueva skill (skill-sistema-status)

Creada desde cero en `BIBLIOTECA/skills/skill-sistema-status/SKILL.md`.  
Diagnóstico de salud del stack en ≤30 s con 5 checks:
1. LiteLLM :4000 (curl health)
2. LM Studio :1234 + perfil RAM activo (AGENTE/GENERAL/LIGERO)
3. agy-bridge :4010
4. Registro del enrutador (últimas 5 entradas, busca errores/colgados)
5. Informe ciclo de automejora (¿PENDIENTE DE REVISIÓN?)

Formato de salida: tabla markdown con semáforo OK/ERROR + acción correctora.

### Loop 5 — §24 + nota sesión + commits

Este parágrafo. Commits a continuación.

### Estado final

| Fichero | Cambio |
|---|---|
| `llm-stack/stack-agentico.html` | 18→19 alias ×3, fecha, fix CODE ref |
| `BIBLIOTECA/skills/enrutador-ia/SKILL.md` | cloud-agentic en destinos + tabla + Two-way |
| `BIBLIOTECA/skills/enrutador-ia/REGLAS_ENRUTAMIENTO.md` | sección cloud-agentic v5.6 |
| `BIBLIOTECA/skills/skill-sistema-status/SKILL.md` | nueva skill creada |
| `llm-stack/sistema-agentico.md` | §24 añadido |
