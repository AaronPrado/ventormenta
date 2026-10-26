"""Parecido entre nombres de parques eólicos, el mismo para OpenStreetMap y el listado.

El parecido es el índice de Jaccard de los trigramas de caracteres de las formas comparables
de los dos nombres: normalizados y sin las palabras que no distinguen un parque de otro. Solo
depende de los dos nombres: una descarga nueva de OpenStreetMap no cambia el parecido de los
pares que siguen igual. La regla está en ``docs/mapeo-listado.md`` (paso 1).
"""

import re
import unicodedata
from collections.abc import Iterable, Sequence
from statistics import quantiles

# Todo lo que no es letra ni dígito separa palabras; el guion bajo cuenta como signo.
_SEPARATORS = re.compile(r"[\W_]+")
_PAD = " "

# Listas cerradas de la regla, ya normalizadas. Las de tipo y unión están en casi todos los
# nombres o cambian entre idiomas; los numerales y las fases distinguen fases de un mismo
# parque, que no cambian la clase.
TYPE_WORDS = frozenset(
    {"parque", "parc", "parke", "eolico", "eolica", "eolic", "eolikoa", "eol", "pe", "p", "uf"}
)
LINK_WORDS = frozenset(
    {"de", "del", "d", "la", "las", "el", "los", "lo", "les", "y"}  # castellano y catalán
    | {"do", "da", "dos", "das", "o", "os", "a", "as", "e"}  # gallego
)
PHASE_WORDS = frozenset({"fase", "ampliacion", "repotenciacion", "parte", "extension"})
_DROPPED = TYPE_WORDS | LINK_WORDS | PHASE_WORDS
# Solo dígitos o solo las letras de los romanos que aparecen en los nombres de fase.
_NUMERAL = re.compile(r"\d+|[ivx]+")

T_PERCENTILE = 95

# Trigramas de las formas comparables no vacías de los nombres de un elemento.
Profile = tuple[frozenset[str], ...]


def normalize(name: str) -> str:
    """Minúsculas, sin tildes y con los signos convertidos en un solo espacio.

    Las tildes se quitan descomponiendo cada letra (NFKD) y descartando las marcas, así que
    también «ñ» pasa a «n» y «ç» a «c», igual en los dos lados.
    """
    decomposed = unicodedata.normalize("NFKD", name.lower())
    bare = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _SEPARATORS.sub(" ", bare).strip()


def comparable(name: str) -> str:
    """Forma comparable: normalizado y sin palabras de tipo, de unión, numerales ni fases."""
    return " ".join(
        word
        for word in normalize(name).split()
        if word not in _DROPPED and not _NUMERAL.fullmatch(word)
    )


def trigrams(form: str) -> frozenset[str]:
    """Trigramas de caracteres de una forma ya normalizada, con un espacio a cada lado.

    El relleno da peso al principio y al final del nombre y deja que un nombre de una o dos
    letras tenga algún trigrama. Una forma vacía no tiene ninguno.
    """
    if not form:
        return frozenset()
    padded = f"{_PAD}{form}{_PAD}"
    return frozenset(padded[i : i + 3] for i in range(len(padded) - 2))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Elementos comunes sobre el total, entre 0 y 1; 0 si alguno de los dos está vacío.

    Sin el caso vacío, dos nombres sin contenido darían 0/0, y valer 1 los haría idénticos.
    """
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def profile(names: Iterable[str]) -> Profile:
    """Los trigramas de las formas comparables de ``names``, sin las vacías ni las repetidas.

    Un perfil vacío es un elemento sin nombre útil: no tiene candidatos ni entra en ``T``.
    """
    sets = (trigrams(comparable(name)) for name in names)
    return tuple(dict.fromkeys(s for s in sets if s))


def best_similarity(a: Profile, b: Profile) -> float:
    """Parecido de dos elementos: el máximo entre sus nombres, o 0 si alguno no tiene."""
    return max((jaccard(x, y) for x in a for y in b), default=0.0)


def similarity(name_a: str, name_b: str) -> float:
    """Parecido de dos nombres sueltos, entre 0 y 1."""
    return best_similarity(profile([name_a]), profile([name_b]))


def best_matches(side: Sequence[Profile], other: Sequence[Profile]) -> list[float]:
    """El mejor parecido de cada elemento con nombre de ``side`` con alguno de ``other``."""
    return [max((best_similarity(p, q) for q in other), default=0.0) for p in side if p]


def null_threshold(galicia: Sequence[Profile], rest: Sequence[Profile]) -> float:
    """Umbral ``T``: percentil 95 del mejor parecido de cada parque con el otro lado.

    Junta los de Galicia frente al resto de España y los del resto frente a Galicia: son
    parques que seguro que son distintos, así que su mejor parecido es el que se alcanza por
    azar. Interpolación lineal entre los valores ordenados (``method="inclusive"``, la misma
    que el percentil por defecto de NumPy). Lanza ``ValueError`` si algún lado no tiene
    parques con nombre.
    """
    if not any(galicia) or not any(rest):
        raise ValueError("hacen falta parques con nombre en los dos lados")
    values = best_matches(galicia, rest) + best_matches(rest, galicia)
    return quantiles(values, n=100, method="inclusive")[T_PERCENTILE - 1]
