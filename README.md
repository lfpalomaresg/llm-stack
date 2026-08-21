# LLM Stack v5

Un stack multiagente de IA corriendo por completo en local sobre una MacBook
Pro M4 Max de 36 GB, con escalado a la nube por criterio explícito (nunca
como fallback automático) y dos puertas de entrada distintas para
[Claude Code](https://claude.com/claude-code): una skill con logging y
reglas de datos sensibles, y un [MCP server](mcp-local-models/) propio para
consultas puntuales.

**📄 Documentación visual completa: [lfpalomaresg.github.io/llm-stack](https://lfpalomaresg.github.io/llm-stack/)**
— arquitectura, catálogo de modelos, orquestación agéntica, guardarraíles e
historial de incidentes.

## En una frase

Seis modelos MLX cuantizados servidos por [LM Studio](https://lmstudio.ai/),
unificados detrás de un proxy [LiteLLM](https://www.litellm.ai/) con API
compatible OpenAI, con roles agénticos fijos (orquestador, workers en
paralelo, auditor) y cuatro modelos de refuerzo en [OpenRouter](https://openrouter.ai/)
que solo entran por señal objetiva — nunca en silencio.

## Contenido de este repo

| Archivo | Qué es |
|---|---|
| [`litellm.config.yaml`](litellm.config.yaml) | Alias de modelos y enrutado. Cambiar un modelo = editar aquí, cero cambios en clientes. |
| [`stack.sh`](stack.sh) | Control de perfiles de RAM (arrancar/parar/cambiar perfil). |
| [`lock.sh`](lock.sh) | Lock file para evitar carreras entre perfiles concurrentes. |
| [`mcp-local-models/`](mcp-local-models/) | MCP server que expone los modelos locales y el catálogo libre de OpenRouter como herramientas para Claude Code. |
| [`llm-stack-v5.md`](llm-stack-v5.md) | Documento de arquitectura — la fuente de verdad del diseño. |
| [`sistema-agentico.md`](sistema-agentico.md) | Roles agénticos, perfiles de RAM, resultados de la batería de estrés. |
| [`llm-stack-conversation.md`](llm-stack-conversation.md) / [`prompt-revision-opus.md`](prompt-revision-opus.md) | Diario de diseño original (agosto 2026) e histórico de revisión externa. |
| `index.html` | La página de arriba — se sirve vía GitHub Pages. |

## Principios de diseño

- **Nadie carga modelos excepto LM Studio.** Los clientes (Claude Code,
  opencode, hermes) son clientes finos del proxy LiteLLM.
- **Sin fallbacks silenciosos.** Si un modelo no cabe en RAM, el error es
  visible y dice qué hacer — nunca una degradación silenciosa a un modelo
  peor.
- **Cloud nunca automático.** OpenRouter solo entra por decisión explícita:
  tests en rojo dos veces, contexto que no cabe, o carga multimodal pesada.
- **Presupuesto con techo físico.** Crédito de OpenRouter prepagado, sin
  auto-recarga — el susto de gasto es imposible, no solo improbable.
- **Revisor ≠ productor.** El auditor para material sensible es de una
  familia de modelos distinta a la que produjo el trabajo.

## Requisitos

- macOS con [LM Studio](https://lmstudio.ai/) sirviendo en `localhost:1234`.
- Python 3.11+ con `litellm` para el proxy (`.venv/` local, no versionado).
- Para el MCP server: `pip install -r mcp-local-models/requirements.txt`.

## Licencia

Sin licencia explícita — todos los derechos reservados por ahora.
