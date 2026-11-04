import unittest
from numeros import numero_es, fecha_es


class T(unittest.TestCase):
    def test_numeros(self):
        self.assertEqual(numero_es("1.234,56"), 1234.56)
        self.assertEqual(numero_es("12"), 12.0)
        self.assertEqual(numero_es(" 0,5 € "), 0.5)
        self.assertEqual(numero_es("-3,2"), -3.2)
        self.assertEqual(numero_es("1.000.000"), 1000000.0)

    def test_numero_invalido(self):
        with self.assertRaises(ValueError):
            numero_es("doce")

    def test_fechas(self):
        self.assertEqual(fecha_es("05/11/2026"), "2026-11-05")
        self.assertEqual(fecha_es("5-11-26"), "2026-11-05")
        self.assertEqual(fecha_es("29/02/2028"), "2028-02-29")

    def test_fecha_imposible(self):
        for f in ("31/02/2026", "29/02/2027", "00/10/2026", "hola"):
            with self.assertRaises(ValueError):
                fecha_es(f)


if __name__ == "__main__":
    unittest.main()
