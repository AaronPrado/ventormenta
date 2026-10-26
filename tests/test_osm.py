"""Tests de los parques de OpenStreetMap, con etiquetas sintéticas."""

import pytest

from ventormenta.osm import Plant, name_tags, plant_from_tags

TAGS = {
    "power": "plant",
    "plant:source": "wind",
    "name": "Parque Eólico Uno",
    "name:gl": "Parque Eólico Un",
    "alt_name": "PE Uno;Uno I",
    "old_name:es": "Uno",
    "plant:output:electricity": "24 MW",
    "operator": "Titular S.A.",
    "wikidata": "Q1",
    "nameplate": "no es un nombre",
    "brand:name": "tampoco",
}


def test_name_tags_keeps_name_keys_with_and_without_suffix() -> None:
    assert name_tags(TAGS) == {
        "name": "Parque Eólico Uno",
        "name:gl": "Parque Eólico Un",
        "alt_name": "PE Uno;Uno I",
        "old_name:es": "Uno",
    }


def test_name_tags_of_unnamed_element_is_empty() -> None:
    assert name_tags({"power": "plant", "plant:source": "wind"}) == {}


def test_plant_keeps_ids_source_names_and_only_the_keys() -> None:
    plant = plant_from_tags("w", 10, TAGS)

    assert plant == Plant(
        osm_type="w",
        osm_id=10,
        source="wind",
        names=name_tags(TAGS),
        keys=tuple(sorted(TAGS)),
        members=(),
    )


def test_plant_drops_values_that_are_not_names() -> None:
    # Ni la potencia ni el titular de un parque pueden llegar al mapeo antes de congelarlo.
    plant = plant_from_tags("w", 10, TAGS)
    values = {plant.source, *plant.names.values()}

    assert "24 MW" not in values
    assert "Titular S.A." not in values
    assert "plant:output:electricity" in plant.keys


def test_plant_without_source_has_none() -> None:
    assert plant_from_tags("n", 1, {"power": "plant"}).source is None


def test_relation_keeps_its_members_in_order() -> None:
    members = [("w", 11), ("w", 12), ("n", 5)]

    plant = plant_from_tags("r", 20, {"power": "plant", "type": "multipolygon"}, members)

    assert plant.members == (("w", 11), ("w", 12), ("n", 5))


def test_unknown_element_type_is_rejected() -> None:
    with pytest.raises(ValueError, match="tipo de elemento"):
        plant_from_tags("a", 1, {"power": "plant"})


def test_members_outside_a_relation_are_rejected() -> None:
    with pytest.raises(ValueError, match="sin ser una relación"):
        plant_from_tags("w", 10, {"power": "plant"}, [("n", 1)])
