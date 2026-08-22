# 🔴 Incidente abierto — Kernel panic de GPU ×2 (2026-08-21)

> **Documento de trabajo del incidente.** Si el Mac vuelve a petar a mitad de la
> investigación, TODO el estado está aquí: evidencia, hipótesis, escalera de
> pruebas y hasta dónde se llegó. Retomar leyendo este archivo — no reconstruir
> de cero.
>
> Cómo recuperar la sesión de Claude Code tras un reinicio: ver §6.

## 1. Qué pasó (hechos verificados, no hipótesis)

Dos kernel panics —reinicio forzado del sistema, no cuelgue de app— la noche
del 21/08/2026, con el mismo origen exacto:

| Hora | Panic string | Fichero fuente | Proceso panicado |
|---|---|---|---|
| 22:22:15 | `IOGPUGroupMemory::remove_memory_object() memory object not found` | `IOGPUGroupMemory.cpp:323` | WindowServer |
| 22:49:00 | `pending memory object unexpectedly found in non pending hash` | `IOGPUGroupMemory.cpp:528` | WindowServer |

- **Subsistema:** `com.apple.iokit.IOGPUFamily` (130.15.2) + `com.apple.AGXG16X`
  (351.2) — el driver de GPU/Metal del M4 Max.
- **Entorno:** macOS 26.5.2 (25F84), Darwin 25.5.0, Mac16,5 (M4 Max, 36 GB).
- **Evidencia en disco:** `panic-full-2026-08-21-222215.0002.panic` y
  `panic-full-2026-08-21-224900.0002.panic` en
  `/Library/Logs/DiagnosticReports/Retired/` + `ResetCounter-*.diag` de ambas
  horas. Reinicios confirmados con `last reboot` y `sysctl kern.boottime`.
- **En el panic de las 22:49 el Compressor iba al 9%** ("OK") — la máquina NO
  estaba asfixiada de RAM en el instante del panic. Refuerza que es un bug de
  consistencia del driver, no un simple out-of-memory.

## 2. Contexto en el que saltó

- Perfil **AGENTE** cargado entero: 35B orquestador@32k + R1-8B worker@16k +
  embed (MLX vía LM Studio), tras la batería de estrés que dejó mínimos de
  13% de RAM libre.
- Se estaba validando **en real** el subagente `@auditor-local` de opencode, que
  llega a `agy` (Antigravity CLI) a través de `agy-bridge.py` (`localhost:4010`).
- Correlación en `litellm.log`: tras el primer reinicio (22:23:39), LM Studio
  rechazó recargar el 35B — *"Model loading was stopped due to insufficient
  system resources… would likely overload your system and cause it to freeze"*.
  El guardarraíl de RAM **reaccionó**, pero el segundo panic llegó igual a las
  22:49, al repetir la invocación del auditor con el stack cargado.

## 3. Hipótesis de trabajo (interpretación, pendiente de confirmar)

Ambos panic strings son fallos de **consistencia interna en la tabla de objetos
de memoria de GPU** del driver (referencia obsoleta / carrera), el patrón de un
race condition — no de "se acabó la memoria". MLX asigna/libera memoria de GPU
constantemente, y ese día el guardarraíl estaba "reciclando" RAM activamente con
varios modelos concurrentes cerca del límite físico. Añadir otro cliente que
toca GPU (opencode + bridge) habría **destapado** una carrera latente del
driver, no creado el problema de la nada.

**Lo que NO sabemos aún:**
- [ ] ¿`agy` toca GPU por sí mismo, o el peso es solo del stack MLX + el tráfico nuevo?
- [ ] ¿Es un bug conocido de macOS 25F84 / Apple Silicon con cargas MLX concurrentes?
- [ ] ¿Reproduce con el stack en LIGERO (solo 8B), o exige el AGENTE completo?

## 4. Escalera de pruebas — de menos a más agresivo

Regla: **un peldaño cada vez**, anotar el resultado aquí ANTES de subir al
siguiente. Si algún peldaño reproduce el panic, PARAR: la información ya está
y el siguiente paso es mitigar/reportar, no insistir.

| # | Prueba | Riesgo | Estado | Resultado |
|---|---|---|---|---|
| 1 | Buscar el panic string + build de macOS en foros Apple/MLX/LM Studio (¿bug conocido? ¿fix en 26.6?) | Ninguno | ✅ 21/08 | **ES UN BUG CONOCIDO de IOGPU.kext de Apple**, disparado por MLX. Ver §7 |
| 2 | Inspeccionar si `agy` usa GPU: lanzarlo SOLO (sin stack cargado, `stack.sh stop`) con `sudo powermetrics --samplers gpu_power` o Monitor de Actividad pestaña GPU | Ninguno (sin stack) | ✅ 22/08 | **`agy` NO toca la GPU local**: frameworks Metal mapeados (enlazado estándar) pero **cero regiones de memoria GPU asignadas** (`vmmap` durante llamada real). Inferencia 100% nube (SUCCESS, 4,2 s) |
| 3 | `agy-bridge.py` + curl manual a `:4010` (SIN opencode) con stack cargado | Bajo | ✅ 22/08 | Bridge responde end-to-end (`gpt-oss-free`, 14,4k tokens in / 64 out); los modelos locales ni se inmutaron (coder+8B IDLE intactos), RAM estable. El camino bridge→agy→nube tiene 0 interacción con GPU local |
| 4 | Lo mismo con stack en **AGENTE** completo — el bridge solo, sin opencode | Medio | ⏭️ Innecesario | Con 2 y 3 demostrado que el camino del bridge no toca GPU local — cargar el AGENTE para repetirlo no aporta información |
| 5 | opencode + `@auditor-local` con stack en **LIGERO** | Medio | ✅ 22/08 00:47 | **SIN PANIC — y reprodujo el mecanismo completo del crash.** Ver §9 |
| 6 | La prueba original: opencode + `@auditor-local` con AGENTE completo — **SOLO si 1-5 no explican nada**, con todo lo demás cerrado y trabajo guardado | Alto (es la que petó 2×) | ❌ Innecesario | El peldaño 5 explicó el mecanismo — repetir la condición de panic no aporta nada |

Mitigación de diseño disponible sin repetir nada (aplicable ya si 1-2 dan
señal): prohibir que opencode invoque el auditor con el perfil AGENTE completo
cargado — forzar descarga parcial antes, como ya hace el relevo worker↔auditor.

## 5. Estado de la investigación

- **2026-08-21 23:0x** — Evidencia recogida y verificada (panics, ResetCounter,
  boottime, litellm.log). Config commiteada (`0dc8f52`) pero SIN validar en
  vivo. Documentado en `sistema-agentico.md` §5/§7, `index.html`, README,
  `REGLAS_ENRUTAMIENTO.md` (skill enrutador-ia) y memoria de Claude Code.
- **Siguiente paso:** peldaño 1 de la escalera.

## 7. Hallazgos del peldaño 1 (2026-08-21 noche) — bug conocido de Apple

**La hipótesis del §3 queda CONFIRMADA por fuentes externas:** es un bug de
`IOGPU.kext` (el kernel extension de GPU de Apple), no de nuestro código ni de
LM Studio — pero el patrón de uso de Metal de MLX lo dispara de forma fiable.
Hay múltiples reportes públicos con los mismos panic strings:

| Fuente | Qué reporta | Coincidencia con nuestro caso |
|---|---|---|
| [mlx#3346](https://github.com/ml-explore/mlx/issues/3346) | M3 Ultra, macOS 26.4: 9 panics en 6 días. `IOGPUGroupMemory.cpp:219` "Memory object unexpectedly not found" + `IOGPUMemory.cpp:550` underflow | Mismo fichero fuente y familia de panic que los nuestros (líneas 323/528) |
| [mlx#3186](https://github.com/ml-explore/mlx/issues/3186) | **M4 Max 36 GB (nuestro hardware exacto)**, macOS 26.3: panic en prefill grande | Mismo chip y RAM |
| [mlx-lm#883](https://github.com/ml-explore/mlx-lm/issues/883) | `mlx_lm.server`: crecimiento de memoria sin límite → panic | Mismo patrón servidor |
| [lmstudio-bug-tracker#927](https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/927) | Cargar un 2º modelo MLX tumba LM Studio | Multi-modelo, nuestro perfil AGENTE |

**Condiciones de disparo documentadas en esos issues — las tres se daban aquí:**
1. Utilización de memoria GPU > ~80% (nuestro AGENTE: ~25,6 GB de modelos + KV,
   con el techo wired de GPU por defecto en ~27 GB en un Mac de 36 GB).
2. Ciclos repetidos de carga/descarga de modelos (nuestro relevo worker↔auditor
   hace EXACTAMENTE eso).
3. Varios procesos compitiendo por la GPU (35B + R1 + la invocación nueva).

**Estado del bug:** sin fix confirmado en los issues (afecta al menos a 26.3 y
26.4; nosotros estamos en 26.5.2 y nos pasó, así que sigue vivo ahí). Sin
respuesta pública de Apple. Requiere escalado interno de Apple.

**Hallazgo adicional (22/08, de los propios stackshots):** en el instante de
AMBOS panics había una sesión de **Codex** viva (`Codex (Renderer)` +
`Codex (Service)` + CLI `codex`), además de Chrome, Claude Desktop, Notion y
Granola — todos con procesos *Renderer* de Electron/Chromium, que son
**clientes de GPU por composición** (reservan IOSurfaces para pintar su
ventana; la inferencia de Codex es cloud y no cuenta). El proceso que panicó
fue **WindowServer**, el compositor que gestiona los objetos de memoria de GPU
de todas esas ventanas — y `IOGPUGroupMemory.cpp` es justo el contable de esos
grupos. Codex no fue LA causa, pero engordó la condición de disparo nº 3
(varios procesos compitiendo por GPU) en el peor momento posible.

**Reconstrucción completa del disparo:**
```
MLX (35B + R1)                        → ~27 GB wired (el techo de GPU del Mac)
+ relevo worker↔gemma                 → ciclos carga/descarga en pleno límite
+ WindowServer sirviendo a Codex/     → N clientes GPU más peleando
  Chrome/Claude/Notion/Granola           por las migajas
= las 3 condiciones de disparo del bug de Apple, simultáneas
```

**Palancas de mitigación identificadas (aún sin aplicar):**
- **Actualizar macOS:** hay **26.6.2 disponible** (verificado con
  `softwareupdate --list` el 21/08). ⚠️ **Verificado el 21/08 noche: NO hay
  documentación de que arregle este bug.** Dos datos en contra: (1) los fixes
  de kernel y driver gráfico que Apple destacó en esta oleada **ya venían en
  26.5.2** — la versión que tenemos, y petó igual; (2) los issues de MLX
  siguen abiertos sin fix de Apple confirmado en ninguna versión. Actualizar
  sigue siendo razonable (higiene general), pero como apuesta, no como
  solución documentada — la mitigación real está en las otras palancas.
- **`sysctl iogpu.wired_limit_mb`** (ahora a 0 = default ~27 GB en este Mac):
  fijarlo MÁS BAJO (p. ej. 24576) deja margen de seguridad a WindowServer —
  los modelos que no quepan fallarán con error visible en vez de panic, que es
  exactamente nuestra filosofía. Se pierde capacidad total de modelo. No
  persiste entre reinicios salvo LaunchDaemon.
- **Reducir la presión estructural del perfil AGENTE** cuando haya un cliente
  GPU adicional: no validar opencode con el AGENTE completo cargado (relevo
  previo), y/o bajar techos de contexto.
- **Reportar a Apple** (Feedback Assistant) con nuestros 2 `panic-full` — suma
  al escalado interno que piden los issues.
- ❌ **DESCARTADO bajar `iogpu.wired_limit_mb` (22/08):** los pesos del AGENTE
  solos son 25,6 GB — cualquier techo que dé margen real (≤24,5 GB) impide que
  el 35B y el R1 convivan, o sea, mata la estructura. Y ni siquiera ataca el
  disparador probable (el relevo caliente). Se protege por reglas operativas,
  no por capado.

## 8. Reglas operativas adoptadas (22/08) — mitigación sin perder estructura

1. **Endurecer el relevo worker↔auditor local**: entre descargar el worker y
   cargar gemma, verificar que la GPU ha liberado de verdad (pausa +
   comprobación), en vez del ciclo descarga→carga inmediato.
   ✅ **IMPLEMENTADO 22/08** en `enrutar.sh` (destino `local-auditor`): espera
   activa hasta 15 s a que los pequeños desaparezcan de `lms ps` + 3 s de
   drenaje del driver antes de cargar gemma; si la descarga no termina,
   BLOQUEADO visible con instrucción (nunca cargar encima de una descarga a
   medias). Suite `test-ram.sh`: 10/10 tras el cambio. Nota: la suite aún no
   tiene caso específico del relevo endurecido — hueco menor conocido.
2. **Relevo solo sin presión**: si la GPU va justa, el auditor sensible espera
   o la tarea va a `auditor-free` (cloud, 0 GPU local).
3. **Minimizar clientes GPU accesorios durante operaciones de carga/descarga
   con el AGENTE cargado**: cerrar o no tener activas las apps Electron
   (Codex desktop, Chrome cargado de pestañas, etc.). El CLI `codex` en
   terminal apenas pesa; la app con Renderer sí.
4. **La validación real de opencode (`@auditor-local`) queda condicionada** a
   tener 1-3 aplicadas y el peldaño 5 de la escalera (stack LIGERO) en verde.

## 9. LA TECLA — peldaño 5 (22/08 00:47): el mecanismo completo, reproducido sin crash

Con el stack en LIGERO (solo 8B, GPU con ~17 GB de margen) se lanzó
`opencode run --agent auditor-local` con un bug sembrado. **No hubo panic** —
y la prueba destapó la cadena causal completa de la noche anterior:

1. **El harness de opencode no cabe en gemma@8k.** opencode mete su prompt de
   sistema + definiciones de herramientas (>8k tokens; `agy` mostró ~14-17k de
   overhead equivalente) y LiteLLM devuelve en bucle:
   *"The number of tokens to keep from the initial prompt is greater than the
   context length"*. En 5 minutos de prueba: **163 líneas de ERROR** en
   `litellm.log` (y 1.078 acumuladas contando la noche del panic).
2. **opencode reacciona con reintentos + compactación**, y cada vuelta dispara
   **cargas JIT del coder (17,2 GB)** vía LiteLLM→LM Studio — recargó el coder
   él solo estando en perfil LIGERO.
3. **El proceso sobrevive a SIGTERM** — siguió re-encolando peticiones y
   regenerando tras matarlo; hizo falta `kill -9` + descargar el coder para
   parar la tormenta.
4. Anoche, esa misma tormenta corrió **con el AGENTE al techo de GPU** (~27 GB):
   cargas de 17-20 GB en bucle + generaciones huérfanas + relevo caliente +
   renderers Electron = churn masivo de asignaciones wired justo en la zona
   del bug de `IOGPU.kext` → **panic**. (Encaja con el `litellm.log` de las
   22:23: *"Failed to load model qwen3.6-35b-a3b… insufficient resources"* —
   la misma recarga JIT, con el 35B.)

Nota positiva: **gemma SÍ cazó el bug sembrado** (identificó el error del IVA)
antes de que la espiral de contexto se lo comiera.

**Causa raíz (dos capas):**
- *Nuestra:* `@auditor-local` vía opencode está **estructuralmente mal
  configurado** — el harness de opencode no cabe en el contexto de 8k con el
  que el relevo carga a gemma, y `local-auditor` **ni siquiera está declarado**
  en `opencode.json` (opencode no sabe su límite y no compacta a tiempo).
  El retry-storm resultante es nuestro.
- *De Apple:* que ese churn tumbe el kernel en vez de fallar limpio es el bug
  de `IOGPU.kext` (§7) — nosotros solo podemos no pisar su zona de disparo.

**Arreglo APLICADO (22/08, decisión del operador): (b) + (c).**
- ✅ **(b) `@auditor-local` retirado de opencode** — `agent/auditor-local.md`
  → `.retired.20260822-0101` (backup, no borrado) y doctrina de AGENTS.md
  reescrita: material sensible NO se revisa desde opencode; la auditoría local
  (gemma) va SOLO por `enrutar.sh` (prompts directos pequeños, relevo
  endurecido, validado — cazó el bug del IVA). opencode usa `@revisor`
  (auditor-free/GLM cloud) para lo demás. Razón de descartar (a): habría que
  pelear DOS problemas (medir si el harness cabe en 16k + el cuelgue documentado
  de opencode con modelos pequeños del 03/08) para conservar un atajo usado
  cero veces — regla de las 3 correcciones: a la tercera se replantea el
  diseño, no se parchea.
- ✅ **(c) tapa anti-tormenta en LiteLLM**: ya existía `num_retries: 1` (sin
  fallbacks desde el 02/08); se deja documentado en el propio
  `litellm.config.yaml` que NO se suba sin releer este incidente (los errores
  de contexto llegan como APIConnectionError, clase reintentable, pero son
  deterministas).
- Los alias del bridge (`gpt-oss-free`/`gemini-free`/`auditor-free`) SE QUEDAN
  en opencode: van a la nube vía agy, 0 GPU local, 128k+ de contexto — no
  pueden reproducir ni la tormenta ni el churn.
- 💡 Opcional a valorar otro día: desactivar el JIT model loading de LM Studio
  (petición a modelo no cargado → error visible en vez de carga sorpresa de
  17-20 GB). Encaja con la filosofía "sin fallbacks silenciosos", pero cambia
  el comportamiento de todos los flujos — decisión de operador, no urgente.

## 6. Recuperar la sesión de Claude Code tras un reinicio

Las sesiones del CLI **se guardan solas**, siempre — cada conversación es un
`.jsonl` en `~/.claude/projects/<carpeta-del-cwd>/`. Tras un panic no se pierde
nada de lo hablado; solo el trabajo no guardado en disco de otras apps.

| Quieres… | Comando |
|---|---|
| Retomar la ÚLTIMA sesión del directorio actual | `claude --continue` |
| Elegir entre sesiones anteriores (lista con fechas) | `claude --resume` |
| Retomar una sesión concreta por id | `claude --resume <session-id>` |

La sesión de esta investigación: id local `efe6ab4d-b0f5-4bc2-b907-4e0644c05fae`
(web: `claude.ai/code/session_01AaSqaS7cTwfdtgkBvKcXFu`). Arrancada desde
`~`, así que: `cd ~ && claude --resume` y elegirla en la lista.

## 10. TERCER EPISODIO (22/08 12:37) — watchdog de WindowServer, SIN tormenta

**Qué pasó:** reinicio a las 12:38 durante la batería de pruebas del entorno
agéntico. Esta vez **NO es kernel panic** (PanicReporter vacío): son dos
`userspace_watchdog_timeout` de WindowServer (12:37:17 y 12:37:53, `bug_type
409`, stackshots en DiagnosticReports) — WindowServer se quedó sin GPU más
allá de su deadline y el watchdog tumbó la sesión gráfica.

**Qué corría (ventana 12:23–12:37):**
- `opencode run` headless (prueba de `@explorador`): coder-30B en
  `PROCESSINGPROMPT` sostenido (harness de ~15-30k tokens) + qwen3-8b
  `GENERATING` (el subagente) — perfil CODE, ~22 GB wired.
- Una TERCERA petición encolada: prueba del MCP `local-models`
  (`ask_local_model` → local-coder), que expiró a los 120 s.
- Renderers Electron habituales (Claude Desktop, Chrome…) pintando contra el
  mismo WindowServer.

**Qué NO pasó (diferencia clave con el 21/08):** cero líneas ERROR en
`litellm.log` en la ventana del crash; sin gemma, sin relevo, sin cargas JIT,
sin retry-storm. Las mitigaciones del §9 funcionaron — y aun así petó.

**Lectura:** la zona frágil no era (solo) la tormenta: es **WindowServer
compitiendo con MLX por la GPU en macOS 26.5.2**. El disparador de hoy fue
concurrencia legítima pesada: prompt-processing largo del 30B + generación
simultánea del 8B + tercera petición manteniendo la cola caliente. El
`PARALLEL=4` de LM Studio permite apilar trabajo pesado que de uno en uno es
inocuo.

**Regla operativa nueva (ADOPTADA 22/08 con OK del operador — criterio: fluidez sin perder productividad; por eso el punto 2, PARALLEL 4→2, se DESCARTA a propósito: recortaría los 4 workers del AGENTE):**
1. **Un solo trabajo pesado de GPU a la vez.** Mientras opencode mastica su
   harness (o cualquier modelo grande procesa >10k tokens), NO lanzar
   peticiones adicionales a modelos locales (ni enrutador, ni MCP, ni pruebas).
   En serie, no en paralelo. La concurrencia queda para peticiones pequeñas.
2. Valorar bajar PARALLEL de LM Studio (4→2) para que el servidor lo imponga.
3. Actualizar a macOS 26.6.2 (higiene, sin fix documentado) y sumar el
   stackshot 409 al reporte a Apple (refuerza: watchdog además de panics).

**Nota de método:** el apilamiento lo provoqué yo (Claude Code) al diseñar la
batería con pruebas en paralelo "para aprovechar el tiempo". Coste real: un
reinicio. La batería continúa EN SERIE y con OK explícito del operador.

### §10.b Secuela (22/08 14:11-15:05) — hermes degradado por TRES huecos encadenados

El operador probó hermes por **Telegram** (gateway) y la sesión fue pésima: 18,8 min
de respuesta (1.129 s según `gateway.log`), congelones, y avisos de «falta de
recursos / posible crash». No era avería del 35B — eran tres huecos apilados:

1. **El arranque en frío del LaunchAgent carga perfil CODE** — pero el proceso
   siempre-encendido es el gateway de hermes, que necesita GENERAL. Tras el
   reinicio de las 12:38, hermes quedó pidiendo `local-general` con el coder
   ocupando el hueco.
2. **El gateway de Telegram NO pasa por el wrapper de `.zshrc`** — la garantía
   de perfil solo cubre sesiones de terminal. Nadie preparó GENERAL, y hermes +
   LiteLLM reintentaron contra el guardarraíl: intentos repetidos de cargar
   20 GB encima de 22 GB = los congelones (mini-tormenta, mismo patrón §9).
3. **El guardarraíl de LM Studio quedó con contabilidad rancia tras los
   reinicios sucios**: rechazaba cargar el 35B incluso con 29 GB libres,
   presión 0 y sin otro grande (falló a 48k Y a 32k). Fix verificado:
   `lms unload --all && lms server stop && lms server start` → cargó a la
   primera (19 GiB) y responde en 2,5 s vía LiteLLM.

**Reglas nuevas que salen de aquí (propuestas al operador):**
- Tras cualquier reinicio sucio: **reiniciar el server de LM Studio** antes de
  diagnosticar nada (guardarraíl rancio = falsos «insufficient resources»).
- Decidir el **perfil de arranque en frío**: GENERAL (sirve al gateway 24/7)
  en vez de CODE, o que el arranque del gateway de hermes garantice su perfil
  como hace el wrapper de terminal.
- Reintentos de hermes: DECIDIDO NO TOCAR (22/08, criterio productividad) — con el
  arranque en frío en GENERAL el escenario determinista desaparece, y capar
  reintentos penalizaría los transitorios legítimos (warm-ups). Riesgo residual
  aceptado: hermes-por-Telegram con un opencode activo ocupando el hueco del
  grande — lo cubre la regla «un solo orquestador a la vez».
- ✅ APLICADO 22/08: arranque en frío del daemon pasa de CODE a GENERAL en
  stack.sh (test-ram.sh 10/10 tras el cambio).
