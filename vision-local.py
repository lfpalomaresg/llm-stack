#!/usr/bin/env python3
# vision-local.py — análisis de imágenes en LOCAL sin atranques.
# El 35B multimodal se ahoga con imágenes GRANDES (cada una = miles de tokens de
# visión al trocearse en tiles). Este script REDIMENSIONA antes de enviar (lado
# largo <= MAXPX) y manda al 35B (local-general) por LiteLLM. Frontera de datos:
# 100% local, nada sale del Mac.
#
# Uso:   ~/llm-stack/.venv/bin/python vision-local.py "<pregunta>" img1 [img2 ...]
#   MAXPX=1024 para bajar más (menos tokens, menos detalle) · default 1568.
#   MODEL=cloud-vision para MiniMax (SOLO si NO es sensible).
import sys, os, io, json, base64, urllib.request, time
from PIL import Image

MAXPX = int(os.environ.get("MAXPX", "1568"))
MODEL = os.environ.get("MODEL", "local-general")
if len(sys.argv) < 3:
    sys.exit("uso: vision-local.py \"<pregunta>\" imagen1 [imagen2 ...]")
prompt, paths = sys.argv[1], sys.argv[2:]

def encode(p):
    im = Image.open(p).convert("RGB"); w, h = im.size
    if max(w, h) > MAXPX:
        r = MAXPX / max(w, h); im = im.resize((int(w * r), int(h * r)), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode(), (w, h), im.size

def ask(b64):
    content = [{"type": "text", "text": prompt},
               {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]
    payload = json.dumps({"model": MODEL, "temperature": 0.3, "max_tokens": 2000,
        "messages": [{"role": "user", "content": content}]}).encode()
    req = urllib.request.Request("http://localhost:4000/v1/chat/completions", data=payload,
        headers={"Content-Type": "application/json", "Authorization": "Bearer x"})
    r = json.loads(urllib.request.urlopen(req, timeout=300).read())
    return r["choices"][0]["message"].get("content", "")

# CLAVE (2026-08-30): procesar DE UNA EN UNA. Varias imágenes en una sola petición
# saturan el contexto del 35B (cada una se trocea en tiles) — fue la causa del bucle
# de hermes con 8 capturas. Una imagen por petición nunca satura.
for i, p in enumerate(paths, 1):
    b64, orig, new = encode(p)
    sys.stderr.write(f"[vision-local] {MODEL} · [{i}/{len(paths)}] {os.path.basename(p)} "
                     f"{orig[0]}x{orig[1]}->{new[0]}x{new[1]} ({len(b64)//1024}KB)\n")
    t0 = time.time()
    try:
        c = ask(b64)
    except Exception as e:
        print(f"\n## [{i}/{len(paths)}] {os.path.basename(p)} — ERROR: {e}"); continue
    sys.stderr.write(f"[vision-local]   {time.time()-t0:.1f}s\n")
    if len(paths) > 1:
        print(f"\n## [{i}/{len(paths)}] {os.path.basename(p)}\n")
    print(c if c else "(respuesta vacía — sube max_tokens o baja MAXPX)")
