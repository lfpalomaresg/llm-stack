"""Lectura de números y fechas en formato español (albaranes ficticios)."""


def numero_es(texto):
    """'1.234,56' -> 1234.56 · '12' -> 12.0 · ' 0,5 € ' -> 0.5 · '-3,2' -> -3.2"""
    raise NotImplementedError


def fecha_es(texto):
    """'05/11/2026' o '5-11-26' -> '2026-11-05' (ISO). Años de dos cifras = 20xx. Fecha imposible -> ValueError."""
    raise NotImplementedError
