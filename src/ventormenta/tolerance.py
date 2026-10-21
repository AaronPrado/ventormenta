"""Regla de la tolerancia mensual de la serie gallega.

La definición está en ``docs/tolerancia-mensual.md`` y se fijó antes de medir: diferencia
relativa mensual entre el P48 eólico peninsular y la producción medida, y tolerancia igual al
peor mes más un margen para el mapeo, con un tope.
"""

from collections.abc import Sequence

MAPPING_MARGIN = 0.03
CAP = 0.05


def relative_difference(program_mwh: float, measured_mwh: float) -> float:
    """``(programa - medida) / medida``: positiva si el programa supera a la medida.

    Lanza ``ValueError`` si la medida no es positiva: un mes eólico sin producción medida
    es un error de los datos, no una diferencia.
    """
    if measured_mwh <= 0:
        raise ValueError(f"producción medida no positiva: {measured_mwh}")
    return (program_mwh - measured_mwh) / measured_mwh


def _worst(differences: Sequence[float]) -> float:
    if not differences:
        raise ValueError("sin diferencias mensuales")
    return max(abs(d) for d in differences)


def tolerance(differences: Sequence[float]) -> float:
    """Tolerancia gallega: el mayor ``|d|`` de los meses más ``MAPPING_MARGIN``, hasta ``CAP``.

    Es el máximo y no la media porque todos los meses gallegos deben quedar dentro: la
    tolerancia tiene que cubrir el peor mes del propio método.
    """
    return min(_worst(differences) + MAPPING_MARGIN, CAP)


def margin_reduced(differences: Sequence[float]) -> bool:
    """Si el peor mes deja para el mapeo menos margen que ``MAPPING_MARGIN`` por el tope."""
    return _worst(differences) + MAPPING_MARGIN > CAP
