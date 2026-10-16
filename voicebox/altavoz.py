#!/usr/bin/env python3
"""Altavoz headless de Voicebox (2026-10-17).

El backend de Voicebox solo GENERA el audio de `voicebox_speak` (MCP) y `POST /speak`;
quien lo reproduce es la app de escritorio, que aquí no se usa. Este proceso escucha
`GET /events/speak` y reproduce con `afplay`, en orden y de uno en uno, SOLO las
generaciones que llegaron con `speak-start` (las pedidas por un agente): `speak-end`
se publica en todas las generaciones y la app también ignora los ids que no conoce.

Careo Codex 17/10 (ronda 1): los pendientes sobreviven a una reconexión, el último bloque
SSE se vacía al cerrar el stream y el proceso termina si el backend (VOICEBOX_PID) muere.

Solo biblioteca estándar. Lo arranca y lo para `stack.sh voz` / `voz-stop`.
Variables: VOICEBOX_URL (def. http://127.0.0.1:17493), VOICEBOX_PID, ALTAVOZ_PLAYER (def. afplay).
Tests: /usr/bin/python3 -m unittest ~/llm-stack/voicebox/test_altavoz.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

URL = os.environ.get("VOICEBOX_URL", "http://127.0.0.1:17493").rstrip("/")
PLAYER = os.environ.get("ALTAVOZ_PLAYER", "afplay")


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def eventos(lineas):
    """Parsea SSE y devuelve (evento, datos) por bloque. Vacía el último bloque al cerrar."""
    evento, datos = "message", []
    for raw in lineas:
        linea = raw.decode("utf-8", "replace").rstrip("\r\n")
        if not linea:
            if datos:
                yield evento, "\n".join(datos)
            evento, datos = "message", []
        elif linea.startswith(":"):
            continue  # comentario / latido
        elif linea.startswith("event:"):
            evento = linea[6:].strip()
        elif linea.startswith("data:"):
            datos.append(linea[5:].strip())
    if datos:
        yield evento, "\n".join(datos)


def backend_vivo(pid, patron: str = "backend.main") -> bool:
    """El backend sigue vivo si el PID existe Y su línea de comando contiene el patrón
    (un PID reciclado por otro proceso no cuenta). Sin PID conocido no se decide: True."""
    if pid is None:
        return True
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    r = subprocess.run(["ps", "-o", "command=", "-p", str(int(pid))], capture_output=True, text=True)
    return r.returncode == 0 and patron in r.stdout


class Altavoz:
    """Estado entre conexiones: qué generaciones pidió un agente y aún no han terminado."""

    def __init__(self, reproducir):
        self.reproducir = reproducir
        self.pendientes: set[str] = set()

    def reconectado(self) -> None:
        # Se conservan los pendientes: un speak-start recibido antes del corte sigue valiendo.
        pass

    def procesar(self, evento: str, datos: str) -> None:
        if evento not in ("speak-start", "speak-end"):
            return
        try:
            d = json.loads(datos)
        except json.JSONDecodeError:
            return
        gid = d.get("generation_id")
        if not gid:
            return
        if evento == "speak-start":
            self.pendientes.add(gid)
        elif gid in self.pendientes:
            self.pendientes.discard(gid)
            if d.get("status") == "completed":
                try:
                    self.reproducir(gid)
                except Exception as e:  # un audio roto no tumba el altavoz
                    log(f"no se pudo reproducir {gid}: {e}")
            else:
                log(f"{gid} terminó en {d.get('status')}: nada que reproducir")


def reproducir_wav(generation_id: str) -> None:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        with urllib.request.urlopen(f"{URL}/audio/{generation_id}", timeout=60) as r:
            tmp.write(r.read())
    try:
        log(f"reproduciendo {generation_id}")
        subprocess.run([PLAYER, tmp.name], check=False)
    finally:
        os.unlink(tmp.name)


def _conectar():
    return urllib.request.urlopen(f"{URL}/events/speak", timeout=60)


def main(conectar=_conectar, reproducir=None, vivo=None, dormir=time.sleep) -> int:
    """Bucle con dependencias inyectables (tests): conectar() devuelve un iterable de líneas
    SSE (o un context manager que lo es); vivo() dice si el backend sigue existiendo."""
    if vivo is None:
        pid = os.environ.get("VOICEBOX_PID") or None
        patron = os.environ.get("VOICEBOX_PATRON", "backend.main")
        vivo = lambda: backend_vivo(pid, patron)  # noqa: E731
    altavoz = Altavoz(reproducir or reproducir_wav)  # UNO para toda la vida del proceso (R2-3)
    espera = 1
    while True:
        if not vivo():
            log("el backend ya no existe: termino")
            return 0
        try:
            resp = conectar()
            with resp if hasattr(resp, "__enter__") else _nulo(resp) as lineas:
                log("conectado a /events/speak")
                espera = 1
                for evento, datos in eventos(lineas):
                    altavoz.procesar(evento, datos)
            altavoz.reconectado()
        except KeyboardInterrupt:
            return 0
        except Exception as e:  # backend reiniciándose o caído: reintento con espera creciente
            altavoz.reconectado()
            log(f"sin conexión con {URL} ({e}); reintento en {espera}s")
            dormir(espera)
            espera = min(espera * 2, 30)


class _nulo:
    def __init__(self, x):
        self.x = x

    def __enter__(self):
        return self.x

    def __exit__(self, *a):
        return False


if __name__ == "__main__":
    sys.exit(main())
