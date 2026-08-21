#!/usr/bin/env python3
"""
MCP server que expone (1) los modelos locales del LLM Stack v5 (LM Studio +
LiteLLM) y (2) el catálogo libre de OpenRouter, como herramientas directas
para Claude Code, sin pasar por el pipeline de enrutador-ia (logging/
aprendizaje). Es una puerta de entrada ADICIONAL a proveedores que
enrutador-ia ya usa -- no reimplementa su lógica de negocio.

- ask_local_model: alias definidos en ~/llm-stack/litellm.config.yaml,
  servidos LOCALMENTE por LM Studio. Nunca sale de esta máquina.
- ask_openrouter_model: cualquier modelo del catálogo de OpenRouter (no solo
  los 4 alias cloud-* fijos de enrutador-ia), reutilizando la MISMA clave que
  ya usa el stack (almacén de opencode). Es tráfico a un proveedor EXTERNO:
  nunca mandar aquí datos personales o sensibles del trabajo (esa regla la
  aplica enrutador-ia con código; aquí es una convención que hay que
  respetar a mano al decidir usar esta tool).

Uso: registrado como MCP server stdio en Claude Code (ver README.md de esta
carpeta / plan de instalación).
"""

import json
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

LITELLM_BASE_URL = "http://localhost:4000/v1"
LITELLM_API_KEY = "lm-studio"  # mismo valor que litellm.config.yaml para modelos locales

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENCODE_AUTH_PATH = Path.home() / ".local/share/opencode/auth.json"

# Alias LOCALES permitidos (deben coincidir con litellm.config.yaml).
# Los alias cloud-* (OpenRouter, vía LiteLLM) quedan fuera a propósito: esos
# siguen gobernados por enrutador-ia, no por este MCP.
ALLOWED_MODELS = {
    "local-coder": "Qwen3-Coder-30B-A3B -- código",
    "local-general": "Qwen3.6-35B-A3B -- orquestador/chat/visión",
    "local-fast": "Qwen3-8B -- utilidad/consultas rápidas",
    "local-embed": "Qwen3-Embedding-0.6B -- RAG/embeddings",
    "local-worker": "DeepSeek-R1-0528-Qwen3-8B -- worker",
    "local-auditor": "Gemma-4-E4B-it OptiQ -- auditor sensible",
}

mcp = FastMCP("local-models")


def _get_openrouter_key() -> str | None:
    """Lee la clave de OpenRouter del almacén de opencode (misma fuente que usa enrutador-ia)."""
    try:
        data = json.loads(OPENCODE_AUTH_PATH.read_text())
        return data["openrouter"]["key"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return None


@mcp.tool()
def list_local_models() -> str:
    """Lista los modelos locales disponibles (servidos por LM Studio vía LiteLLM) y para qué sirve cada uno."""
    lineas = [f"- {alias}: {desc}" for alias, desc in ALLOWED_MODELS.items()]
    return "Modelos locales disponibles:\n" + "\n".join(lineas)


@mcp.tool()
def ask_local_model(model: str, prompt: str, system: str = "") -> str:
    """Pregunta algo a un modelo local (LM Studio vía LiteLLM), sin pasar por enrutador-ia.

    Úsalo para consultas puntuales y rápidas (resúmenes, lookups, borradores)
    donde no hace falta el logging/aprendizaje del enrutador. Para tareas que
    SÍ deban quedar registradas o que toquen datos sensibles del trabajo, usa
    la skill enrutador-ia en su lugar.

    Args:
        model: alias del modelo local. Debe ser uno de: local-coder, local-general,
            local-fast, local-embed, local-worker, local-auditor.
        prompt: el texto/pregunta a enviar al modelo.
        system: (opcional) mensaje de sistema para orientar la respuesta.
    """
    if model not in ALLOWED_MODELS:
        return (
            f"Modelo '{model}' no permitido en este MCP. "
            f"Alias válidos: {', '.join(ALLOWED_MODELS)}. "
            "Para modelos cloud (cloud-coder, cloud-vision, etc.) usa la skill enrutador-ia."
        )

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        resp = httpx.post(
            f"{LITELLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LITELLM_API_KEY}"},
            json={"model": model, "messages": messages},
            timeout=120,
        )
        resp.raise_for_status()
    except httpx.ConnectError:
        return (
            "No se pudo conectar con LiteLLM en localhost:4000. "
            "¿Está arrancado el LLM Stack? Prueba: ~/llm-stack/stack.sh start"
        )
    except httpx.HTTPStatusError as e:
        return f"Error HTTP {e.response.status_code} de LiteLLM: {e.response.text[:500]}"
    except httpx.TimeoutException:
        return "Timeout esperando respuesta del modelo local (120s). El modelo puede estar cargando en frío."

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        return f"Respuesta inesperada de LiteLLM: {data}"


@mcp.tool()
def ask_openrouter_model(model: str, prompt: str, system: str = "") -> str:
    """Pregunta algo a CUALQUIER modelo del catálogo libre de OpenRouter (no solo los 4 alias fijos de enrutador-ia).

    ⚠️ Esto sale de tu Mac hacia un proveedor externo (OpenRouter) y consume
    la clave de pago prepagada del stack. NO uses esta tool con datos
    personales o sensibles del trabajo -- para eso usa la skill
    enrutador-ia, que sí aplica esa regla en código. Úsala solo para probar
    modelos puntuales del catálogo (p.ej. uno recién salido) con contenido no
    sensible.

    Args:
        model: id del modelo tal como aparece en openrouter.ai/models
            (ej. "z-ai/glm-5.2", "moonshotai/kimi-k3", "qwen/qwen3-coder-next").
        prompt: el texto/pregunta a enviar al modelo.
        system: (opcional) mensaje de sistema para orientar la respuesta.
    """
    key = _get_openrouter_key()
    if not key:
        return (
            f"No se pudo leer la clave de OpenRouter de {OPENCODE_AUTH_PATH}. "
            "¿Sigue autenticado opencode? Prueba: opencode auth login"
        )

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        resp = httpx.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "messages": messages},
            timeout=120,
        )
        resp.raise_for_status()
    except httpx.ConnectError:
        return "No se pudo conectar con OpenRouter (¿sin internet?)."
    except httpx.HTTPStatusError as e:
        return f"Error HTTP {e.response.status_code} de OpenRouter: {e.response.text[:500]}"
    except httpx.TimeoutException:
        return "Timeout esperando respuesta de OpenRouter (120s)."

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        return f"Respuesta inesperada de OpenRouter: {data}"


if __name__ == "__main__":
    mcp.run()
