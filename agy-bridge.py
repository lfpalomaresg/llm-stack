#!/usr/bin/env python3
"""
agy-bridge — puente HTTP compatible con OpenAI (/v1/chat/completions) que expone
gemini-free / gpt-oss-free / auditor-free como MODELOS de verdad, no solo como
destinos de enrutador-ia. Necesario porque `agy` (Antigravity CLI) no tiene modo
servidor: es un CLI de un solo disparo, y LiteLLM/opencode solo saben hablar HTTP.

Por qué existe (21/08): Claude Code y hermes llegan a `agy` porque delegan vía
`enrutador-ia` (Bash → enrutar.sh). opencode habla DIRECTO con LiteLLM — nunca pasa
por ese script — así que sin este puente, su agente `revisor` (auditor) no podía
llegar a `agy` de ninguna manera, por mucho que enrutador-ia ya lo soportara.

Arquitectura: este proceso escucha en localhost:4010. LiteLLM lo registra como un
model_name más (api_base apuntando aquí) — sigue habiendo "un solo endpoint"
(:4000) desde el punto de vista de los clientes (opencode, hermes, scripts); este
puente es una pieza interna del stack, igual que LM Studio.

Streaming (2026-11-03): `agy` emite NDJSON con `--output-format stream-json`; cada
`step_update` trae un `text_delta`. Este puente lo traduce a SSE (`text/event-stream`,
formato `chat.completion.chunk`) para que opencode/LiteLLM consuman `stream:true` sin
esperar la respuesta completa. Si agy no emite nada, se aplica el mismo respaldo
visible que en modo no-stream.

Misma disciplina que el resto del stack: SIN fallbacks silenciosos. Si `agy` falla
y hay respaldo (auditor-free → GLM vía el propio LiteLLM en :4000), el aviso queda
tanto en el log de este proceso como en el contenido devuelto — nunca oculto.
"""

import json
import subprocess
import json
import time
import uuid

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()

AGY_BIN = "agy"
LITELLM_URL = "http://localhost:4000/v1/chat/completions"
LITELLM_KEY = "proxy"
AGY_TIMEOUT = 180

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

MODELOS = {
    "gpt-oss-free": {"agy_model": "gpt-oss-120b-medium", "fallback": None},
    "gemini-free": {"agy_model": None, "fallback": "gemini-cli"},
    "auditor-free": {"agy_model": "gpt-oss-120b-medium", "fallback": "cloud-coder"},
}


def _extraer_prompt(messages):
    system = ""
    user_parts = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if isinstance(content, list):  # formato multi-parte
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        if role == "system":
            system = content
        else:
            user_parts.append(content)
    return system, "\n\n".join(user_parts)


def _llamar_agy(prompt, agy_model, system=""):
    """Devuelve (ok, texto, usage_dict) — nunca lanza excepción hacia arriba."""
    cmd = [AGY_BIN, "-p", prompt, "--output-format", "json"]
    if agy_model:
        cmd += ["--model", agy_model]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return False, f"agy no disponible: {e}", {}
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        return False, f"agy devolvió salida no-JSON (rc={r.returncode}): {r.stdout[:300]}", {}
    if d.get("status") != "SUCCESS":
        return False, f"agy status={d.get('status')} (rc={r.returncode})", {}
    return True, d.get("response", "(respuesta vacía)").rstrip(), d.get("usage", {})


def _stream_agy(prompt, agy_model, usage_out):
    """Genera deltas de texto desde el NDJSON de `agy --output-format stream-json`.

    `usage_out` se rellena con el usage del evento `result` (dict mutable).
    Lanza RuntimeError si agy termina sin éxito y no llegó a emitir texto.
    """
    cmd = [
        AGY_BIN, "-p", prompt,
        "--output-format", "stream-json",
        "--print-timeout", f"{AGY_TIMEOUT}s",
    ]
    if agy_model:
        cmd += ["--model", agy_model]

    proc = subprocess.Popen(
        cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    emitido = False
    status = None
    error = None
    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = ev.get("event")
            if kind == "step_update":
                delta = (ev.get("step_update") or {}).get("text_delta")
                if delta:
                    emitido = True
                    yield delta
            elif kind == "result":
                res = ev.get("result") or {}
                status = res.get("status")
                usage = res.get("usage") or {}
                if usage:
                    usage_out.update(usage)
                # Modelos que no mandan deltas: se entrega la respuesta final de una vez.
                if not emitido and res.get("response"):
                    emitido = True
                    yield res["response"]
                if status not in (None, "SUCCESS"):
                    error = res.get("error") or f"agy status={status}"
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
        try:
            rc = proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            rc = proc.wait()
        if rc != 0 and error is None:
            stderr = (proc.stderr.read() or "")[:300] if proc.stderr else ""
            error = f"agy terminó con rc={rc}: {stderr}".strip()
        if proc.stderr is not None:
            proc.stderr.close()

    if error and not emitido:
        raise RuntimeError(error)


def _llamar_gemini_cli(prompt):
    """Respaldo de gemini-free: mismo comando que enrutar.sh (gemini destino)."""
    cmd = ["gemini", "--skip-trust", "--approval-mode", "plan", "-p", prompt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return False, f"gemini CLI no disponible: {e}"
    if r.returncode != 0:
        return False, f"gemini CLI falló (rc={r.returncode}): {r.stderr[:300]}"
    return True, r.stdout.strip()


def _llamar_glm(messages):
    """Respaldo de auditor-free: reusa el propio LiteLLM (:4000, alias cloud-coder) —
    no reimplementa la llamada a OpenRouter, que ya vive en litellm.config.yaml."""
    try:
        resp = httpx.post(
            LITELLM_URL,
            headers={"Authorization": f"Bearer {LITELLM_KEY}"},
            json={"model": "cloud-coder", "messages": messages},
            timeout=120,
        )
        resp.raise_for_status()
        d = resp.json()
        return True, d["choices"][0]["message"]["content"], d.get("usage", {})
    except Exception as e:
        return False, f"respaldo a GLM también falló: {e}", {}


def _openai_response(model, content, usage_agy=None, usage_glm=None):
    prompt_tokens = (usage_agy or {}).get("input_tokens") or (usage_glm or {}).get("prompt_tokens") or 0
    completion_tokens = (usage_agy or {}).get("output_tokens") or (usage_glm or {}).get("completion_tokens") or 0
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _sse_frame(cid, created, model, delta, finish_reason=None, usage=None):
    obj = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": delta,
            "finish_reason": finish_reason,
        }],
    }
    if usage is not None:
        obj["usage"] = usage
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _stream_response(model, cfg, messages, prompt, include_usage=False):
    """Generador SSE compatible con OpenAI (`chat.completion.chunk`)."""
    cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    yield _sse_frame(cid, created, model, {"role": "assistant", "content": ""})

    emitido = False
    fallo = ""
    usage: dict = {}

    try:
        for trozo in _stream_agy(prompt, cfg["agy_model"], usage):
            emitido = True
            yield _sse_frame(cid, created, model, {"content": trozo})
    except Exception as e:  # noqa: BLE001 - cualquier fallo de agy cae al respaldo
        fallo = str(e)
        print(f"[agy-bridge] ⚠️  {model}: stream de agy falló ({fallo}) — respaldo={cfg['fallback']}")

    if not emitido:
        if cfg["fallback"] == "cloud-coder":
            ok2, texto2, usage2 = _llamar_glm(messages)
            marca = f"\n\n--- [{model}] agy falló ({fallo or 'sin respuesta'}): se usó GLM (cloud-coder) como respaldo ---"
            if ok2:
                usage = usage2
                yield _sse_frame(cid, created, model, {"content": texto2 + marca})
            else:
                yield _sse_frame(cid, created, model, {
                    "content": f"Fallo total: agy falló ({fallo or 'sin respuesta'}) y {texto2}",
                })
        elif cfg["fallback"] == "gemini-cli":
            ok2, texto2 = _llamar_gemini_cli(prompt)
            marca = f"\n\n--- [{model}] agy falló ({fallo or 'sin respuesta'}): se usó la API de pago (gemini) como respaldo ---"
            if ok2:
                yield _sse_frame(cid, created, model, {"content": texto2 + marca})
            else:
                yield _sse_frame(cid, created, model, {
                    "content": f"Fallo total: agy falló ({fallo or 'sin respuesta'}) y gemini CLI también: {texto2}",
                })
        else:
            yield _sse_frame(cid, created, model, {
                "content": f"agy falló ({fallo or 'sin respuesta'}) y {model} no tiene respaldo de pago a propósito.",
            })
    elif fallo:
        print(f"[agy-bridge] {model}: stream parcial de agy ({fallo}); no se duplica con respaldo")

    if include_usage and usage:
        prompt_tokens = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
        completion_tokens = usage.get("output_tokens") or usage.get("completion_tokens") or 0
        yield _sse_frame(cid, created, model, {}, None, {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        })

    yield _sse_frame(cid, created, model, {}, "stop")
    yield "data: [DONE]\n\n"


@app.get("/v1/models")
def listar_modelos():
    return {"object": "list", "data": [{"id": m, "object": "model"} for m in MODELOS]}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    model = body.get("model", "")
    messages = body.get("messages", [])
    system, prompt = _extraer_prompt(messages)

    cfg = MODELOS.get(model)
    if not cfg:
        return JSONResponse(status_code=404, content={"error": f"Modelo desconocido en agy-bridge: {model}"})

    if body.get("stream"):
        include_usage = bool((body.get("stream_options") or {}).get("include_usage"))
        print(f"[agy-bridge] {model}: stream SSE hacia el cliente")
        return StreamingResponse(
            _stream_response(model, cfg, messages, prompt, include_usage=include_usage),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    ok, texto, usage = _llamar_agy(prompt, cfg["agy_model"], system)
    if ok:
        print(f"[agy-bridge] {model}: respondido por agy ({cfg['agy_model'] or 'default'})")
        return _openai_response(model, texto, usage_agy=usage)

    print(f"[agy-bridge] ⚠️  {model}: agy falló ({texto}) — respaldo={cfg['fallback']}")

    if cfg["fallback"] == "cloud-coder":
        ok2, texto2, usage2 = _llamar_glm(messages)
        marca = f"\n\n--- [{model}] agy falló ({texto}): se usó GLM (cloud-coder) como respaldo ---"
        if ok2:
            return _openai_response(model, texto2 + marca, usage_glm=usage2)
        return _openai_response(model, f"Fallo total: agy falló ({texto}) y {texto2}", )

    if cfg["fallback"] == "gemini-cli":
        ok2, texto2 = _llamar_gemini_cli(prompt)
        marca = f"\n\n--- [{model}] agy falló ({texto}): se usó la API de pago (gemini) como respaldo ---"
        if ok2:
            return _openai_response(model, texto2 + marca)
        return _openai_response(model, f"Fallo total: agy falló ({texto}) y gemini CLI también: {texto2}")

    # Sin respaldo (gpt-oss-free): igual que enrutar.sh, error visible, sin inventar.
    return JSONResponse(status_code=502, content={
        "error": f"agy falló ({texto}) y gpt-oss-free no tiene respaldo de pago a propósito."
    })


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=4010, log_level="info")
