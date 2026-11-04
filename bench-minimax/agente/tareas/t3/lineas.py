from config import IVA_POR_DEFECTO, IVA_REDUCIDO, FAMILIAS_REDUCIDAS


def tipo_iva(familia):
    return IVA_REDUCIDO if familia in FAMILIAS_REDUCIDAS else IVA_POR_DEFECTO


def importe_linea(linea):
    """linea = {'cantidad', 'precio', 'descuento' (0-1, opcional), 'familia'} -> base sin IVA, redondeada a céntimos."""
    base = linea["cantidad"] * linea["precio"]
    base = base - linea.get("descuento", 0)  # bug: el descuento es un porcentaje
    return round(base, 2)
