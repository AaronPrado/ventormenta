"""Cierre del P48 eólico de fuera del listado contra el P48 eólico peninsular (10010).

La regla está en ``docs/unidades-fuera-del-listado.md`` y se fijó antes de medir: el residuo
entre el 10010 y el P48 de las UP eólicas del listado tiene que ser la suma del P48 de algunas
UP de fuera de él. El ajuste que da un peso a cada candidata se hace en el notebook, con
SciPy, que el paquete no necesita. Aquí están el residuo, la clasificación por peso y la
medida del cierre, que no depende del ajuste y por eso también lo comprueba.

Las series van indexadas por el instante UTC de inicio de cada cuarto de hora, no por
posición: dos series desalineadas dan error en vez de restarse cuarto con cuarto equivocado.
"""

from collections.abc import Iterable, Mapping
from datetime import datetime

WIND_WEIGHT = 0.5
MAX_CLOSURE_ERROR = 0.01

Series = Mapping[datetime, float]


def residual(reference: Series, listed: Series) -> dict[datetime, float]:
    """``R(t) = E(t) - P(t)``: el 10010 menos el P48 de las UP eólicas del listado.

    Lanza ``ValueError`` si las dos series no tienen los mismos cuartos de hora o si sus
    instantes no llevan zona horaria.
    """
    if reference.keys() != listed.keys():
        raise ValueError("el 10010 y el P48 del listado no tienen los mismos cuartos de hora")
    if any(t.tzinfo is None for t in reference):
        raise ValueError("instantes sin zona horaria: se esperan instantes UTC")
    return {t: reference[t] - listed[t] for t in reference}


def wind_by_weight(weights: Mapping[str, float]) -> frozenset[str]:
    """Candidatas eólicas según el 10010: las de peso al menos ``WIND_WEIGHT``."""
    return frozenset(unit for unit, weight in weights.items() if weight >= WIND_WEIGHT)


def closure_error(
    reference: Series, listed: Series, profiles: Mapping[str, Series], wind: Iterable[str]
) -> float:
    """``Q``: lo que las candidatas eólicas dejan sin explicar del residuo, sobre el 10010.

    Suma, cuarto a cuarto, ``|R(t) - suma de p_u(t)|`` con las ``u`` de ``wind`` (peso 1; las
    demás, peso 0) y la divide por la energía del 10010. Va en valor absoluto por cuarto, y
    no por mes, para que un exceso en unas horas no tape un defecto en otras. Un cuarto que
    falta en un perfil es un programa nulo.

    Lanza ``ValueError`` si el 10010 no suma energía positiva, si una candidata eólica no
    tiene perfil o si un perfil tiene cuartos fuera de los del residuo.
    """
    total = sum(reference.values())
    if total <= 0:
        raise ValueError(f"10010 sin energía positiva: {total}")
    remaining = residual(reference, listed)
    # Orden fijo: la suma en coma flotante da el mismo resultado en cada ejecución.
    for unit in sorted(set(wind)):
        if unit not in profiles:
            raise ValueError(f"candidata eólica sin perfil: {unit}")
        for t, mwh in profiles[unit].items():
            if t not in remaining:
                raise ValueError(f"perfil de {unit} con un cuarto fuera del mes: {t}")
            remaining[t] -= mwh
    return sum(abs(r) for r in remaining.values()) / total


def closure_holds(errors: Iterable[float]) -> bool:
    """Condición 1: el cierre ``Q`` no pasa de ``MAX_CLOSURE_ERROR`` en ningún mes."""
    months = list(errors)
    if not months:
        raise ValueError("sin meses")
    return all(error <= MAX_CLOSURE_ERROR for error in months)
