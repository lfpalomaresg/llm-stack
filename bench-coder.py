#!/usr/bin/env python3
# Bench de código con verificación EJECUTABLE. Un modelo ya cargado en LM Studio (:1234).
# Uso: bench-coder.py <identifier> <etiqueta> <salida.md>
import json, sys, time, re, subprocess, urllib.request, os

ID, LABEL, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
API = "http://localhost:1234/v1/chat/completions"

def call(prompt, maxtok=3000):
    payload = json.dumps({"model": ID, "temperature": 0.2, "top_p": 0.8, "max_tokens": maxtok,
        "messages": [{"role": "user", "content": prompt}]}).encode()
    t0 = time.time()
    req = urllib.request.Request(API, data=payload, headers={"Content-Type": "application/json"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=300).read())
    except Exception as e:
        return 0, 0, f"__ERROR__ {e}"
    dt = time.time() - t0
    m = r["choices"][0]["message"]
    return dt, r.get("usage", {}).get("completion_tokens", 0), m.get("content", "") or ""

def extract_code(txt):
    m = re.search(r"```(?:python)?\s*\n(.*?)```", txt, re.DOTALL)
    return m.group(1) if m else txt

def run_test(code, test):
    full = code + "\n\n" + test
    try:
        p = subprocess.run(["python3", "-c", full], capture_output=True, text=True, timeout=15)
        return p.returncode == 0, (p.stderr.strip().splitlines() or [""])[-1][:120]
    except Exception as e:
        return False, str(e)[:120]

# (prompt, test que importa las funciones definidas y hace asserts)
TASKS = [
 ("Escribe SOLO el código Python de una función revpar(adr, ocupacion) que: lance ValueError si ocupacion no está en [0,1], y devuelva adr*ocupacion redondeado a 2 decimales. Sin explicación.",
  "assert revpar(120,0.85)==102.0\ntry:\n revpar(1,2); raise SystemExit(1)\nexcept ValueError: pass\nprint('ok')"),
 ("Escribe SOLO el código Python de una función n_primos(n) que devuelva una lista con los primeros n números primos. Sin explicación.",
  "assert n_primos(5)==[2,3,5,7,11]\nassert n_primos(1)==[2]\nassert n_primos(0)==[]\nprint('ok')"),
 ("Escribe SOLO el código Python de una función suma_hora(hhmm, minutos) que reciba una hora 'HH:MM' (str) y un entero de minutos, y devuelva la hora resultante como 'HH:MM' en formato 24h (con vuelta de día). Sin explicación.",
  "assert suma_hora('09:40',155)=='12:15'\nassert suma_hora('23:30',60)=='00:30'\nprint('ok')"),
 ("Escribe SOLO el código Python de una función agrupar(registros, clave) que agrupe una lista de diccionarios por el valor de 'clave' y devuelva un dict {valor: [registros...]}. Sin explicación.",
  "r=[{'c':'a','n':1},{'c':'b','n':2},{'c':'a','n':3}]\ng=agrupar(r,'c')\nassert g['a']==[{'c':'a','n':1},{'c':'a','n':3}] and g['b']==[{'c':'b','n':2}]\nprint('ok')"),
 ("Este código tiene un bug (falla en el último elemento). Corrígelo y devuelve SOLO el código corregido de la función:\n\ndef ultimo_n(lista, n):\n    # debe devolver los ULTIMOS n elementos en orden original\n    return lista[len(lista)-n-1:]\n",
  "assert ultimo_n([1,2,3,4,5],2)==[4,5]\nassert ultimo_n([1,2,3],3)==[1,2,3]\nprint('ok')"),
 ("Escribe SOLO el código Python de una función merge_ocupacion(a, b) que reciba dos dicts {ciudad: ocupacion} y devuelva un dict con todas las ciudades; si una ciudad está en ambos, la media de las dos ocupaciones. Sin explicación.",
  "assert merge_ocupacion({'M':80,'R':50},{'M':90,'G':70})=={'M':85.0,'R':50,'G':70}\nprint('ok')"),
]

lines = [f"# Bench CODER — {LABEL} ({ID}) — {time.strftime('%H:%M')}", ""]
# velocidad
dt, ct, _ = call("Escribe una función Python que sume dos números. Solo el código.", 500)
lines.append(f"velocidad: {ct} tok en {dt:.1f}s = {ct/max(dt,0.01):.1f} tok/s\n")
ok = 0; tt = 0; ts = 0.0
for i, (prompt, test) in enumerate(TASKS, 1):
    dt, ct, txt = call(prompt); tt += ct; ts += dt
    code = extract_code(txt)
    passed, err = run_test(code, test)
    if passed: ok += 1
    lines.append(f"C{i} [{dt:.0f}s/{ct}t] {'✅ PASS' if passed else '❌ FAIL: '+err}")
lines.append(f"\nCODIGO: {ok}/{len(TASKS)} PASS | media {tt//len(TASKS)} tok/tarea | vel media {tt/max(ts,0.01):.1f} tok/s")
lines.append(f"== FIN {LABEL} ==")
open(OUT, "w").write("\n".join(lines))
print(f"{LABEL}: {ok}/{len(TASKS)}")
