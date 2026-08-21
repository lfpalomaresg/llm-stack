# Hilo de conversación · Stack LLM para MacBook Pro M4 Max 36GB

> Documento de referencia para revisión externa (Claude Opus, GPT-4, Gemini Pro, etc.).
> Generado el 1 de agosto de 2026.
> Conversación entre un usuario (Luis) y un asistente AI (MiniMax-M3 vía Ollama cloud).

---

## 0. Contexto del usuario

| Dato | Valor |
|---|---|
| **Equipo** | MacBook Pro M4 Max |
| **RAM unificada** | 36 GB |
| **CPU** | 14 núcleos |
| **Objetivo principal** | Stack multiagente para desarrollo con agentes IA (opencode, hermes) |
| **Objetivo secundario** | Experimentación con modelos locales |
| **Objetivo terciario** | Producción / self-hosted API |
| **Integración crítica** | opencode y hermes deben detectar el servidor sin fricción |
| **Suscripciones actuales** | ChatGPT, Claude (Pro o Max), Gemini, OpenRouter |
| **Planes próximos** | Vercel + Supabase (presupuesto ajustado) |
| **Miedos principales** | (a) sustos de facturas API (b) congelamiento de Ollama cloud por rate limit |
| **Preferencia de pago cloud** | Ollama cloud NO (ni free ni pago). OpenRouter sí, con límite duro. |
| **Idiomas** | Multilingüe (español principalmente) |

---

## 1. Discusión inicial · Ollama vs LM Studio vs LMX

### Primer malentendido
El usuario menciona "LMX" como servidor Apple Silicon. Se aclara que se refiere a **MLX** (framework de Apple Machine Learning Research) + servidores que lo envuelven (`mlx-lm`, `mlx-serve`, `omlx`, `macMLX`).

### Decisión base
**Ollama sigue como servidor principal** por madurez, OpenAI-compatible nativo, ecosistema.
**MLX se añade como acelerador opcional** para modelos grandes o prompt processing.
**LM Studio queda como banco de pruebas visual** (no como servidor de producción).

### Reglas de oro para 36 GB
- 7B: 1-2 simultáneos sin problema
- 14B: solo, sin combinar con 32B
- 32B: modo "serious", descarga todo antes
- Embeddings (~270-700 MB): permanente, no afecta
- 70B+: no cabe

---

## 2. Catálogo MLX inicial (sesgo hacia Qwen)

### Reconocimiento del sesgo
El usuario identifica correctamente que las recomendaciones iniciales están sesgadas hacia Qwen. Se reconoce:
- No es por superioridad absoluta
- Es por familiarity + ecosistema maduro + fácil de recomendar
- Modelos como Codestral, Phi-4, Gemma 2, DeepSeek, Pixtral, GLM fueron subestimados

### Catálogo expandido por tarea

#### 🔧 Coding agents
| # | Modelo | VRAM Q4 | Punto fuerte real |
|---|---|---|---|
| 1 | `mlx-community/Qwen2.5-Coder-32B-Instruct-4bit` | ~20 GB | El rey actual en coding open-weight |
| 2 | `mlx-community/Codestral-22B-v0.1-4bit` | ~13 GB | Mistral, supera a Qwen 14B en HumanEval |
| 3 | `mlx-community/DeepSeek-Coder-V2-Lite-Instruct-4bit` | 16B MoE / 2.4B activo / ~10 GB | MoE eficiente |
| 4 | `mlx-community/Qwen2.5-Coder-14B-Instruct-4bit` | ~9 GB | Sweet spot conocido |
| 5 | `mlx-community/Mixtral-8x7B-Instruct-v0.1-4bit` | 8x7B MoE / ~24 GB | MoE veterano |
| 6 | `mlx-community/StarCoder2-15B-Instruct-4bit` | ~9 GB | Code-first puro |
| 7 | `mlx-community/Qwen2.5-Coder-7B-Instruct-4bit` | ~4.5 GB | Default diario |
| 8 | `mlx-community/granite-20b-code-instruct-4bit` | ~12 GB | IBM, enterprise Java/Go |
| 9 | `mlx-community/Phi-3.5-mini-instruct-4bit` | ~2.5 GB | Compacto |

#### 🧠 Razonamiento / Planning
| # | Modelo | VRAM Q4 | Notas |
|---|---|---|---|
| 1 | `Qwen2.5-32B-Instruct-4bit` | ~20 GB | Lo mejor que cabe |
| 2 | `Mistral-Small-24B-Instruct-2501-4bit` | ~14 GB | Sólido, agentic |
| 3 | `Phi-4-14B-Instruct-4bit` | ~9 GB | **Sleeper hit Microsoft** |
| 4 | `gemma-2-27b-it-4bit` | ~17 GB | **Google subestimado** |
| 5 | `DeepSeek-V2-Lite-Chat-4bit` | 16B MoE / ~10 GB | MoE razonador |
| 6 | `Qwen2.5-14B-Instruct-4bit` | ~9 GB | Versátil |
| 7 | `Mixtral-8x7B-Instruct-4bit` | ~24 GB | Buen razonador MoE |
| 8 | `gemma-2-9b-it-4bit` | ~6 GB | Google sólido |

#### 💬 Chat / Redacción
- `Mistral-Small-24B` (estilo menos AI-ish)
- `gemma-2-27b` (Google, muy pulido)
- `Phi-4-14B` (sorprendentemente bueno)
- `Command-R-Plus` (Cohere, multilingüe top)

#### 🛠️ Tool calling
| # | Modelo | VRAM Q4 | Notas |
|---|---|---|---|
| 1 | `Qwen2.5-14B-Instruct-4bit` | ~9 GB | Top tool use |
| 2 | `Mistral-Small-24B-Instruct-4bit` | ~14 GB | Excelente JSON output |
| 3 | `functionary-7b-v3.2-4bit` | ~4.5 GB | **Diseñado para function calling** |
| 4 | `Hermes-3-Llama-3.1-8B-4bit` | ~5 GB | Nous, tool use + JSON |
| 5 | `ToolACE-8B-4bit` | ~5 GB | Nuevo, agents |

#### 🔍 Embeddings
| # | Modelo | Tamaño | Notas |
|---|---|---|---|
| 1 | `bge-m3-4bit` | ~600 MB | Multilingüe top |
| 2 | `nomic-embed-text-v1.5-4bit` | ~270 MB | Estándar |
| 3 | `mxbai-embed-large-v1-4bit` | ~670 MB | Top MTEB inglés |
| 4 | `e5-mistral-7b-instruct-4bit` | ~4.5 GB | **Embedding con LLM, premium** |
| 5 | `snowflake-arctic-embed-4bit` | ~270 MB | Snowflake |
| 6 | `gte-Qwen2-7B-instruct-4bit` | ~4.5 GB | Alibaba GTE |

#### 🎯 Reranking
- `bge-reranker-v2-m3-4bit` (multilingüe top)
- `bge-reranker-large-4bit` (inglés)
- `jina-reranker-4bit` (sólido)
- `mxbai-rerank-large-v1-4bit` (nuevo, competitivo)

#### 📊 Vision / Multimodal
| # | Modelo | VRAM | Notas |
|---|---|---|---|
| 1 | `Qwen2.5-VL-7B-Instruct-4bit` | ~4.5 GB | Top multimodal open |
| 2 | `Qwen2.5-VL-32B-Instruct-4bit` | ~20 GB | Cabría pero quita mucho |
| 3 | `Pixtral-12B-4bit` | ~7 GB | **Mistral, excelente en docs** |
| 4 | `llava-1.5-13b-4bit` | ~8 GB | Veterano |
| 5 | `llava-v1.6-mistral-7b-4bit` | ~4.5 GB | LLaVA + Mistral |

---

## 3. Modelo del asistente (MiniMax-M3)

El usuario pregunta por "minimax-m3" pensando que es externo. Se aclara que es el modelo con el que está hablando en ese momento.

**Identificado en system prompt:** `minimax-m3:cloud` corriendo vía Ollama cloud.

**Información verificable del modelo:**
- Desarrollador: MiniMax
- Versión: M3
- Conocimiento cutoff: enero 2026
- Empresa fundada early 2022, foco AGI
- Licencia: open weight
- HuggingFace: `MiniMaxAI/MiniMax-M3` y `unsloth/MiniMax-M3`

---

## 4. MiniMax-M3 · Especificaciones verificadas

| Spec | Valor |
|---|---|
| Parámetros totales | ~428B |
| Parámetros activados | ~23B (MoE) |
| Context | 1M tokens |
| Modalidad | **Nativo multimodal** (texto+visión+audio desde pre-train) |
| Fortalezas oficiales | "Coding & Agentic Frontier", MSA, multimodal |
| Licencia | Open weight |

### Versiones disponibles en MLX/HF
| Versión | Tamaño | Cabe en 36 GB | Notas |
|---|---|---|---|
| `MiniMax-M3-MLX-4bit` (pipenetwork) | ~150 GB | ❌ | Balanceada |
| `MiniMax-M3-MLX-3bit` (pipenetwork) | ~110 GB | ❌ | Smallest, text-only |
| `MiniMax-M3-oQ4` (unigilby) | ~228 GB | ❌❌ | 4-bit oMLX |
| `MiniMax-M3-MLX-Q8.5` (inferencerlabs) | ~422 GB | ❌❌❌ | Necesita M3 Ultra 512 GB |
| GGUF 5-bit (unsloth) | enorme | ❌ | Para servidores |

**Confirmación oficial:** El modelo requiere **Mac Studio M3 Ultra 512 GB** para correr a 19 tok/s. No viable en M4 Max 36 GB.

### Conclusión
- **MiniMax-M3 full NO es viable local** en 36 GB.
- **Plan A:** usar M3 vía cloud (Z.ai API o OpenRouter) + M2.7 local como fallback offline.
- **Plan C:** probar 3-bit con offload a SSD (dolorosamente lento, no usable diario).

---

## 5. Arquitectura multiagente propuesta

### Estructura de 3 capas
```
CAPA 1 · ORQUESTADOR
  - Decide qué agente llamar, en qué orden, con qué modelo
  - MLX: Phi-4-14B o Mixtral-8x7B (razonamiento puro)
  - Cloud: Claude-3.5-Sonnet, MiniMax-M3, GLM-5.2

CAPA 2 · EJECUCIÓN (agentes especializados)
  - Coding, Reasoning, Vision, RAG, Tool calling, Chat, Embeddings, Math

CAPA 3 · REVISIÓN
  - Recibe outputs de todos los demás
  - MLX: Qwen2.5-32B o Gemma2-27B
  - Cloud: Claude-3.5-Sonnet, GPT-4-Turbo, GLM-5.2
```

### 3 modos de servir modelos
| Backend | Puerto | Para qué |
|---|---|---|
| Local MLX | `localhost:11435/v1` | Modelos MLX nativos, máximo rendimiento M-series |
| Local Ollama | `localhost:11434/v1` | Modelos GGUF, gestión fácil, embeddings |
| Cloud / API | remoto | MiniMax-M3, Claude, GPT-4, Gemini |

### Soporte en opencode y hermes
- **OpenCode:** soporta múltiples providers (Ollama, OpenAI, Anthropic, custom). NO tiene orquestador multiagente nativo, se monta por encima con scripts/LangGraph/CrewAI.
- **Hermes:** más flexible, soporta function calling robusto, permite definir tools custom que llaman a otros modelos.

### Frameworks de orquestación posibles
- LangGraph (Python) - máxima flexibilidad
- CrewAI - más opinado, rápido de montar
- Smolagents (HuggingFace) - minimalista, MLX-friendly
- Script propio - máximo control

---

## 6. OpenRouter como unificador

### Por qué OpenRouter
- **Un solo endpoint**, una sola API key, todos los modelos
- Cambias de modelo cambiando el string
- Compatible con opencode y hermes

### Modelos disponibles en OpenRouter relevantes

#### Top tier (revisor + orquestador)
| Modelo | Provider | Coste/M out | Punto fuerte |
|---|---|---|---|
| `anthropic/claude-3.5-sonnet` | Anthropic | $15.00 | Best coding agent comercial |
| `openai/gpt-4o` | OpenAI | $10.00 | Multimodal nativo |
| `openai/o1` | OpenAI | $60.00 | Reasoning mode |
| `openai/o1-mini` | OpenAI | $12.00 | Reasoning barato |
| `google/gemini-2.0-flash` | Google | $0.30 | Best price/performance, 1M context |
| `google/gemini-2.0-pro` | Google | $5.00 | Pro quality |
| `MiniMax/minimax-m3` | MiniMax | varies | 1M context, multimodal |
| `deepseek/deepseek-r1` | DeepSeek | $2.19 | Reasoning open-weight comparable a o1 |
| `qwen/qwen-2.5-coder-32b-instruct` | Alibaba | $0.40 | Coding serio barato |
| `mistralai/codestral-22b` | Mistral | bajo | Coding |
| `perplexity/sonar-pro` | Perplexity | $15.00 | Research con búsqueda web |
| `nousresearch/hermes-3-llama-3.1-405b` | Nous | medio | Best open-weight en OpenRouter |

---

## 7. GLM-5.2 · El modelo que el usuario pidió que revisara

### Especificaciones verificadas
| Spec | Valor |
|---|---|
| Desarrollador | Z.ai (Zhipu AI, Beijing) |
| Release | 16 junio 2026 |
| Parámetros totales | 744B (MoE) |
| Parámetros activos | 40B por token |
| Context | 1M tokens (con Index/MSA) |
| Licencia | MIT (open weight) |
| Pricing OpenRouter | $1.40/M input · $4.40/M output |
| Foco oficial | "Agentic & tools", "long-horizon tasks" |
| MLX | ✅ `mlx-community/GLM-5.2-DQ4plus-q8` (para M3 Ultra 512 GB) |

### Comparativa 1M context · Club exclusivo
| Modelo | Params activos | Open weight | Coste/M out | Calidad coding |
|---|---|---|---|---|
| **GLM-5.2** | 40B | ✅ | $4.40 | ⭐⭐⭐⭐⭐ |
| **MiniMax-M3** | 23B | ✅ | varies | ⭐⭐⭐⭐⭐ |
| **Gemini 2.0 Flash** | — | ❌ | $0.30 | ⭐⭐⭐ |
| Claude 3.5 Sonnet | — | ❌ (200k) | $15.00 | ⭐⭐⭐⭐⭐ |

**Conclusión:** GLM-5.2 es el modelo open-weight con 1M context más capaz ahora mismo (40B activos > 23B de MiniMax).

### Versión lite local
**`mlx-community/GLM-4-9B-Chat-1M`** es la joya:
- 9B parámetros
- 1.000.000 tokens de context
- ~6 GB VRAM Q4
- Cabe perfecto en M4 Max 36 GB
- **1M context en 9B es único en su tamaño**

### GLM-5.2 en arquitectura
- **Como revisor crítico:** mejor precio/calidad que Claude ($4.40 vs $15)
- **Como orquestador:** top en agentic, 1M context ve todo el proyecto
- **Como coding agent de producción:** compite con Qwen Coder 32B y Claude

---

## 8. Comparativa MiniMax-M3 vs GLM-5.2

### Compiten en
- Open weight con 1M context
- Posicionamiento "agentic/coding frontier"
- MoE eficiente
- Disponibles en OpenRouter
- Multimodal (M3 nativo profundo, GLM parcial)
- Open weight bajo licencia amigable

### Se diferencian en
| Dimensión | MiniMax-M3 | GLM-5.2 |
|---|---|---|
| Parámetros activos | 23B | 40B (casi 2x) |
| Capacidad bruta razonamiento | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Multimodalidad | ⭐⭐⭐⭐⭐ nativa | ⭐⭐⭐ |
| Velocidad por token | Más rápido | Más lento |
| Coste OpenRouter | Similar | Más barato |
| MSA (Sparse Attention) | ❌ | ✅ GLM patent |
| Ecosistema | Más grande | Más pequeño |
| Versión "lite" local útil | No | **Sí, GLM-4-9B-Chat-1M** |

### Cuál es mejor para qué
| Caso | Ganador |
|---|---|
| Razonamiento puro (math, lógica, planning) | **GLM-5.2** |
| Multimodal serio | **MiniMax-M3** |
| Coding 1M context | Empate |
| Velocidad/latencia | **MiniMax-M3** |
| Coste-eficiencia OpenRouter | **GLM-5.2** |
| Tool calling complejo | Empate |
| RAG contextos enormes | Empate |
| Local en tu Mac | **GLM-5.2** (tiene GLM-4-9B-Chat-1M) |
| Self-host futuro Mac Studio | **GLM-5.2** |

---

## 9. Cuestiones críticas resueltas en la conversación

### 9.1 Sobre `minimax-m3:cloud` en Ollama
- **Incertidumbre:** El system prompt indica `minimax-m3:cloud` corriendo vía Ollama
- **Realidad:** No se puede confirmar coste real (free tier, rate limits, facturación)
- **Recomendación:** Usuario debe verificar en su dashboard de Ollama
- **Decisión final del usuario:** **Ollama cloud queda descartado** (ni free ni pago) por experiencia previa de congelamiento por rate limit

### 9.2 Ollama solo local
- A partir de ahora, Ollama **solo sirve modelos GGUF locales**
- OpenRouter es **el único puente a cloud** (con control de gasto)
- MiniMax-M3 y otros se acceden vía OpenRouter o vía apps nativas

### 9.3 Planes de IA del usuario
| Plan | Coste | Uso |
|---|---|---|
| ChatGPT | suscripción fija | Chat directo |
| Claude Pro/Max | $20-100/mes | Chat directo |
| Gemini Advanced | suscripción fija | Chat directo |
| OpenRouter | free + paid opcional | API unificada |

**Recomendación:** bajar Claude Max a Claude Pro ($20/mes) si se reasigna presupuesto a Vercel+Supabase.

### 9.4 Mistral AI
- **Europeo (Francia)**, no americano
- Sede París, fundador Arthur Mensch (ex-DeepMind)
- Modelos: Mistral, Mixtral, Codestral, Pixtral, Mistral Large

### 9.5 Kimi K2
- **Moonshot AI (China)**, open weight
- 2M tokens de context
- Variantes: K2 y K2 Thinking
- En OpenRouter disponible
- Especialidad: agentic, coding, tool use, contextos enormes

---

## 10. Stack v3 · Arquitectura final decidida

### Tier 0 · SIEMPRE LOCAL (0 €, sin sustos)

| Agente | Modelo | Backend | VRAM |
|---|---|---|---|
| **Orquestador** | GLM-4-9B-Chat-1M | MLX | ~6 GB |
| **Coding principal** | Qwen 2.5 Coder 14B | MLX | ~9 GB |
| **Coding lite** | Qwen 2.5 Coder 7B | MLX | ~4.5 GB |
| **Reasoning** | Phi-4 14B | MLX | ~9 GB |
| **Vision** | Pixtral 12B | MLX | ~7 GB |
| **Function calling** | Functionary 7B v3.2 | MLX | ~4.5 GB |
| **RAG embeddings** | bge-m3 | Ollama | ~0.6 GB |
| **Reranker** | bge-reranker-v2-m3 | Ollama | ~0.6 GB |
| **Revisor** | GLM-4-9B-Chat-1M (mismo que orquestador) | MLX | (ya cargado) |

**Uso RAM total:** ~17-20 GB de 36 GB ✓
**Coste:** 0 €

### Tier 1 · CLOUD BAJO DEMANDA (con límite duro)

| Agente | Modelo | OpenRouter ID | Coste/M out |
|---|---|---|---|
| **Orquestador alternativo** | GLM-5.2 | `z-ai/glm-5.2` | $4.40 |
| **Multimodal cloud** | MiniMax-M3 | `MiniMax/minimax-m3` | varies |
| **2M context** | Kimi K2 | `moonshotai/kimi-k2` | bajo |
| **Reasoning mode** | DeepSeek R1 | `deepseek/deepseek-r1` | $2.19 |
| **Vision barata** | GPT-4o-mini | `openai/gpt-4o-mini` | $0.60 |
| **Research web** | Perplexity Sonar Pro | `perplexity/sonar-pro` | $15.00 |
| **Tool calling premium** | Claude 3.5 Sonnet | `anthropic/claude-3.5-sonnet` | $15.00 |
| **Revisor crítico** | GLM-5.2 | `z-ai/glm-5.2` | $4.40 |

**Activación:** solo bajo demanda del usuario o cuando Tier 0 falla 3 veces
**Límite duro OpenRouter:** $20-50/mes con alertas

---

## 11. Stack v4 · Mejoras identificadas

### Mejora 1 · Router de coste automático
Antes de cada llamada cloud, evalúa:
- Confianza del resultado local > 0.85 → no cloud
- Coste del mes > límite → no cloud
- Tarea crítica + local falló → cloud

### Mejora 2 · Modo híbrido inteligente
Cada agente tiene 3-4 niveles de fallback:
```
Coding Agent:
  1. Qwen 2.5 Coder 7B local
  2. Qwen 2.5 Coder 14B local
  3. Qwen 2.5 Coder 32B cloud
  4. GLM-5.2 cloud (solo crítico)
```

### Mejora 3 · Caché semántico
- Embeddings locales (bge-m3) para detectar respuestas similares
- Si similitud > 0.92, devuelve respuesta cacheada
- Ahorro enorme en trabajo repetitivo

### Mejora 4 · Métricas y observabilidad
- Dashboard SQLite con: timestamp, agent, model, tokens, cost, latency, success
- Visibilidad total desde día 1

### Mejora 5 · Agente guardián de presupuesto
- Vigila gasto en tiempo real
- Alerta por macOS notification
- Apaga cloud si superas límite
- Sugiere optimizaciones

---

## 12. Coste mensual realista

| Concepto | Coste |
|---|---|
| Electricidad Mac (~8h/día) | ~5-8 €/mes |
| Planes IA actuales | Lo que ya paga el usuario |
| Local stack (todo el tier 0) | **0 € adicional** |
| OpenRouter free tier | **0 €** |
| Cloud bajo demanda (si lo usa) | **0-30 €/mes con límite** |
| **Total adicional** | **5-40 €/mes** |

**Comparado con un setup API-only:** 5-10x más barato.

---

## 13. Otros modelos mencionados (mapa completo)

### 🇰🇷 Modelos asiáticos top
- **Kimi K2 / K2 Thinking** (Moonshot AI, China): 2M context, agentic
- **DeepSeek V3 / R1** (China): reasoning open-weight best-in-class
- **DeepSeek Coder V2** (China): coding MoE, multilingüe
- **Qwen 2.5 / Qwen 3** (Alibaba, China): familia completa
- **GLM-5.2** (Z.ai, China): agentic + 1M context
- **MiniMax-M3** (MiniMax, China): multimodal nativo
- **Yi-Lightning** (01.AI, China): subestimado
- **Baichuan 4** (China): veterano
- **ERNIE 4.5** (Baidu, China): multimodal chino
- **Hunyuan** (Tencent, China): multimodal, video
- **Solar Pro** (Upstage, Corea): coreano/inglés
- **HyperClova** (Naver, Corea): solo API
- **Sarvam** (India): multilingüe indio
- **Phi-4** (Microsoft Research Asia): sleeper hit
- **SEA-LION** (SEA): sudeste asiático

### 🇺🇸 Modelos americanos open-weight
- Llama 3.3 70B, Llama 3.1 405B (Meta)
- Codestral 22B (Mistral AI, Francia pero occidental)
- Mixtral 8x7B / 8x22B (Mistral)
- Mistral Large 2 (Mistral)
- Gemma 2 27B, Gemma 3 (Google)
- DBRX (Databricks): enterprise MoE
- Granite 3.0 (IBM): enterprise code
- Falcon 3 (TII, UAE): árabe
- OLMo 2 (Allen AI): 100% open
- Tulu 3 (Allen AI): fine-tunes
- StarCoder 2 (BigCode): code ético
- Command-R Plus (Cohere, Canadá): RAG
- Aya 23 (Cohere): 23 idiomas
- Hermes 3 (Nous Research): tool use
- Pixtral 12B (Mistral): multimodal

### 🇪🇺 Europeos
- Mistral AI (Francia)
- Aya 23 (Cohere, Canadá)
- Falcon 3 (TII, UAE)
- BLOOM (BigScience, Francia)
- EuroLLM (Europa)

### Especializados
- Codestral 22B (coding)
- DeepSeek Coder V2 Lite (coding MoE)
- Qwen 2.5-Math-7B (math)
- InternVL2 (vision)
- Molmo 72B (vision + texto)
- BGE / GTE / E5 (embeddings)
- Qwen2-VL / Qwen2.5-VL (vision)
- Llama 3.2 Vision (vision)
- Pixtral 12B (vision)
- Functionary 7B v3.2 (function calling)
- ToolACE 8B (function calling)
- Nous Hermes 3 (tool use)
- WizardLM 2 (instruction following)
- Yi-Coder (coding)
- OpenCoder (coding open)
- Granite Code (coding enterprise)
- StarCoder 2 (coding ético)
- Code Llama 70B (coding)

---

## 14. Decisiones finales del usuario

| Decisión | Valor |
|---|---|
| Ollama cloud | ❌ Descartado por completo |
| OpenRouter | ✅ Con límite duro de gasto |
| MiniMax-M3 | ✅ Incluido (cloud) |
| GLM-5.2 | ✅ Incluido (cloud, orquestador y revisor alternativo) |
| GLM-4-9B-Chat-1M | ✅ Local, orquestador y revisor default |
| Kimi K2 | ✅ Incluido (cloud, 2M context) |
| Plan Claude | Pendiente bajar de Max a Pro |
| Vercel + Supabase | Próximamente, reasignar presupuesto |
| Miedos | (a) cargos API sorpresa (b) congelamiento Ollama rate limit |

---

## 15. Próximos pasos

1. Verificar coste real de OpenRouter free tier
2. Descargar `mlx-community/GLM-4-9B-Chat-1M-4bit` (la joya local)
3. Configurar OpenCode y Hermes apuntando a:
   - Ollama local: `http://localhost:11434/v1` (modelos GGUF)
   - MLX local: `http://localhost:11435/v1` (modelos MLX)
   - OpenRouter: `https://openrouter.ai/api/v1` (cloud, con límite)
4. Decidir framework de orquestación (LangGraph, CrewAI, script propio)
5. Implementar mejoras v4 (router de coste, caché, métricas, guardian)
6. Test A/B entre modelos locales y cloud en tareas reales

---

## 16. Preguntas abiertas para revisión externa

1. ¿El stack v3 cubre los casos de uso principales del usuario?
2. ¿Las mejoras v4 son las más relevantes o hay otras prioritarias?
3. ¿La distribución Tier 0/Tier 1 es la adecuada para el presupuesto?
4. ¿Hay algún modelo local (MLX) que debería estar en Tier 0 y no está?
5. ¿El plan de fallback (7B → 14B → 32B cloud → GLM-5.2) es razonable?
6. ¿La elección de GLM-4-9B-Chat-1M como orquestador es la mejor, o hay alternativa?
7. ¿El límite de $20-50/mes cloud es realista o muy ajustado?
8. ¿La arquitectura multiagente con opencode/hermes es la más práctica, o hay alternativa mejor?
9. ¿Cómo integrar Kimi K2 efectivamente sin que sea un modelo más "olvidado"?
10. ¿Qué framework de orquestación recomendar (LangGraph, CrewAI, otro)?

---

*Fin del documento. Generado el 1 de agosto de 2026.*
