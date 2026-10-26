"""Parques de OpenStreetMap para el mapeo de las unidades eólicas.

De cada parque solo se guardan sus identificadores, el tipo de planta, las etiquetas de
nombre y la lista de sus claves, sin los valores. Así no entra ninguna potencia ni otra cifra
de los parques que pueda influir en el mapeo antes de congelarlo: la pertenencia a Galicia se
decide por el identificador y el parecido, por los nombres.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

OSM_TYPES = frozenset({"n", "w", "r"})

# Claves de nombre de OpenStreetMap, con o sin sufijo («name:gl», «alt_name:es»...). La lista
# es amplia a propósito: qué variantes entran en el parecido se decide tras explorarlas.
NAME_KEYS = (
    "name",
    "alt_name",
    "official_name",
    "old_name",
    "short_name",
    "loc_name",
    "reg_name",
    "nat_name",
    "int_name",
    "sorting_name",
)


@dataclass(frozen=True)
class Plant:
    """Un elemento de OpenStreetMap con ``power=plant``.

    ``osm_type`` es ``n``, ``w`` o ``r`` (nodo, vía o relación): los identificadores se
    repiten entre tipos, así que un elemento se identifica por el par. ``members`` solo
    tiene algo en las relaciones, como pares (tipo, identificador).
    """

    osm_type: str
    osm_id: int
    source: str | None
    names: Mapping[str, str]
    keys: tuple[str, ...]
    members: tuple[tuple[str, int], ...]


def name_tags(tags: Mapping[str, str]) -> dict[str, str]:
    """Las etiquetas de nombre de ``tags``, con su clave."""
    return {
        key: value
        for key, value in tags.items()
        if any(key == base or key.startswith(f"{base}:") for base in NAME_KEYS)
    }


def plant_from_tags(
    osm_type: str,
    osm_id: int,
    tags: Mapping[str, str],
    members: Iterable[tuple[str, int]] = (),
) -> Plant:
    """El parque de un elemento, con solo lo que el mapeo puede usar de sus etiquetas.

    Lanza ``ValueError`` si ``osm_type`` no es de nodo, vía o relación, o si un elemento que
    no es relación trae miembros: sería un error de lectura del fichero.
    """
    if osm_type not in OSM_TYPES:
        raise ValueError(f"tipo de elemento desconocido: {osm_type!r}")
    members = tuple(members)
    if members and osm_type != "r":
        raise ValueError(f"{osm_type}{osm_id} tiene miembros sin ser una relación")
    return Plant(
        osm_type=osm_type,
        osm_id=osm_id,
        source=tags.get("plant:source"),
        names=name_tags(tags),
        keys=tuple(sorted(tags)),
        members=members,
    )
