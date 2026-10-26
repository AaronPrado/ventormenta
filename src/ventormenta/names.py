"""Parecido entre nombres de parques eólicos, el mismo para OpenStreetMap y el listado.

El parecido es el índice de Jaccard de los trigramas de caracteres de los dos nombres
normalizados. Solo depende de los dos nombres: una descarga nueva de OpenStreetMap no cambia
el parecido de los pares que siguen igual.
"""

import re
import unicodedata

# Todo lo que no es letra ni dígito separa palabras; el guion bajo cuenta como signo.
_SEPARATORS = re.compile(r"[\W_]+")
_PAD = " "


def normalize(name: str) -> str:
    """Minúsculas, sin tildes y con los signos convertidos en un solo espacio.

    Las tildes se quitan descomponiendo cada letra (NFKD) y descartando las marcas, así que
    también «ñ» pasa a «n» y «ç» a «c», igual en los dos lados.
    """
    decomposed = unicodedata.normalize("NFKD", name.lower())
    bare = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _SEPARATORS.sub(" ", bare).strip()


def trigrams(normalized: str) -> frozenset[str]:
    """Trigramas de caracteres de un nombre ya normalizado, con un espacio a cada lado.

    El relleno da peso al principio y al final del nombre y deja que un nombre de una o dos
    letras tenga algún trigrama. Un nombre vacío no tiene ninguno.
    """
    if not normalized:
        return frozenset()
    padded = f"{_PAD}{normalized}{_PAD}"
    return frozenset(padded[i : i + 3] for i in range(len(padded) - 2))


def similarity(name_a: str, name_b: str) -> float:
    """Jaccard de los trigramas de los dos nombres normalizados, entre 0 y 1.

    Si alguno de los dos se queda sin trigramas (vacío o solo signos), el parecido es 0: un
    nombre sin contenido no puede ser candidato de nada.
    """
    a = trigrams(normalize(name_a))
    b = trigrams(normalize(name_b))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
