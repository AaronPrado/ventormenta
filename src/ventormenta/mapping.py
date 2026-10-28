"""Clase de las unidades eólicas del listado: paso 1 (nombre y OpenStreetMap) y clase de la UP.

Funciones puras, sin datos: reciben los parques ya leídos y la descripción de cada UF. La
regla está en ``docs/mapeo-listado.md``.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from ventormenta.names import comparable, jaccard, trigrams
from ventormenta.osm import Plant, name_variants


class UfClass(StrEnum):
    """Clase de una unidad física, con los valores de la tabla del mapeo."""

    GALICIAN = "gallega"
    OTHER = "otra"
    UNKNOWN = "desconocida"


class UpClass(StrEnum):
    """Clase de una unidad de programación según las de sus UF eólicas."""

    GALICIAN = "gallega"
    OTHER = "otra"
    MIXED = "mixta"
    UNKNOWN = "desconocida"


@dataclass(frozen=True)
class Park:
    """Un parque eólico de OpenStreetMap, listo para comparar.

    ``forms`` lleva cada nombre con los trigramas de su forma comparable, sin los nombres de
    forma vacía: así la evidencia puede decir con qué nombre se parece una UF, no solo cuánto.
    """

    osm_type: str
    osm_id: int
    galicia: bool
    forms: tuple[tuple[str, frozenset[str]], ...]


def park_from_plant(plant: Plant, *, galicia: bool) -> Park:
    """El parque de ``plant``, con sus nombres partidos por «;» y sin los de forma vacía."""
    forms = ((name, trigrams(comparable(name))) for name in name_variants(plant.names))
    return Park(plant.osm_type, plant.osm_id, galicia, tuple((n, t) for n, t in forms if t))


@dataclass(frozen=True)
class Candidate:
    """Un parque con un parecido de al menos ``T`` con una UF, y el nombre que lo alcanza."""

    park: Park
    name: str
    similarity: float


def candidates(description: str, parks: Iterable[Park], threshold: float) -> list[Candidate]:
    """Los parques con un parecido de al menos ``threshold`` con ``description``.

    El parecido con un parque es el máximo entre sus nombres; si dos nombres empatan, queda el
    primero. Van del más parecido al menos, y a igual parecido por tipo e identificador, para
    que el mejor candidato no dependa del orden de lectura del extracto. Una descripción de
    forma comparable vacía no tiene candidatos.
    """
    uf = trigrams(comparable(description))
    if not uf:
        return []
    found = []
    for park in parks:
        best = max(park.forms, key=lambda form: jaccard(uf, form[1]), default=None)
        if best is None:
            continue
        score = jaccard(uf, best[1])
        if score >= threshold:
            found.append(Candidate(park, best[0], score))
    return sorted(found, key=lambda c: (-c.similarity, c.park.osm_type, c.park.osm_id))


def step1_class(found: Sequence[Candidate]) -> UfClass | None:
    """Consenso de comunidad: gallega si todos los candidatos lo son, otra si ninguno.

    ``None`` es sin ubicar por el paso 1: sin candidatos o con candidatos de los dos lados.
    """
    if not found:
        return None
    sides = {c.park.galicia for c in found}
    if sides == {True}:
        return UfClass.GALICIAN
    if sides == {False}:
        return UfClass.OTHER
    return None


def up_class(uf_classes: Iterable[UfClass]) -> UpClass:
    """La clase de una UP a partir de las de sus UF eólicas.

    Basta una desconocida para que la UP lo sea, aunque las demás sean gallegas: el P48 de la
    UP no separa sus UF. Lanza ``ValueError`` si la UP no tiene UF: sería un error de lectura
    del listado, no una clase.
    """
    classes = set(uf_classes)
    if not classes:
        raise ValueError("una UP sin UF eólicas no tiene clase")
    if UfClass.UNKNOWN in classes:
        return UpClass.UNKNOWN
    if classes == {UfClass.GALICIAN}:
        return UpClass.GALICIAN
    if classes == {UfClass.OTHER}:
        return UpClass.OTHER
    return UpClass.MIXED
