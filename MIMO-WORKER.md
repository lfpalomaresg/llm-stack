# MiMo-V2.6-Distill-Qwen-9B como `@worker` / `local-worker` (2026-10-19)

**Modelo:** `mlx-community/MiMo-V2.6-Distill-Qwen-9B-OptiQ-4bit` (Xiaomi, MIT; SFT agéntico sobre Qwen3.5-9B),
7,1 GB, id LM Studio `mimo-v2.6-distill-qwen-9b-optiq`. Sustituye al DeepSeek-R1-0528-Qwen3-8B (queda en disco).

## Dos arreglos imprescindibles (sin ellos falla en opencode)

1. **Plantilla de Qwen3.5, no la suya.** Con la plantilla original de MiMo, LM Studio NO interpreta las
   llamadas a herramientas: el modelo escribe `<tool_call><function=read>…` como TEXTO, opencode no ve
   ninguna herramienta y el subagente compacta en bucle (medido: 41 pasos, 21 compactaciones, 0 herramientas).
   Fix: `chat_template.jinja` del modelo = el del explorador (Qwen3.5-9B, no-think por defecto).
   Copias en este repo: `mimo-chat_template-qwen35-nothink.jinja` (la que se usa) y
   `mimo-chat_template-original.jinja`. **Re-aplicar si se re-descarga el modelo:**
   `cp ~/llm-stack/mimo-chat_template-qwen35-nothink.jinja ~/.lmstudio/models/mlx-community/MiMo-V2.6-Distill-Qwen-9B-OptiQ-4bit/chat_template.jinja`
2. **32k de contexto, también declarados en opencode.** A 24k (límite declarado 16k, heredado del R1) el
   harness de opencode (~10k) + la reserva de compactación no dejaban sitio: compactaba a cada paso.
   Ahora: config por modelo de LM Studio 32768, `enrutar.sh` carga a 32768, `opencode.json` `limit.context` 32768.

## Cómo pedirle las cosas
MiMo razona **por escrito en la respuesta**, no en un bloque oculto (con la plantilla de Qwen no-think su
razonamiento oculto es 0). Si le pides "solo el número" se salta el razonamiento y falla (RevPAR 68,50 en vez
de 102). Pídele "razona lo necesario y termina con RESPUESTA: <valor>". Está en `agent/worker.md` y en REGLAS.

## Medido (19/10)
| | R1-8B | MiMo-9B (final) |
|---|---|---|
| Razonar, 8 tareas hoteleras (`bench-razonar.py`) | 2/8 · 927 s · 51.734 tok de razonamiento | **8/8 · 34 s** |
| Código, 6 tareas verificables (`bench-coder.py`) | 3/6 · 2.302 tok/tarea | **6/6** · 73 tok/tarea |
| Subagente real en opencode: arreglar 5 fallos | 2 compactaciones en 10 min, cortado | **✅ 131 s · 0 compactaciones** |
| Subagente real en opencode: factura, 8 tests ocultos | — | **✅ 8/8 · 713 s · 3 compactaciones** (3 delegaciones) |

Descartados: plantilla original (sin herramientas), razonamiento forzado en bloque oculto (6/8, peor).
LM Studio ignora `chat_template_kwargs` y `reasoning_effort` por petición: el modo lo fija la plantilla.
