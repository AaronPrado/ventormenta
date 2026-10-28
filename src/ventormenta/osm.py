"""Parques de OpenStreetMap para el mapeo de las unidades eólicas.

De cada parque solo se guardan sus identificadores, el tipo de planta, las etiquetas de nombre
y la lista de sus claves, sin los valores. Así no entra ninguna potencia ni otra cifra de los
parques que pueda influir en el mapeo antes de congelarlo: la pertenencia a Galicia se decide
por el identificador y el parecido, por los nombres.

De sus miembros solo se guardan las coordenadas, sin ninguna etiqueta, por la misma razón: un
aerogenerador puede llevar su potencia en las suyas. Sirven para ver dónde queda cada parque
respecto a un límite, no para decidir su pertenencia.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

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

# Longitud y latitud de un nodo en grados (WGS84), en el orden x, y de las geometrías.
Point = tuple[float, float]


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


def name_variants(names: Mapping[str, str]) -> list[str]:
    """Los nombres de un parque: cada valor de sus etiquetas de nombre, partido por «;».

    El «;» separa varios valores en una misma etiqueta de OpenStreetMap. Se quitan los
    espacios de los extremos y los valores vacíos; el orden es el de las etiquetas.
    """
    return [part.strip() for value in names.values() for part in value.split(";") if part.strip()]


def _references(plant: Plant) -> tuple[tuple[str, int], ...]:
    """Lo que ubica un parque: sus miembros si es una relación, o él mismo si no lo es."""
    if plant.osm_type == "r":
        return plant.members
    return ((plant.osm_type, plant.osm_id),)


def member_ids(plants: Iterable[Plant]) -> tuple[frozenset[int], frozenset[int]]:
    """Los nodos y las vías que hay que leer para ubicar ``plants``, en ese orden.

    Son los miembros de las relaciones y los parques que son un nodo o una vía. Van separados
    porque los identificadores se repiten entre tipos. Los miembros que son relaciones no se
    piden: esta lectura no los resuelve, y ``plant_points`` los cuenta sin ubicación.
    """
    nodes: set[int] = set()
    ways: set[int] = set()
    for plant in plants:
        for osm_type, osm_id in _references(plant):
            if osm_type == "n":
                nodes.add(osm_id)
            elif osm_type == "w":
                ways.add(osm_id)
    return frozenset(nodes), frozenset(ways)


@dataclass(frozen=True)
class PlantPoints:
    """Los puntos de un parque y cuántas de sus referencias se quedaron sin ubicación."""

    points: tuple[Point, ...]
    unlocated: int


def plant_points(
    plant: Plant,
    nodes: Mapping[int, Point | None],
    ways: Mapping[int, Sequence[Point | None]],
) -> PlantPoints:
    """Los puntos de ``plant``: sus nodos miembro y los nodos de sus vías miembro.

    Un parque que es un nodo o una vía se ubica con ese nodo o con los nodos de esa vía.
    ``nodes`` y ``ways`` son lo leído del fichero: la ubicación de cada nodo y las de los nodos
    de cada vía, con ``None`` donde no es válida. Quedan sin ubicación, y se cuentan, los nodos
    y las vías que no se leyeron (una vía cuenta una vez), las ubicaciones no válidas y los
    miembros que son relaciones.
    """
    points: list[Point] = []
    unlocated = 0
    for osm_type, osm_id in _references(plant):
        if osm_type == "n":
            locations: Sequence[Point | None] = (nodes.get(osm_id),)
        elif osm_type == "w":
            locations = ways.get(osm_id, (None,))
        else:
            locations = (None,)
        for location in locations:
            if location is None:
                unlocated += 1
            else:
                points.append(location)
    return PlantPoints(tuple(points), unlocated)


class BorderClass(StrEnum):
    """Dónde queda un parque respecto a un límite, según sus puntos."""

    INSIDE = "inside"
    CROSSES = "crosses"
    OUTSIDE = "outside"
    UNPLACED = "unplaced"


def border_class(inside: Iterable[bool]) -> BorderClass:
    """La clase de un parque según si cada uno de sus puntos cae dentro del límite.

    Dentro si caen todos, fuera si no cae ninguno, cruza si unos sí y otros no, y sin posición
    si no tiene puntos. Las referencias sin ubicación no deciden la clase: solo cuentan los
    puntos.
    """
    flags = list(inside)
    if not flags:
        return BorderClass.UNPLACED
    if all(flags):
        return BorderClass.INSIDE
    if not any(flags):
        return BorderClass.OUTSIDE
    return BorderClass.CROSSES
