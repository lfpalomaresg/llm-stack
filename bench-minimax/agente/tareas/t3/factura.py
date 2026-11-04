from lineas import importe_linea, tipo_iva


def totales(lineas):
    """Devuelve {'base': ..., 'iva': ..., 'total': ...}. El IVA se calcula por línea y se suma."""
    base = sum(importe_linea(l) for l in lineas)
    iva = round(base * tipo_iva(lineas[0]["familia"]), 2)  # bug: usa el tipo de la primera línea para todo
    return {"base": round(base, 2), "iva": iva, "total": base + iva}  # bug: total sin redondear
