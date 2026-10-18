#!/usr/bin/env python3
# Bench de RAZONAMIENTO con verificación (2026-10-19). 8 tareas hoteleras con respuesta única.
# Uso: bench-razonar.py <identifier> <etiqueta> <salida.md>   (modelo ya cargado en LM Studio :1234)
# Muestreo/techo de producción del worker: temp 0.6 · top_p 0.95 · 14k tokens.
import json, re, sys, time, urllib.request
ID, LABEL, OUT = sys.argv[1:4]
FMT = " Razona lo necesario y termina con una última línea exactamente así: RESPUESTA: <valor>"
T = [
 ("Un hotel tiene 80 habitaciones y vendió 68 a un ADR de 120 €. ¿Cuál es el RevPAR en euros?", "102"),
 ("¿Cuántos números primos hay entre 80 y 100?", "3"),
 ("Regla: si un huésped es VIP, recibe upgrade. Juan no recibió upgrade. ¿Es Juan VIP? Responde SI o NO.", "NO"),
 ("¿Qué número sigue en la serie 2, 6, 12, 20, 30, ...?", "42"),
 ("¿Cuántas noches hay entre la entrada el 28/02/2028 y la salida el 03/03/2028?", "4"),
 ("Una tarifa de 150 € recibe un descuento del 20 % y después una subida del 10 % sobre el precio rebajado. ¿Precio final en euros?", "132"),
 ("Ana, Beto y Carla cubren los turnos de mañana, tarde y noche, uno cada uno. Ana no hace noche. Beto hace tarde. ¿Quién hace la noche?", "CARLA"),
 ("Un hotel de 120 habitaciones vendió 2.700 habitaciones-noche en un mes de 30 días. ¿Ocupación en porcentaje?", "75"),
]
def ask(q):
    body = {"model": ID, "temperature": 0.6, "top_p": 0.95, "max_tokens": 14000,
            "messages": [{"role": "user", "content": q + FMT}]}
    req = urllib.request.Request("http://localhost:1234/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t = time.time(); r = json.loads(urllib.request.urlopen(req, timeout=900).read()); dt = time.time() - t
    u = r.get("usage", {}); c = r["choices"][0]["message"].get("content") or ""
    return dt, c, (u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0), u.get("completion_tokens", 0)
def norm(x):
    x = x.upper().replace("Í", "I").replace("€", "").replace("%", "").strip().strip(".* ")
    x = re.sub(r"[.,]0+$", "", x.replace(",", "."))
    return x
L = [f"# Bench RAZONAR — {LABEL} ({ID}) — {time.strftime('%Y-%m-%d %H:%M')}", ""]; ok = rt = tt = 0; ts = 0
for i, (q, a) in enumerate(T, 1):
    dt, c, r_tok, c_tok = ask(q); ts += dt; rt += r_tok; tt += c_tok
    m = re.findall(r"RESPUESTA\s*:\s*\**\s*([^\n*]+)", c, re.I); got = norm(m[-1]) if m else "(sin RESPUESTA)"
    hit = got == a or got.startswith(a + " ") or (a.isalpha() and got.split()[0:1] == [a]); ok += hit
    L.append(f"R{i} [{dt:.0f}s · razona {r_tok} · sale {c_tok}] {'✅' if hit else '❌'} esperado {a} · obtenido {got}")
L.append(f"\nRAZONAR: {ok}/{len(T)} | razonamiento total {rt} tok | salida total {tt} tok | tiempo {ts:.0f}s")
open(OUT, "w").write("\n".join(L)); print(f"{LABEL}: {ok}/{len(T)} · razona {rt} tok · {ts:.0f}s")
