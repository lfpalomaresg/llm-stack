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
