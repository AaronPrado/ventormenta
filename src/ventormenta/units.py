"""Listados de unidades de e·sios: unidades de programación (UP) y físicas (UF).

Los listados (archivos 82 y 81) son la foto del momento de la descarga, no un historial:
clasifican las unidades que aparecen en el P48, pero no dicen cuáles existían en un día
pasado. Todos sus campos llegan como texto.
"""

import json
import re
from collections.abc import Iterable, Mapping

UP_KEY = "UnidadesProgramacion"
UF_KEY = "UnidadesFisicas"
WIND_KINDS = frozenset({"Eólica terrestre", "Eólica marina"})

# Coma decimal obligatoria si hay punto de miles: «9.999» sin coma sería ambiguo.
_MW_FORMAT = re.compile(r"\d{1,3}(?:\.\d{3})+,\d+|\d+(?:,\d+)?")

Unit = Mapping[str, str]


class ListingError(ValueError):
    """El listado no tiene la forma esperada."""


def parse_listing(data: bytes, key: str) -> list[dict[str, str]]:
    """Registros de un listado descargado, bajo la clave ``key`` (``UP_KEY`` o ``UF_KEY``).

    Lanza ``ListingError`` si no es JSON, si falta la lista o si algún registro tiene un
    campo que no es texto: el resto del módulo da por hecho que todo es texto.
    """
    try:
        body = json.loads(data)
    except ValueError as err:
        # str y no repr: el repr de UnicodeDecodeError lleva el contenido entero.
        raise ListingError(f"el listado no es JSON: {err}") from err
    rows = body.get(key) if isinstance(body, dict) else None
    if not isinstance(rows, list):
        raise ListingError(f"el listado no tiene la lista {key!r}")
    for row in rows:
        if not isinstance(row, dict) or not all(
            isinstance(name, str) and isinstance(value, str) for name, value in row.items()
        ):
            raise ListingError(f"registro de {key!r} con campos que no son texto")
    return rows


def parse_mw(text: str) -> float | None:
    """Potencia en MW de un listado: coma decimal y, opcionalmente, punto de miles.

    Un texto vacío es una potencia sin informar (``None``). Cualquier otro formato lanza
    ``ValueError``: adivinar si un punto es decimal o de miles cambiaría la escala.
    """
    cleaned = text.strip()
    if not cleaned:
        return None
    if not _MW_FORMAT.fullmatch(cleaned):
        raise ValueError(f"potencia con formato inesperado: {text!r}")
    return float(cleaned.replace(".", "").replace(",", "."))


def wind_units(ups: Iterable[Unit]) -> frozenset[str]:
    """Códigos de las UP de tipo «Eólica terrestre» o «Eólica marina».

    El tipo se toma de la UP y no de sus UF, que en el listado es menos fiable.
    """
    return frozenset(row["Código de UP"] for row in ups if row["Tipo de producción"] in WIND_KINDS)


def hybrid_wind_units(ups: Iterable[Unit], ufs: Iterable[Unit]) -> frozenset[str]:
    """Códigos de las UP que no son eólicas pero tienen alguna UF eólica (híbridas).

    Su P48 no separa la energía eólica de la del resto de la UP, así que se tratan aparte de
    las eólicas. Lanza ``ListingError`` si una UF eólica apunta a una UP que no está en el
    listado: sin su UP no se puede saber si es eólica o híbrida.
    """
    ups = list(ups)
    known = {row["Código de UP"] for row in ups}
    linked: set[str] = set()
    for row in ufs:
        if row["Tipo de producción"] not in WIND_KINDS:
            continue
        up = row["Vinculación con UP"]
        if up not in known:
            raise ListingError(f"UF eólica {row['Código de UF']} con una UP fuera del listado")
        linked.add(up)
    return frozenset(linked - wind_units(ups))
