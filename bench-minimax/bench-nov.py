#!/usr/bin/env python3
# bench-nov.py (2026-11-04) — MiniMax M3.1 Flash (pago) frente a MiniMax-M3 y DeepSeek V4.1-Flash-1017.
# SOLO datos ficticios: el banco oculto de cotejo-arquitecturas (proveedores y productos inventados).
#   vision  : renderiza albaranes y facturas del banco como fotos degradadas y pide extraer las líneas en JSON.
#   cotejo  : el caso entero (pedido+albarán+factura) en una llamada; F1 sobre pares (codigo, tipo).
# Uso: OPENROUTER_KEY=... .venv/bin/python bench-minimax/bench-nov.py vision|cotejo <model_id> [proveedor]
import json, os, re, sys, time, io, base64, random, unicodedata, difflib, urllib.request
from pathlib import Path

BANCO = Path.home() / "MAIN_PROYECTOS/proyectos-lab/.verificacion-oculta/cotejo-arquitecturas/oculto.jsonl"
OUT = Path(__file__).parent / "nov"
API = "https://openrouter.ai/api/v1/chat/completions"
KEY = os.environ["OPENROUTER_KEY"]
CASOS = [json.loads(l) for l in BANCO.open(encoding="utf-8") if l.strip()]

def llamar(model, content, prov=None, maxtok=4000):
    body = {"model": model, "temperature": 0, "max_tokens": maxtok,
            "messages": [{"role": "user", "content": content}],
            "usage": {"include": True}}
    body["provider"] = {"data_collection": "deny"}  # como los alias de LiteLLM
    if prov:
        body["provider"].update(order=[prov], allow_fallbacks=False)
    req = urllib.request.Request(API, data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    t0 = time.time()
    for intento in range(3):
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=300).read())
            break
        except Exception as e:  # noqa: BLE001
            err = str(e); time.sleep(3)
    else:
        return {"txt": f"__ERROR__ {err}", "dt": time.time() - t0, "tok": 0, "coste": 0.0, "prov": "?"}
    if "choices" not in r:
        return {"txt": f"__NOCHOICES__ {json.dumps(r)[:300]}", "dt": time.time() - t0, "tok": 0, "coste": 0.0, "prov": "?"}
    u = r.get("usage", {}) or {}
    return {"txt": r["choices"][0]["message"].get("content") or "", "dt": time.time() - t0,
            "tok": u.get("completion_tokens", 0), "tok_in": u.get("prompt_tokens", 0),
            "coste": float(u.get("cost") or 0), "prov": r.get("provider", "?")}

def json_de(txt):
    txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S)
    m = re.search(r"```(?:json)?\s*(.*?)```", txt, re.S)
    if m: txt = m.group(1)
    pares = sorted((("{", "}"), ("[", "]")), key=lambda ab: (txt.find(ab[0]) == -1, txt.find(ab[0])))
    for a, b in pares:
        i, j = txt.find(a), txt.rfind(b)
        if i != -1 and j > i:
            try: return json.loads(txt[i:j + 1])
            except Exception: pass  # noqa: BLE001
    return None

# ---------------------------------------------------------------- visión
def fuente(tam, negrita=False, mono=False):
    from PIL import ImageFont
    base = "/System/Library/Fonts/Supplemental/"
    nombre = ("Courier New Bold.ttf" if negrita else "Courier New.ttf") if mono else ("Arial Bold.ttf" if negrita else "Arial.ttf")
    return ImageFont.truetype(base + nombre, tam)

def fmt(n):
    s = f"{n:,.2f}" if isinstance(n, float) and n != int(n) or isinstance(n, float) else f"{n:,}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")

def num_es(n):
    if float(n) == int(n): return str(int(n))
    return str(n).replace(".", ",")

def documento(caso, tipo, rnd):
    from PIL import Image, ImageDraw, ImageFilter
    mono = rnd.random() < 0.5
    W, H = 1240, 1754
    im = Image.new("RGB", (W, H), (250, 249, 245)); d = ImageDraw.Draw(im)
    prov = rnd.choice(["Distribuciones Albaria S.L.", "Comercial Nervalia S.A.", "Suministros Ortelio S.L.", "Hostelera Brumar S.L."])
    numero = f"{'AL' if tipo == 'albaran' else 'F'}-{rnd.randint(2026000, 2026999)}"
    fecha = f"{rnd.randint(1, 28):02d}/{rnd.randint(1, 12):02d}/2026"
    y = 90
    d.text((90, y), prov, font=fuente(44, True, mono), fill=(20, 20, 60)); y += 60
    d.text((90, y), f"CIF B{rnd.randint(10000000, 99999999)} · Pol. Ind. Ficticio, nave {rnd.randint(1, 40)}", font=fuente(24, False, mono), fill=(60, 60, 60)); y += 80
    d.text((90, y), ("ALBARÁN DE ENTREGA" if tipo == "albaran" else "FACTURA"), font=fuente(40, True, mono), fill=(0, 0, 0))
    d.text((760, y), f"Nº {numero}", font=fuente(30, True, mono), fill=(0, 0, 0)); y += 50
    d.text((760, y), f"Fecha: {fecha}", font=fuente(28, False, mono), fill=(0, 0, 0)); y += 90
    cols = [90, 690, 830, 980] if tipo == "factura" else [90, 820, 980]
    cab = ["Descripción", "Cant.", "Ud.", "Precio"] if tipo == "factura" else ["Descripción", "Cantidad", "Unidad"]
    if tipo == "factura": cols.append(1100); cab.append("Importe")
    d.line((80, y - 10, W - 80, y - 10), fill=(0, 0, 0), width=3)
    for x, t in zip(cols, cab): d.text((x, y), t, font=fuente(26, True, mono), fill=(0, 0, 0))
    y += 50; d.line((80, y - 8, W - 80, y - 8), fill=(0, 0, 0), width=2)
    lineas = caso[tipo]["lineas"]; base = 0.0
    for l in lineas:
        desc = l["descripcion"]; f = fuente(26, False, mono)
        while d.textlength(desc, font=f) > cols[1] - cols[0] - 20 and f.size > 16: f = fuente(f.size - 1, False, mono)
        d.text((cols[0], y), desc, font=f, fill=(10, 10, 10))
        d.text((cols[1], y), num_es(l["cantidad"]), font=fuente(26, False, mono), fill=(10, 10, 10))
        d.text((cols[2], y), l["unidad"], font=fuente(26, False, mono), fill=(10, 10, 10))
        if tipo == "factura":
            imp = round(l["cantidad"] * l["precio"], 2); base += imp
            d.text((cols[3], y), f"{l['precio']:.2f}".replace(".", ","), font=fuente(26, False, mono), fill=(10, 10, 10))
            d.text((cols[4], y), f"{imp:.2f}".replace(".", ","), font=fuente(26, False, mono), fill=(10, 10, 10))
        y += 56
    d.line((80, y, W - 80, y), fill=(0, 0, 0), width=2); y += 30
    verdad = {"numero": numero, "fecha": fecha, "lineas": lineas}
    if tipo == "factura":
        base = round(base, 2); iva = round(base * 0.10, 2); total = round(base + iva, 2)
        for et, v in (("Base imponible", base), ("IVA 10 %", iva), ("TOTAL", total)):
            d.text((760, y), et, font=fuente(28, et == "TOTAL", mono), fill=(0, 0, 0))
            d.text((1060, y), f"{v:.2f} €".replace(".", ","), font=fuente(28, et == "TOTAL", mono), fill=(0, 0, 0)); y += 46
        verdad.update(base=base, iva=iva, total=total)
    else:
        d.text((90, y + 40), "Recibí conforme:", font=fuente(26, False, mono), fill=(0, 0, 0))
        d.line((330, y + 120, 640, y + 70), fill=(30, 30, 140), width=3)  # «firma»
    # Degradado tipo foto de móvil: giro leve, sombra, desenfoque, ruido, JPEG.
    im = im.rotate(rnd.uniform(-3.5, 3.5), resample=Image.BICUBIC, expand=True, fillcolor=(120, 110, 100))
    sombra = Image.new("L", im.size, 0); ds = ImageDraw.Draw(sombra)
    ds.rectangle((0, 0, int(im.size[0] * rnd.uniform(0.2, 0.5)), im.size[1]), fill=rnd.randint(20, 55))
    im = Image.composite(Image.new("RGB", im.size, (0, 0, 0)), im, sombra.filter(ImageFilter.GaussianBlur(120)))
    im = im.filter(ImageFilter.GaussianBlur(rnd.uniform(0.6, 1.4)))
    im = im.resize((int(im.size[0] * 0.8), int(im.size[1] * 0.8)))
    px = im.load()
    for _ in range(25000):
        x, yy = rnd.randrange(im.size[0]), rnd.randrange(im.size[1]); v = rnd.randint(-40, 40)
        r, g, b = px[x, yy]; px[x, yy] = (max(0, min(255, r + v)), max(0, min(255, g + v)), max(0, min(255, b + v)))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=rnd.randint(55, 75))
    return buf.getvalue(), verdad

PROMPT_V = ("Esta imagen es la foto de un {doc} de proveedor. Extrae los datos y devuelve SOLO un JSON con esta forma: "
            '{{"numero": str, "fecha": "dd/mm/aaaa", "lineas": [{{"descripcion": str, "cantidad": number, "unidad": str{precio}}}]{tot}}}. '
            "Copia las descripciones tal cual aparecen. Números con punto decimal.")

def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip(" .")

def a_num(v):
    if isinstance(v, (int, float)): return float(v)
    try: return float(str(v).replace("€", "").replace(".", "").replace(",", ".")) if "," in str(v) else float(str(v).replace("€", ""))
    except Exception: return None  # noqa: BLE001

def puntuar(verdad, obt, tipo):
    campos = ok = 0; fallos = []
    def chk(nombre, bien):
        nonlocal campos, ok
        campos += 1; ok += bool(bien)
        if not bien: fallos.append(nombre)
    o = obt or {}
    chk("numero", norm(o.get("numero", "")).replace(" ", "").endswith(norm(verdad["numero"]).replace(" ", "")))
    chk("fecha", norm(o.get("fecha", "")) == norm(verdad["fecha"]))
    ol = o.get("lineas") or []
    chk("n_lineas", len(ol) == len(verdad["lineas"]))
    for i, vl in enumerate(verdad["lineas"]):
        x = ol[i] if i < len(ol) and isinstance(ol[i], dict) else {}
        chk(f"L{i+1}.desc", difflib.SequenceMatcher(None, norm(x.get("descripcion", "")), norm(vl["descripcion"])).ratio() >= 0.9)
        c = a_num(x.get("cantidad"))
        chk(f"L{i+1}.cant", c is not None and abs(c - vl["cantidad"]) < 1e-6)
        chk(f"L{i+1}.ud", norm(x.get("unidad", "")) == norm(vl["unidad"]))
        if tipo == "factura":
            p = a_num(x.get("precio"))
            chk(f"L{i+1}.precio", p is not None and abs(p - vl["precio"]) < 0.005)
    if tipo == "factura":
        for k in ("base", "iva", "total"):
            v = a_num(o.get(k)); chk(k, v is not None and abs(v - verdad[k]) < 0.015)
    return campos, ok, fallos

def vision(model, prov):
    rnd = random.Random(20261104)  # mismas imágenes para todos los modelos
    imgdir = OUT / "imagenes"; imgdir.mkdir(parents=True, exist_ok=True)
    T = {"campos": 0, "ok": 0, "perfectos": 0, "docs": 0, "dt": 0.0, "tok": 0, "tok_in": 0, "coste": 0.0, "sin_json": 0}
    filas = []
    for caso in CASOS:
        for tipo in ("albaran", "factura"):
            jpg, verdad = documento(caso, tipo, rnd)
            (imgdir / f"{caso['id']}-{tipo}.jpg").write_bytes(jpg)
            pr = PROMPT_V.format(doc="albarán" if tipo == "albaran" else "factura",
                                 precio=', "precio": number' if tipo == "factura" else "",
                                 tot=', "base": number, "iva": number, "total": number' if tipo == "factura" else "")
            content = [{"type": "text", "text": pr},
                       {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpg).decode()}}]
            r = llamar(model, content, prov)
            obt = json_de(r["txt"]); T["sin_json"] += obt is None
            campos, ok, fallos = puntuar(verdad, obt, tipo)
            T["campos"] += campos; T["ok"] += ok; T["perfectos"] += (ok == campos); T["docs"] += 1
            for k in ("dt", "tok", "tok_in", "coste"): T[k] += r.get(k, 0)
            filas.append(f"{caso['id']} {tipo:<8} {ok}/{campos} {r['dt']:.1f}s {r['prov']} {','.join(fallos) or '—'}")
            print(filas[-1], flush=True)
    res = (f"{model} [{prov or 'auto'}] VISIÓN: campos {T['ok']}/{T['campos']} = {100*T['ok']/T['campos']:.1f} % · "
           f"documentos perfectos {T['perfectos']}/{T['docs']} · sin JSON {T['sin_json']} · "
           f"{T['dt']/T['docs']:.1f} s/doc · entrada {T['tok_in']} tok · salida {T['tok']} tok · {T['coste']:.4f} $")
    return res, filas

# ---------------------------------------------------------------- cotejo
PROMPT_C = """Coteja un pedido de compra con su albarán de entrega y su factura (datos JSON abajo).
Las unidades pueden diferir (cajas, packs, sacos…): convierte siempre a la unidad del pedido usando lo que dicen las descripciones.
Devuelve SOLO una lista JSON de discrepancias [{{"codigo": "Pn", "tipo": T}}] con T exactamente uno de:
- "cantidad": lo recibido según el albarán, convertido a la unidad del pedido, difiere de lo pedido.
- "precio": el precio unitario facturado, convertido a la unidad del pedido, difiere MÁS de un 1 % del pedido.
- "no_recibido": línea del pedido que no aparece en el albarán.
- "no_pedido": línea del albarán o de la factura que no corresponde a nada del pedido; usa "codigo": "EXTRA".
Sin discrepancias → [].

PEDIDO: {p}
ALBARÁN: {a}
FACTURA: {f}"""

def cotejo(model, prov):
    tp = fp = fn = exactos = sinr = 0; T = {"dt": 0.0, "tok": 0, "coste": 0.0}; filas = []
    for c in CASOS:
        pr = PROMPT_C.format(p=json.dumps(c["pedido"], ensure_ascii=False), a=json.dumps(c["albaran"], ensure_ascii=False),
                             f=json.dumps(c["factura"], ensure_ascii=False))
        r = llamar(model, pr, prov, maxtok=8000)
        obt = json_de(r["txt"])
        if not isinstance(obt, list): sinr += 1; obt = []
        o = {(d.get("codigo"), d.get("tipo")) for d in obt if isinstance(d, dict)}
        e = {(d["codigo"], d["tipo"]) for d in c["esperado"]}
        tp += len(e & o); fp += len(o - e); fn += len(e - o); exactos += (e == o)
        for k in T: T[k] += r.get(k, 0)
        filas.append(f"{c['id']} {'OK ' if e == o else 'MAL'} {r['dt']:.1f}s {r['prov']} esperado={sorted(e)} obtenido={sorted(o)}")
        print(filas[-1], flush=True)
    p = tp / (tp + fp) if tp + fp else 1.0; rc = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * p * rc / (p + rc) if p + rc else 0.0
    res = (f"{model} [{prov or 'auto'}] COTEJO: F1 {f1:.3f} · precisión {p:.3f} · cobertura {rc:.3f} · exactos {exactos}/{len(CASOS)} · "
           f"sin respuesta {sinr} · {T['dt']/len(CASOS):.1f} s/caso · salida {T['tok']} tok · {T['coste']:.4f} $")
    return res, filas

if __name__ == "__main__":
    modo, model = sys.argv[1], sys.argv[2]; prov = sys.argv[3] if len(sys.argv) > 3 else None
    res, filas = (vision if modo == "vision" else cotejo)(model, prov)
    etiqueta = re.sub(r"[^a-z0-9.-]+", "_", f"{modo}-{model}-{prov or 'auto'}".lower())
    (OUT / f"{etiqueta}.md").write_text(f"# {time.strftime('%Y-%m-%d %H:%M')}\n\n{res}\n\n```\n" + "\n".join(filas) + "\n```\n", encoding="utf-8")
    print("\n" + res)
