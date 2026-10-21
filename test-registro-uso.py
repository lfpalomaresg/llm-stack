#!/usr/bin/env python3
"""Tests del registro de uso de LiteLLM (registro_uso.py). Sin red ni proxy."""
import asyncio, datetime as dt, json, os, sys, tempfile, types, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["REGISTRO_USO_PATH"] = tempfile.mktemp(suffix=".jsonl")
import registro_uso as ru

def kwargs(model_group="cloud-agentic", **extra):
    k = {"model": "openrouter/deepseek/deepseek-v4.1-flash-1017",
         "litellm_params": {"metadata": {"model_group": model_group}},
         "messages": [{"role": "user", "content": "SECRETO-DEL-PROMPT"}],
         "response_cost": 0.00042, "stream": False}
    k.update(extra); return k

class Resp:  # imita ModelResponse.usage
    usage = types.SimpleNamespace(prompt_tokens=120, completion_tokens=30)

class T(unittest.TestCase):
    def setUp(self):
        if os.path.exists(ru.RUTA): os.remove(ru.RUTA)
    def leer(self):
        return [json.loads(l) for l in open(ru.RUTA)]
    def test_exito_anota_metadatos_y_nunca_el_prompt(self):
        t0 = dt.datetime(2026, 10, 21, 20, 0, 0); t1 = t0 + dt.timedelta(seconds=2.5)
        asyncio.run(ru.registro.async_log_success_event(kwargs(), Resp(), t0, t1))
        (fila,) = self.leer()
        self.assertEqual(fila["alias"], "cloud-agentic")
        self.assertEqual(fila["ok"], True)
        self.assertAlmostEqual(fila["latencia_s"], 2.5)
        self.assertEqual((fila["tokens_in"], fila["tokens_out"]), (120, 30))
        self.assertAlmostEqual(fila["coste_usd"], 0.00042)
        self.assertNotIn("SECRETO-DEL-PROMPT", open(ru.RUTA).read())
    def test_fallo_anota_la_clase_de_error_sin_mensaje(self):
        t0 = dt.datetime(2026, 10, 21, 20, 0, 0)
        k = kwargs("local-worker", exception=ValueError("contenido sensible en el mensaje"))
        asyncio.run(ru.registro.async_log_failure_event(k, None, t0, t0))
        (fila,) = self.leer()
        self.assertEqual((fila["alias"], fila["ok"], fila["error"]), ("local-worker", False, "ValueError"))
        self.assertNotIn("contenido sensible", open(ru.RUTA).read())
    def test_datos_raros_no_rompen_el_proxy(self):
        asyncio.run(ru.registro.async_log_success_event({}, None, None, None))
        (fila,) = self.leer()
        self.assertEqual(fila["alias"], None)

if __name__ == "__main__":
    unittest.main()
