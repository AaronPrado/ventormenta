"""Tests de los parques de OpenStreetMap, con etiquetas y coordenadas sintéticas."""

import pytest

from ventormenta.osm import (
    BorderClass,
    Plant,
    PlantPoints,
    border_class,
    member_ids,
    name_tags,
    name_variants,
    plant_from_tags,
    plant_points,
)

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


def test_name_variants_split_values_by_semicolon_in_tag_order() -> None:
    names = {"name": "Parque Eólico Uno", "alt_name": "PE Uno; Uno I;", "name:gl": " "}

    assert name_variants(names) == ["Parque Eólico Uno", "PE Uno", "Uno I"]


def test_name_variants_of_unnamed_park_is_empty() -> None:
    assert name_variants({}) == []


WIND = {"power": "plant", "plant:source": "wind"}


def test_member_ids_split_by_type_and_include_parks_that_are_not_relations() -> None:
    relation = plant_from_tags("r", 1, WIND, [("n", 7), ("w", 7), ("n", 8), ("r", 9)])
    way = plant_from_tags("w", 2, WIND)
    node = plant_from_tags("n", 3, WIND)

    assert member_ids([relation, way, node]) == (frozenset({3, 7, 8}), frozenset({2, 7}))


def test_plant_points_are_its_nodes_and_the_nodes_of_its_ways_in_member_order() -> None:
    # El 7 es a la vez un nodo y una vía: cada miembro se busca en lo leído de su tipo.
    relation = plant_from_tags("r", 1, WIND, [("n", 7), ("w", 7), ("n", 8)])
    nodes = {7: (-8.0, 43.0), 8: (-8.1, 43.1)}
    ways = {7: [(-8.2, 43.2), (-8.3, 43.3)]}

    assert plant_points(relation, nodes, ways) == PlantPoints(
        points=((-8.0, 43.0), (-8.2, 43.2), (-8.3, 43.3), (-8.1, 43.1)),
        unlocated=0,
    )


def test_plant_points_count_every_reference_left_without_location() -> None:
    # Un nodo que no se leyó, uno sin ubicación válida, una vía que no se leyó (cuenta una vez),
    # un nodo de vía sin ubicación válida y una relación dentro de la relación.
    members = [("n", 1), ("n", 2), ("w", 3), ("w", 4), ("r", 5)]
    relation = plant_from_tags("r", 10, WIND, members)
    nodes = {2: None}
    ways = {4: [(-8.0, 43.0), None]}

    assert plant_points(relation, nodes, ways) == PlantPoints(points=((-8.0, 43.0),), unlocated=5)


def test_parks_that_are_a_way_or_a_node_are_located_by_themselves() -> None:
    way = plant_from_tags("w", 10, WIND)
    node = plant_from_tags("n", 10, WIND)
    nodes = {10: (-7.0, 42.0)}
    ways = {10: [(-8.0, 43.0), (-8.1, 43.1)]}

    assert plant_points(way, nodes, ways).points == ((-8.0, 43.0), (-8.1, 43.1))
    assert plant_points(node, nodes, ways).points == ((-7.0, 42.0),)


@pytest.mark.parametrize(
    ("inside", "expected"),
    [
        ([True, True], BorderClass.INSIDE),
        ([True, False], BorderClass.CROSSES),
        ([False, False], BorderClass.OUTSIDE),
        ([], BorderClass.UNPLACED),
    ],
)
def test_border_class_depends_only_on_which_points_fall_inside(
    inside: list[bool], expected: BorderClass
) -> None:
    assert border_class(inside) == expected
