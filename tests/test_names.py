"""Tests del parecido entre nombres de parques, con nombres inventados."""

import pytest

from ventormenta.names import normalize, similarity, trigrams


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


def test_trigrams_are_padded_with_one_space_on_each_side() -> None:
    assert trigrams("uno") == {" un", "uno", "no "}


def test_trigrams_keep_the_space_between_words() -> None:
    assert trigrams("a b") == {" a ", "a b", " b "}


def test_one_letter_name_has_one_trigram() -> None:
    assert trigrams("a") == {" a "}


def test_empty_name_has_no_trigrams() -> None:
    assert trigrams("") == frozenset()


def test_similarity_ignores_case_accents_and_signs() -> None:
    assert similarity("Parque Eólico Os Moutiños", "parque-eolico OS MOUTINOS") == 1.0


def test_similarity_is_jaccard_of_trigrams() -> None:
    # «uno» = {" un", "uno", "no "}; «una» = {" un", "una", "na "}: 1 común de 5.
    assert similarity("Uno", "Una") == pytest.approx(1 / 5)


def test_similarity_is_symmetric() -> None:
    assert similarity("Monte Alto", "Alto do Monte") == similarity("Alto do Monte", "Monte Alto")


def test_unrelated_names_have_no_similarity() -> None:
    assert similarity("Xiabre", "Fuy") == 0.0


@pytest.mark.parametrize(("name_a", "name_b"), [("", "Uno"), ("Uno", "..."), ("", "")])
def test_name_without_content_has_zero_similarity(name_a: str, name_b: str) -> None:
    assert similarity(name_a, name_b) == 0.0
