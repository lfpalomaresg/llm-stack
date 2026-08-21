# Prompt para revisión del stack LLM con Claude Opus

> Archivo creado el 1 de agosto de 2026.
> Uso: copiar el contenido del bloque "PROMPT PRINCIPAL" (abajo) y pegarlo en Claude Opus / GPT-4 / Gemini Pro junto con el archivo `llm-stack-conversation.md`.

---

## PROMPT PRINCIPAL · Revisión completa

```
Voy a compartirte un documento markdown que describe un stack multiagente
LLM que estoy diseñando para mi MacBook Pro M4 Max 36GB / 14 núcleos.

Mi objetivo es montar un sistema multiagente para desarrollo con opencode
y hermes, con base en modelos LOCALES y cloud solo bajo demanda con
presupuesto cerrado.

CONTEXTO MIO (importante leerlo):
- MacBook Pro M4 Max, 36GB unified memory, 14 cores
- Ya tengo planes de: ChatGPT, Claude, Gemini, OpenRouter
- Voy a meter Vercel + Supabase pronto (presupuesto justo)
- Ya me ha pasado que Ollama cloud me congela por rate limit, NO lo quiero
- Tengo miedo a sustos de facturas por API
- Mi objetivo principal: coding agents. Secundario: experimentación.
  Terciario: algo de producción.
- Hablo español pero el sistema estará en inglés/multilingüe

EL DOCUMENTO:
[pega aquí el contenido de /Users/pifanmac/llm-stack/llm-stack-conversation.md]

LO QUE NECESITO DE TI:

1. AUDITORIA CRITICA del stack v3:
   - ¿Hay errores técnicos?
   - ¿Hay modelos que se me han escapado (especialmente en MLX para
     Apple Silicon)?
   - ¿El Tier 0 (local) y Tier 1 (cloud) están bien dimensionados?
   - ¿La elección de GLM-4-9B-Chat-1M como orquestador es correcta?
   - ¿El plan de fallback 7B→14B→32B→GLM-5.2 tiene sentido?

2. VALIDACION DE PRESUPUESTO:
   - ¿El límite de $20-50/mes cloud es realista o muy ajustado?
   - ¿Hay forma de reducir más el coste sin perder funcionalidad?
   - ¿Algún modelo de pago que merezca la pena incluir por precio/calidad?

3. RECOMENDACIONES DE MODELOS MLX:
   - Revisa HuggingFace (mlx-community) y dime si hay algún modelo
     reciente (junio-agosto 2026) que debería estar en mi Tier 0
   - ¿Hay algún modelo "lite" con context largo (>=128k) que me he
     perdido para local?
   - ¿Qué modelos de embeddings/reranking son ahora el estado del arte?

4. ARQUITECTURA:
   - ¿La estructura de 3 capas (orquestador → especializados → revisor)
     es la mejor para opencode/hermes?
   - ¿Qué framework de orquestación recomiendas: LangGraph, CrewAI,
     smolagents, script propio? Justifica.
   - ¿Cómo integrarías Kimi K2 efectivamente sin que sea un "modelo más
     olvidado"?

5. MEJORAS AL v4:
   - Las 5 mejoras propuestas (router de coste, modo híbrido,
     caché semántico, métricas, guardian de presupuesto) son las más
     relevantes? ¿Falta alguna crítica?

6. TOP 5 MODELOS MLX PARA MI SETUP (36GB, M4 Max):
   Si tuvieras que recomendar SOLO 5 modelos en MLX que cubrieran el
   90% de mis casos de uso, ¿cuáles serían? Justifica cada uno.

7. RIESGOS QUE NO HE VISTO:
   - ¿Hay algún riesgo técnico, operativo o de seguridad que se me
     haya escapado?
   - ¿Algo de licenciamiento que deba tener en cuenta con los modelos
     open-weight?

FORMATO DE RESPUESTA QUE PREFIERO:
- Directo, sin floritura
- Si ves un error, dilo sin tapujos
- Si estás de acuerdo con algo, dilo brevemente
- Tablas y listas cuando aporten
- Tono de colega que sabe, no de consultor
- Si no sabes algo, dilo (no inventes)
- En español
```

---

## VARIANTE CORTA · Si quieres algo más directo

```
He diseñado este stack LLM multiagente:
[pega el doc]

Stack: M4 Max 36GB, opencode+hermes, base local + cloud bajo demanda.
Presupuesto cloud: $20-50/mes máximo.

Revisa y dime:
1. ¿3 errores garrafales que veas?
2. ¿3 modelos MLX que faltan en Tier 0?
3. ¿3 mejoras críticas al stack v4?
4. ¿Orquestador con LangGraph o CrewAI?
5. ¿Qué modelo MLX me recomiendas como "el definitivo"?

Respuesta concisa, máximo 800 palabras, español.
```

---

## VARIANTE ADVERSARIAL · La crítica más dura

```
ROL: Eres un crítico senior de arquitectura de IA. No me adules, no me
vendas. Tu trabajo es encontrar lo que está mal.

CONTEXTO: Stack LLM multiagente para M4 Max 36GB, opencode+hermes,
presupuesto cloud $20-50/mes, miedo a sustos de API.

DOCUMENTO: [pega el doc]

TAREAS:
1. Enumera 5 debilidades reales del stack v3 (ordenadas por gravedad)
2. ¿Qué modelo caro está justificado y cuál sobra?
3. ¿Qué decisión parece "smart" pero es un error en producción?
4. ¿Cómo romperías mi presupuesto en 30 días si quisieras hacerme
   daño con este setup?
5. ¿Qué CloudLock-in me he metido sin darme cuenta?

Tono: colega que no se corta, pero con fundamento técnico.
Máximo 1200 palabras, español.
```

---

## ADAPTACIONES POR MODELO

### Claude Opus / Sonnet
- Pega prompt + doc en un solo mensaje
- Opus maneja contexto largo perfectamente
- Si usas Sonnet, añade al final: "Sé conciso, máximo 1500 palabras"

### GPT-4 / GPT-4o
- Añade: "Antes de responder, enumera los 3 puntos más críticos que
  ves y luego desarrolla. Prioriza acción sobre explicación."

### Gemini Pro
- Añade: "Si encuentras información desactualizada en tu knowledge,
  búscala en web. Cita fuentes."

### DeepSeek R1
- Añade: "Pienso paso a paso, muestro tu reasoning interno si lo crees
  útil, y terminas con acción concreta."

---

## CÓMO PROCEDER

1. Elige una de las 3 variantes (principal / corta / adversarial)
2. Abre Claude Opus (o el modelo que prefieras)
3. Pega el prompt elegido
4. Pega el contenido de `llm-stack-conversation.md`
5. Envía y espera respuesta
6. Vuelve con la respuesta y la analizamos juntos

