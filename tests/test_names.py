"""Tests del parecido entre nombres de parques, con nombres inventados."""

import math

import pytest

from ventormenta.names import (
    Profile,
    best_matches,
    best_similarity,
    comparable,
    jaccard,
    normalize,
    null_threshold,
    profile,
    similarity,
    trigrams,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Parque Eólico Os Moutiños", "parque eolico os moutinos"),
        ("P.E. Monte-Alto II", "p e monte alto ii"),
        ("  Serra   da  Faladoira  ", "serra da faladoira"),
        ("Coto_Novo (fase 2)", "coto novo fase 2"),
        ("Coll·lecció Garçó", "coll leccio garco"),
        ("ÁÉÍÓÚÜ", "aeiouu"),
        ("...", ""),
    ],
)
def test_normalize(name: str, expected: str) -> None:
    assert normalize(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Parque Eólico Os Moutiños", "moutinos"),
        ("P.E. Monte-Alto II", "monte alto"),
        ("P. E. LA NAVA", "nava"),
        ("P.E LOS REVENTONES", "reventones"),
        ("UF EOLICA CIERZO", "cierzo"),
        ("EOL MAYOR", "mayor"),
        ("Parc Eòlic Torre Miró I", "torre miro"),
        ("Erreniegako parke eolikoa", "erreniegako"),
        ("Parque Eólico do Irixo fase 1", "irixo"),
        ("Parque Eólico de Sóan Ampliación", "soan"),
        ("Vedadillo parte 3", "vedadillo"),
        ("PE Mairos 1234", "mairos"),
        ("Las Majas IV", "majas"),
        ("Serra da Panda - A Coriscada", "serra panda coriscada"),
        ("Parc eòlic d'Es Milà", "es mila"),
    ],
)
def test_comparable_drops_type_link_numeral_and_phase_words(name: str, expected: str) -> None:
    assert comparable(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Croas2", "croas2"),  # el numeral pegado a una palabra no es una palabra aparte
        ("Vixía", "vixia"),  # la «x» o la «i» dentro de una palabra no son numerales
        ("parque elico Viveiro", "elico viveiro"),  # las erratas no se corrigen
        ("Monte Pe", "monte"),
    ],
)
def test_comparable_only_drops_whole_words(name: str, expected: str) -> None:
    assert comparable(name) == expected


@pytest.mark.parametrize("name", ["Parque Eólico II", "P.E. Fase 1", "UF", ""])
def test_name_with_only_dropped_words_has_empty_form(name: str) -> None:
    assert comparable(name) == ""


def test_trigrams_are_padded_with_one_space_on_each_side() -> None:
    assert trigrams("uno") == {" un", "uno", "no "}


def test_trigrams_keep_the_space_between_words() -> None:
    assert trigrams("a b") == {" a ", "a b", " b "}


def test_one_letter_name_has_one_trigram() -> None:
    assert trigrams("a") == {" a "}


def test_empty_name_has_no_trigrams() -> None:
    assert trigrams("") == frozenset()


def test_jaccard_is_shared_over_all() -> None:
    assert jaccard(frozenset("abc"), frozenset("bcd")) == pytest.approx(2 / 4)


@pytest.mark.parametrize(
    ("a", "b"),
    [(frozenset(), frozenset("a")), (frozenset("a"), frozenset()), (frozenset(), frozenset())],
)
def test_jaccard_with_an_empty_set_is_zero(a: frozenset[str], b: frozenset[str]) -> None:
    assert jaccard(a, b) == 0.0


def test_similarity_ignores_case_accents_and_signs() -> None:
    assert similarity("Parque Eólico Os Moutiños", "parque-eolico OS MOUTINOS") == 1.0


def test_similarity_ignores_type_words_and_phases() -> None:
    assert similarity("P.E. MAIROS I", "Parque Eólico de Mairos II") == 1.0


def test_similarity_is_jaccard_of_trigrams() -> None:
    # «uno» = {" un", "uno", "no "}; «una» = {" un", "una", "na "}: 1 común de 5.
    assert similarity("Uno", "Una") == pytest.approx(1 / 5)


def test_similarity_is_symmetric() -> None:
    assert similarity("Monte Alto", "Alto do Monte") == similarity("Alto do Monte", "Monte Alto")


def test_unrelated_names_have_no_similarity() -> None:
    assert similarity("Xiabre", "Fuy") == 0.0


@pytest.mark.parametrize(
    ("name_a", "name_b"), [("", "Uno"), ("Uno", "..."), ("", ""), ("Parque Eólico", "P.E.")]
)
def test_name_without_content_has_zero_similarity(name_a: str, name_b: str) -> None:
    assert similarity(name_a, name_b) == 0.0


def test_profile_drops_empty_and_repeated_forms() -> None:
    names = ["Parque Eólico Uno", "P.E. UNO", "Parque Eólico", "Uno II"]

    assert profile(names) == (trigrams("uno"),)


def test_profile_keeps_each_distinct_name() -> None:
    assert profile(["Muras I", "Bustelo"]) == (trigrams("muras"), trigrams("bustelo"))


def test_profile_without_useful_names_is_empty() -> None:
    assert profile(["Parque Eólico II"]) == ()
    assert profile([]) == ()


def test_best_similarity_is_the_maximum_over_names() -> None:
    park = profile(["Parque Eólico de Muras I", "Bustelo"])

    assert best_similarity(park, profile(["P.E. BUSTELO"])) == 1.0


def test_best_similarity_without_names_is_zero() -> None:
    assert best_similarity((), profile(["Uno"])) == 0.0


def test_best_matches_skip_elements_without_names() -> None:
    side = [profile(["Uno"]), (), profile(["Xiabre"])]
    other = [profile(["Una"]), profile(["Fuy"])]

    assert best_matches(side, other) == [pytest.approx(1 / 5), 0.0]


def linear_percentile(values: list[float], percent: float) -> float:
    """Percentil con interpolación lineal entre los valores ordenados, escrito a mano."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


GALICIA = [
    profile([name])
    for name in (
        "Uno",
        "Monte Alto",
        "Serra da Faladoira",
        "Xiabre",
        "Mouriños",
        "Paxareiras",
        "Fonteavia",
        "Barbanza",
        "A Capelada",
        "Corzán",
        "Serra do Xistral",
        "Parque Eólico",
    )
]
REST = [
    profile([name])
    for name in (
        "Una",
        "Monte Baixo",
        "Sierra Costera",
        "Las Majas",
        "La Muela",
        "Tardienta",
        "La Cabrera",
        "Loma Gorda",
        "Cerro Blanco",
        "Los Llanos",
        "Sierra de Faladora",
        "Fuy",
        "Lugo",
        "Barbastro",
    )
]


def test_null_threshold_is_the_linear_95th_percentile_of_both_directions() -> None:
    values = best_matches(GALICIA, REST) + best_matches(REST, GALICIA)
    ordered = sorted(values)

    assert len(values) == 25  # el parque sin nombre útil no entra
    # El percentil cae entre dos valores distintos: el test comprueba la interpolación.
    assert ordered[22] < ordered[23]
    assert null_threshold(GALICIA, REST) == pytest.approx(linear_percentile(values, 95))


@pytest.mark.parametrize(
    ("galicia", "rest"),
    [([profile(["Parque Eólico"])], [profile(["Uno"])]), ([profile(["Uno"])], [])],
)
def test_null_threshold_needs_named_parks_on_both_sides(
    galicia: list[Profile], rest: list[Profile]
) -> None:
    with pytest.raises(ValueError, match="los dos lados"):
        null_threshold(galicia, rest)
