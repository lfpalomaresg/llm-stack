"""Tests del altavoz headless (careo Codex 17/10, ronda 1: hallazgos 5, 7 y 8).

Uso: /usr/bin/python3 -m unittest ~/llm-stack/voicebox/test_altavoz.py   (sin red ni audio)
"""
import importlib.util
import os
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location("altavoz", Path(__file__).with_name("altavoz.py"))
altavoz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(altavoz)


def sse(texto: str):
    return [linea.encode() + b"\n" for linea in texto.split("\n")]


class Parser(unittest.TestCase):
    def test_bloque_final_sin_linea_en_blanco_no_se_pierde(self):
        # Hallazgo 8: un stream que acaba justo tras el último data: no vaciaba el bloque.
        datos = list(altavoz.eventos(sse('event: speak-end\ndata: {"generation_id":"g1"}')))
        self.assertEqual(datos, [("speak-end", '{"generation_id":"g1"}')])

    def test_data_multilinea_se_une_con_salto(self):
        datos = list(altavoz.eventos(sse("event: x\ndata: a\ndata: b\n")))
        self.assertEqual(datos, [("x", "a\nb")])

    def test_comentarios_y_ping_no_rompen(self):
        datos = list(altavoz.eventos(sse(': latido\nevent: ping\ndata: {}\n\nevent: speak-start\ndata: {"generation_id":"g2"}\n')))
        self.assertEqual([e for e, _ in datos], ["ping", "speak-start"])


class Seguimiento(unittest.TestCase):
    def setUp(self):
        self.sonado = []
        self.a = altavoz.Altavoz(reproducir=self.sonado.append)

    def test_solo_reproduce_lo_que_pidio_un_agente(self):
        self.a.procesar("speak-end", '{"generation_id":"ajena","status":"completed"}')
        self.a.procesar("speak-start", '{"generation_id":"g1"}')
        self.a.procesar("speak-end", '{"generation_id":"g1","status":"completed"}')
        self.assertEqual(self.sonado, ["g1"])

    def test_fallida_no_suena(self):
        self.a.procesar("speak-start", '{"generation_id":"g1"}')
        self.a.procesar("speak-end", '{"generation_id":"g1","status":"failed"}')
        self.assertEqual(self.sonado, [])

    def test_pendiente_sobrevive_a_una_reconexion(self):
        # Hallazgo 7: el estado era local a cada conexión SSE y se perdía al reconectar.
        self.a.procesar("speak-start", '{"generation_id":"g1"}')
        self.a.reconectado()
        self.a.procesar("speak-end", '{"generation_id":"g1","status":"completed"}')
        self.assertEqual(self.sonado, ["g1"])

    def test_json_roto_se_ignora(self):
        self.a.procesar("speak-start", "{no json")
        self.assertEqual(self.sonado, [])


class BackendMuerto(unittest.TestCase):
    def test_identidad_del_backend(self):
        # R1-5 / R2-4: con el backend muerto (o su PID reciclado) el altavoz quedaba huérfano.
        self.assertFalse(altavoz.backend_vivo(999999, "test_altavoz"))
        self.assertTrue(altavoz.backend_vivo(os.getpid(), "test_altavoz"))
        self.assertFalse(altavoz.backend_vivo(os.getpid(), "backend.main-no-soy-yo"))  # PID reciclado
        self.assertTrue(altavoz.backend_vivo(None, "backend.main"))  # sin PID conocido: no decide


class Bucle(unittest.TestCase):
    """Integración de main() (R2-3 y R2-4): reconexión y fin con el backend muerto."""

    def test_pendiente_sobrevive_a_la_reconexion_de_main(self):
        sonado, conexiones = [], [
            sse('event: speak-start\ndata: {"generation_id":"g1"}\n'),
            ConnectionError("corte"),
            sse('event: speak-end\ndata: {"generation_id":"g1","status":"completed"}\n'),
        ]
        def conectar():
            c = conexiones.pop(0)
            if isinstance(c, Exception):
                raise c
            return c
        vivo = iter([True, True, True, False])
        rc = altavoz.main(conectar=conectar, reproducir=sonado.append, vivo=lambda: next(vivo), dormir=lambda s: None)
        self.assertEqual(sonado, ["g1"])
        self.assertEqual(rc, 0)

    def test_termina_si_el_backend_muere(self):
        llamadas = []
        def conectar():
            llamadas.append(1)
            raise ConnectionError("sin backend")
        vivo = iter([True, True, False])
        rc = altavoz.main(conectar=conectar, reproducir=lambda g: None, vivo=lambda: next(vivo), dormir=lambda s: None)
        self.assertEqual(rc, 0)
        self.assertEqual(len(llamadas), 2)  # deja de reintentar en cuanto el backend no existe


if __name__ == "__main__":
    unittest.main()
