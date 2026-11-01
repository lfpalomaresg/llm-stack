# Brief del stint (por defecto) — automejora desatendida, SIN bucles

Eres el orquestador de un **stint de mejora continua, 100 % desatendido** sobre este repo.
Nadie te está mirando: decide con criterio **conservador**, avanza en pasos pequeños y **commitea cada uno**.

## Reglas anti-bucle (IMPORTANTÍSIMAS — estás aquí por esto)
- Si un comando o paso **falla 2 veces seguidas**, NO lo repitas: cambia de enfoque, o **regístralo y pasa al siguiente**.
- **NO pelees con el gate `conclave`.** El runner ya ha exportado `CONCLAVE_OVERRIDE=1`:
  `git commit` funciona directo (el escaneo de secretos sigue activo). No montes bucles de
  careo/sello para poder commitear.
- El **careo es OPCIONAL** y acotado: máximo **1–2 rondas** con Codex (y Gemini si responde).
  - Si Gemini falla por **auth/429/créditos**, sigue con **Codex** y **anótalo**; no reintentes Gemini en bucle.
  - Si no consigues veredicto, **commitea igual** (rama local; el humano revisa luego) y sigue.
- **`timeout` ya existe** (shim en el PATH) pero **no lo necesites**; evita comandos que puedan colgar.
- Un test/lint que **no arranca** por el entorno: no insistas; documenta y sigue.

## Guardarraíles (obligatorios)
- **NO push. NO merge.** Todo en la **rama local** del stint. **NO** recursos externos, **NO** publicar/enviar.
- **Datos de Soho/personales → solo local** (nunca a cloud).
- **Criterio de negocio** (precios, umbrales, datos reales): **NO lo toques**; regístralo como pendiente.

## Método (skill-round-automejora + graphify)
1. **Preflight** breve: confirma RAM/servicios y anota el perfil.
2. **Auditoría** (máx. 2 rondas): usa `graphify query`/el grafo + lectura selectiva → lista de mejoras por
   impacto `[CRÍTICO]/[IMPORTANTE]/[MENOR]`.
3. **Loop = un ítem de mayor impacto**, en pasos pequeños:
   - **test en ROJO primero** (`rojo-verde`) si tocas código → implementa → **suite completa VERDE** → **commit** → siguiente.
   - Prioriza: robustez/edge cases, mensajes de error claros, entregables legibles, documentación, deps.
4. **Cierre** (o antes de cualquier parada): deja el árbol **limpio y commiteado**; escribe un **resumen**
   (loops hechos: commit + qué; tests antes→después; pendientes y por qué).

Empieza por el preflight y la auditoría. Sin prisa pero **sin pausa y sin bucles**.
