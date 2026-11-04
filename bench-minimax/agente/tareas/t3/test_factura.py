import unittest
from factura import totales


class T(unittest.TestCase):
    def test_mixta(self):
        lineas = [
            {"cantidad": 10, "precio": 2.5, "familia": "alimentacion"},
            {"cantidad": 2, "precio": 15.0, "descuento": 0.10, "familia": "limpieza"},
            {"cantidad": 3, "precio": 1.15, "familia": "bebidas_sin_alcohol"},
        ]
        t = totales(lineas)
        self.assertEqual(t["base"], 55.45)
        self.assertEqual(t["iva"], 8.52)
        self.assertEqual(t["total"], 63.97)

    def test_una_linea(self):
        t = totales([{"cantidad": 1, "precio": 0.1, "familia": "limpieza"}])
        self.assertEqual(t, {"base": 0.1, "iva": 0.02, "total": 0.12})


if __name__ == "__main__":
    unittest.main()
