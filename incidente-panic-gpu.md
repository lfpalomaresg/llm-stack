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
| 1 | Buscar el panic string + build de macOS en foros Apple/MLX/LM Studio (¿bug conocido? ¿fix en 26.6?) | Ninguno | ⬜ | |
| 2 | Inspeccionar si `agy` usa GPU: lanzarlo SOLO (sin stack cargado, `stack.sh stop`) con `sudo powermetrics --samplers gpu_power` o Monitor de Actividad pestaña GPU | Ninguno (sin stack) | ⬜ | |
| 3 | `agy-bridge.py` + curl manual a `:4010` (SIN opencode) con stack en **LIGERO** (solo 8B) | Bajo | ⬜ | |
| 4 | Lo mismo con stack en **AGENTE** completo — el bridge solo, sin opencode | Medio | ⬜ | |
| 5 | opencode + `@auditor-local` con stack en **LIGERO** | Medio | ⬜ | |
| 6 | La prueba original: opencode + `@auditor-local` con AGENTE completo — **SOLO si 1-5 no explican nada**, con todo lo demás cerrado y trabajo guardado | Alto (es la que petó 2×) | ⬜ | |

Mitigación de diseño disponible sin repetir nada (aplicable ya si 1-2 dan
señal): prohibir que opencode invoque el auditor con el perfil AGENTE completo
cargado — forzar descarga parcial antes, como ya hace el relevo worker↔auditor.

## 5. Estado de la investigación

- **2026-08-21 23:0x** — Evidencia recogida y verificada (panics, ResetCounter,
  boottime, litellm.log). Config commiteada (`0dc8f52`) pero SIN validar en
  vivo. Documentado en `sistema-agentico.md` §5/§7, `index.html`, README,
  `REGLAS_ENRUTAMIENTO.md` (skill enrutador-ia) y memoria de Claude Code.
- **Siguiente paso:** peldaño 1 de la escalera.

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
