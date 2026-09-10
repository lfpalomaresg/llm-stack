# Nex-N2-mini — default NO-THINK (fix crítico de fluidez, 2026-09-10)

## Problema
Nex (orquestador) razona en voz alta por defecto → en el harness agéntico de opencode
(~14k tokens/vuelta) generaba una cadena de "thinking" larga y la volcaba al contenido →
cada vuelta tardaba 14-27s y salía sucia. opencode/hermes hablan directo con LiteLLM y NO
inyectan `/no_think` (eso solo lo hace enrutar.sh).

## Fix
En el chat_template.jinja del modelo, se invirtió el default de `enable_thinking`:

    ANTES: {%- if enable_thinking is defined and enable_thinking is false %}
    AHORA: {%- if enable_thinking is not defined or enable_thinking is false %}

Efecto: por DEFECTO Nex no piensa (directo, ~10x más rápido). Para forzar razonamiento
puntual, pasar enable_thinking=true (o el token /think). Nex es el ORQUESTADOR (delegación
rápida), no el razonador profundo (eso es cloud-reasoning/careo) → no-think por defecto es lo correcto.

## Medido (prompt 14k tokens)
- Con thinking (antes): 27s frío / 14,5s caliente, con thinking-dump.
- No-think (ahora): 13,1s frío / **2,4s caliente**, directo.

## ⚠️ Re-aplicar si se re-descarga Nex
El template vive en `~/.lmstudio/models/mlx-community/Nex-N2-mini-4bit-local/chat_template.jinja`
(local, NO git/Drive). Si se re-baja el modelo, re-aplicar el cambio de una línea de arriba,
o copiar `nex-chat_template-nothink.jinja` de este repo encima. Backup original: se regenera
al re-descargar; el modificado está aquí.
