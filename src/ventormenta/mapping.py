"""Clase de las unidades eólicas del listado: paso 1 (nombre y OpenStreetMap), clase de la UP
y hash de una versión congelada del mapeo.

Funciones puras, sin datos: reciben los parques ya leídos, la descripción de cada UF o las filas
de la tabla. La regla y la forma canónica del hash están en ``docs/mapeo-listado.md``.
"""

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
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


# Columnas de la tabla del mapeo que entran en el hash, en el orden de la tabla. computed_at no
# entra: cambia en cada ejecución sin cambiar el mapeo.
HASH_COLUMNS = (
    "mapping_version",
    "uf_code",
    "up_code",
    "uf_description",
    "uf_mw",
    "listing_capture_date",
    "osm_extract_date",
    "uf_class",
    "uf_step",
    "best_osm_type",
    "best_osm_id",
    "best_osm_name",
    "best_similarity",
    "candidates_galicia",
    "candidates_rest",
    "up_class",
)


def _canonical_value(value: object) -> object:
    """Un valor de la tabla tal como entra en el texto canónico: las fechas, como ISO 8601.

    Un instante no tiene forma canónica (su texto depende de la zona horaria), y cualquier otro
    tipo sería un error de lectura de la tabla: los dos lanzan ``TypeError``. Un NaN o un
    infinito tampoco, porque JSON no los admite: lanzan ``ValueError``.
    """
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"NaN o infinito sin forma canónica: {value!r}")
    if isinstance(value, datetime):
        raise TypeError("un instante no entra en el hash: su texto depende de la zona horaria")
    if isinstance(value, date):
        return value.isoformat()
    if value is None or isinstance(value, str | int | float):
        return value
    raise TypeError(f"tipo sin forma canónica: {type(value).__name__}")


def _uf_code(row: Mapping[str, object]) -> str:
    """El código de UF de una fila, que ordena el texto canónico."""
    code = row["uf_code"]
    if not isinstance(code, str):
        raise TypeError(f"uf_code no es texto: {code!r}")
    return code


def canonical_text(rows: Iterable[Mapping[str, object]]) -> str:
    """Texto canónico de una versión del mapeo, el que se hashea al congelarla.

    Una línea con ``HASH_COLUMNS`` y otra por fila, ordenadas por ``uf_code``; cada una, un
    array JSON compacto con los caracteres no ASCII sin escapar y terminado en salto de línea.
    Lanza ``ValueError`` si las filas no son de una sola versión, si se repite un código de UF
    (la clave primaria de la tabla es informativa) o si hay un NaN o un infinito; ``KeyError``
    si a una fila le falta una columna, y ``TypeError`` si un valor no tiene forma canónica.
    """
    ordered = sorted(rows, key=_uf_code)
    versions = {row["mapping_version"] for row in ordered}
    if len(versions) != 1:
        raise ValueError(f"se espera una sola versión del mapeo y hay {len(versions)}")
    codes = [_uf_code(row) for row in ordered]
    if len(set(codes)) != len(codes):
        raise ValueError("códigos de UF repetidos en la versión")
    lines: list[list[object]] = [list(HASH_COLUMNS)]
    lines += [[_canonical_value(row[column]) for column in HASH_COLUMNS] for row in ordered]
    return "".join(
        json.dumps(line, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
        for line in lines
    )


def mapping_digest(rows: Iterable[Mapping[str, object]]) -> str:
    """SHA-256, en hexadecimal, del texto canónico de una versión del mapeo."""
    return hashlib.sha256(canonical_text(rows).encode("utf-8")).hexdigest()
