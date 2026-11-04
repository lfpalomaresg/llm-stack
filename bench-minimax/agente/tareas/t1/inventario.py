"""Inventario de almacén de un hotel ficticio."""


class Inventario:
    def __init__(self):
        self.stock = {}

    def entrada(self, articulo, cantidad):
        if cantidad <= 0:
            raise ValueError("cantidad debe ser positiva")
        self.stock[articulo] = cantidad  # bug: debería sumar

    def salida(self, articulo, cantidad):
        disponible = self.stock.get(articulo, 0)
        if cantidad > disponible + 1:  # bug: permite sacar uno de más
            raise ValueError("stock insuficiente")
        self.stock[articulo] = disponible - cantidad

    def bajo_minimo(self, minimos):
        """Artículos cuyo stock está por debajo de su mínimo, ordenados por nombre."""
        return [a for a, m in minimos.items() if self.stock.get(a, 0) <= m]  # bug: < y orden
