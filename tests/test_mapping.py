"""Tests del paso 1 del mapeo y de la clase de las UP, con parques y nombres inventados."""

import pytest

from ventormenta.mapping import (
    Candidate,
    Park,
    UfClass,
    UpClass,
    candidates,
    park_from_plant,
    step1_class,
    up_class,
)
from ventormenta.names import similarity
from ventormenta.osm import plant_from_tags


def make_park(osm_id: int, *names: str, galicia: bool = True, osm_type: str = "w") -> Park:
    tags = {"power": "plant", "plant:source": "wind"}
    tags |= {f"alt_name:{i}" if i else "name": name for i, name in enumerate(names)}
    return park_from_plant(plant_from_tags(osm_type, osm_id, tags), galicia=galicia)


def candidate(park: Park) -> Candidate:
    return Candidate(park, "nombre", 1.0)


def test_park_from_plant_splits_names_and_drops_empty_forms() -> None:
    park = make_park(1, "Parque Eólico Monte Alto;Serra Alta", "P.E.", galicia=False)
    assert [name for name, _ in park.forms] == ["Parque Eólico Monte Alto", "Serra Alta"]
    assert (park.osm_type, park.osm_id, park.galicia) == ("w", 1, False)


def test_park_without_useful_name_has_no_candidates() -> None:
    park = make_park(1, "Parque Eólico")
    assert park.forms == ()
    assert candidates("Parque Eólico", [park], 0.0) == []


def test_candidates_keep_best_name_and_threshold_is_inclusive() -> None:
    park = make_park(1, "Serra do Faro", "Monte Faro Novo")
    exact = similarity("PE Monte Faro Novo", "Monte Faro Novo")
    found = candidates("PE Monte Faro Novo", [park], exact)
    assert found == [Candidate(park, "Monte Faro Novo", exact)]
    assert candidates("PE Monte Faro Novo", [park], exact + 1e-9) == []


def test_candidates_order_does_not_depend_on_input_order() -> None:
    parks = [
        make_park(9, "Monte Faro"),
        make_park(3, "Monte Faro", osm_type="n"),
        make_park(5, "Faro"),
    ]
    found = candidates("Monte Faro", parks, 0.0)
    assert [(c.park.osm_type, c.park.osm_id) for c in found] == [("n", 3), ("w", 9), ("w", 5)]
    assert found == candidates("Monte Faro", parks[::-1], 0.0)


def test_description_with_empty_form_has_no_candidates() -> None:
    assert candidates("UF Eólica II", [make_park(1, "Monte Faro")], 0.0) == []


@pytest.mark.parametrize(
    ("sides", "expected"),
    [
        ((), None),
        ((True,), UfClass.GALICIAN),
        ((True, True), UfClass.GALICIAN),
        ((False,), UfClass.OTHER),
        ((True, False), None),
    ],
)
def test_step1_class_is_community_consensus(
    sides: tuple[bool, ...], expected: UfClass | None
) -> None:
    found = [candidate(make_park(i, f"Parque {i}", galicia=side)) for i, side in enumerate(sides)]
    assert step1_class(found) is expected


GAL, OTH, UNK = UfClass.GALICIAN, UfClass.OTHER, UfClass.UNKNOWN


@pytest.mark.parametrize(
    ("classes", "expected"),
    [
        ([GAL], UpClass.GALICIAN),
        ([GAL, GAL, GAL], UpClass.GALICIAN),
        ([OTH, OTH], UpClass.OTHER),
        ([GAL, OTH], UpClass.MIXED),
        ([GAL, GAL, UNK], UpClass.UNKNOWN),
        ([GAL, OTH, UNK], UpClass.UNKNOWN),
        ([UNK], UpClass.UNKNOWN),
    ],
)
def test_up_class(classes: list[UfClass], expected: UpClass) -> None:
    assert up_class(classes) is expected


def test_up_class_without_ufs_is_an_error() -> None:
    with pytest.raises(ValueError, match="sin UF"):
        up_class([])


def test_class_values_match_the_table_checks() -> None:
    assert {c.value for c in UfClass} == {"gallega", "otra", "desconocida"}
    assert {c.value for c in UpClass} == {"gallega", "otra", "mixta", "desconocida"}
