# Qwen3.5-9B (explorador residente) — default NO-THINK (2026-09-15)

## Contexto
Opción b del stack (OK operador, 15/09): el orquestador es DeepSeek-V4-Pro (cloud) y en RAM
fija solo queda el **explorador** (`local-fast` → `qwen3.5-9b-mlx`, 32k, sin TTL), que sirve a
`@explorador`, a `enrutar.sh` (destino y degradado) y al bot de Telegram. `@worker` (R1-8B) y
`@nexn2` (Nex) entran JIT.

Por qué este modelo: misma familia `qwen3_5` que Nex (LM Studio ya la soporta), mismo formato de
tool-call `<function=…>` que Nex, 32k de contexto ≥ harness de opencode (~10k tokens), ~6 GB.
Sustituye al R1-8B que hacía de "fast" desde el 08/09 (razonaba: mal encaje para el rol).

## Problema
La plantilla original de Qwen3.5 PIENSA por defecto (`<think>` abierto salvo
`enable_thinking=false`). opencode/hermes/el bot hablan directo con LiteLLM y no pasan ese flag.

## Fix (idéntico a NEX-NOTHINK-FIX.md)
En `chat_template.jinja` del modelo, línea 149:

    ANTES: {%- if enable_thinking is defined and enable_thinking is false %}
    AHORA: {%- if enable_thinking is not defined or enable_thinking is false %}

Efecto: por defecto no piensa. Para forzar razonamiento puntual: `enable_thinking=true`.

## ⚠️ Re-aplicar si se re-descarga el modelo
El template vive en
`~/.lmstudio/models/lmstudio-community/Qwen3.5-9B-MLX-4bit/chat_template.jinja` (local, NO git/Drive).
Copia parcheada en este repo: `qwen35-9b-chat_template-nothink.jinja` (cópiala encima).
