"""Registro de uso de LiteLLM — una línea JSON por petición, SOLO metadatos (2026-10-21).

Por qué: el registro del enrutador (`~/.local/state/enrutador-ia/registro.jsonl`) solo se
alimenta cuando alguien usa `enrutar.sh`, y desde octubre el tráfico real (opencode,
hermes, laboratorio) va directo a LiteLLM: el registro llevaba muerto desde el 04/10.
Este callback anota cada petición del proxy y `aprender.sh` lo agrega.

Frontera de datos: NUNCA se escribe el contenido (ni prompts, ni respuestas, ni el
mensaje de error, que puede citar el prompt). Solo alias, modelo, éxito, clase de error,
latencia, tokens y coste. Cualquier fallo del callback se traga: el proxy no puede caer
por culpa del registro.

Se carga desde `litellm.config.yaml` → `litellm_settings.callbacks: registro_uso.registro`.
Tests: `test-registro-uso.py`.
"""
import json
import os
import time

from litellm.integrations.custom_logger import CustomLogger

RUTA = os.environ.get(
    "REGISTRO_USO_PATH", os.path.expanduser("~/.local/state/litellm/uso.jsonl")
)


def _get(d, *claves):
    for c in claves:
        if not isinstance(d, dict):
            return None
        d = d.get(c)
    return d


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _fila(kwargs, respuesta, inicio, fin, ok):
    kwargs = kwargs if isinstance(kwargs, dict) else {}
    uso = getattr(respuesta, "usage", None)
    try:
        latencia = round((fin - inicio).total_seconds(), 3)
    except Exception:
        latencia = None
    error = kwargs.get("exception")
    return {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "alias": _get(kwargs, "litellm_params", "metadata", "model_group"),
        "modelo": kwargs.get("model"),
        "ok": ok,
        "error": type(error).__name__ if (not ok and error is not None) else None,
        "latencia_s": latencia,
        "tokens_in": _num(getattr(uso, "prompt_tokens", None)),
        "tokens_out": _num(getattr(uso, "completion_tokens", None)),
        "coste_usd": _num(kwargs.get("response_cost")),
        "stream": bool(kwargs.get("stream")),
    }


def _anotar(fila):
    try:
        os.makedirs(os.path.dirname(RUTA), exist_ok=True)
        fd = os.open(RUTA, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    except Exception:
        pass


class RegistroUso(CustomLogger):
    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        try:
            _anotar(_fila(kwargs, response_obj, start_time, end_time, True))
        except Exception:
            pass

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        try:
            _anotar(_fila(kwargs, response_obj, start_time, end_time, False))
        except Exception:
            pass


registro = RegistroUso()
