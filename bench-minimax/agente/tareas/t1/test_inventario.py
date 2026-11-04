import unittest
from inventario import Inventario


class T(unittest.TestCase):
    def test_entrada_suma(self):
        i = Inventario(); i.entrada("arroz", 5); i.entrada("arroz", 3)
        self.assertEqual(i.stock["arroz"], 8)

    def test_entrada_negativa(self):
        with self.assertRaises(ValueError):
            Inventario().entrada("arroz", 0)

    def test_salida_justa(self):
        i = Inventario(); i.entrada("sal", 2); i.salida("sal", 2)
        self.assertEqual(i.stock["sal"], 0)

    def test_salida_de_mas(self):
        i = Inventario(); i.entrada("sal", 2)
        with self.assertRaises(ValueError):
            i.salida("sal", 3)

    def test_bajo_minimo(self):
        i = Inventario(); i.entrada("zumo", 5); i.entrada("agua", 1); i.entrada("cafe", 10)
        self.assertEqual(i.bajo_minimo({"zumo": 6, "agua": 2, "cafe": 10, "leche": 1}), ["agua", "leche", "zumo"])


if __name__ == "__main__":
    unittest.main()
