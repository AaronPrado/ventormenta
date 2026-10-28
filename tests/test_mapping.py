"""Tests del paso 1 del mapeo, de la clase de las UP y del hash de una versión congelada, con
parques, nombres y filas inventados."""

import hashlib
import re
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from ventormenta.mapping import (
    HASH_COLUMNS,
    Candidate,
    Park,
    UfClass,
    UpClass,
    candidates,
    canonical_text,
    mapping_digest,
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


REPO_ROOT = Path(__file__).resolve().parents[1]


def table_row(code: str, **changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "mapping_version": "v1",
        "uf_code": code,
        "up_code": "UPFARO",
        "uf_description": "Parque Eólico Monte Faro",
        "uf_mw": 12.5,
        "listing_capture_date": date(2026, 10, 20),
        "osm_extract_date": date(2026, 10, 25),
        "uf_class": "gallega",
        "uf_step": "paso1",
        "best_osm_type": "w",
        "best_osm_id": 123,
        "best_osm_name": "Monte Faro",
        "best_similarity": 0.5,
        "candidates_galicia": 1,
        "candidates_rest": 0,
        "up_class": "gallega",
        "computed_at": datetime(2026, 10, 28, 13, 0, tzinfo=UTC),
    }
    return row | changes


def test_hash_columns_are_the_table_columns_without_computed_at() -> None:
    sql = (REPO_ROOT / "infra" / "unity_catalog.sql").read_text(encoding="utf-8")
    block = sql.split("CREATE TABLE IF NOT EXISTS ventormenta.mapeo.uf (", 1)[1].split("\n)", 1)[0]
    columns = re.findall(r"^  (\w+) +(?:STRING|DOUBLE|DATE|INT|BIGINT|TIMESTAMP)\b", block, re.M)
    assert tuple(c for c in columns if c != "computed_at") == HASH_COLUMNS
    assert "computed_at" in columns


def test_canonical_text_is_the_documented_format() -> None:
    row = table_row(
        "UF1",
        uf_description="Parque Eólico Ñandú",
        best_osm_type=None,
        best_osm_id=None,
        best_osm_name=None,
        best_similarity=None,
        candidates_galicia=0,
        uf_class="desconocida",
        uf_step="ninguno",
        up_class="desconocida",
        uf_mw=0.1 + 0.2,
    )
    header = "[" + ",".join(f'"{column}"' for column in HASH_COLUMNS) + "]\n"
    line = (
        '["v1","UF1","UPFARO","Parque Eólico Ñandú",0.30000000000000004,"2026-10-20",'
        '"2026-10-25","desconocida","ninguno",null,null,null,null,0,0,"desconocida"]\n'
    )
    assert canonical_text([row]) == header + line


def test_digest_is_the_sha256_of_the_canonical_text() -> None:
    rows = [table_row("UF2"), table_row("UF1")]
    expected = hashlib.sha256(canonical_text(rows).encode("utf-8")).hexdigest()
    assert mapping_digest(rows) == expected
    assert re.fullmatch(r"[0-9a-f]{64}", expected)


def test_digest_ignores_row_order_and_computed_at() -> None:
    rows = [table_row("UF1"), table_row("UF2"), table_row("UF10")]
    later = datetime(2026, 11, 2, 9, 30, tzinfo=UTC)
    rerun = [row | {"computed_at": later} for row in reversed(rows)]
    assert mapping_digest(rerun) == mapping_digest(rows)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("uf_class", "otra"),
        ("up_class", "mixta"),
        ("uf_mw", 12.500000000000002),
        ("best_similarity", None),
        ("listing_capture_date", date(2026, 10, 21)),
        ("best_osm_type", "n"),
    ],
)
def test_digest_changes_with_any_hashed_value(column: str, value: object) -> None:
    rows = [table_row("UF1"), table_row("UF2")]
    changed = [rows[0] | {column: value}, rows[1]]
    assert mapping_digest(changed) != mapping_digest(rows)


@pytest.mark.parametrize(
    ("rows", "match"),
    [
        ([], "una sola versión"),
        ([table_row("UF1"), table_row("UF1")], "repetidos"),
        ([table_row("UF1"), table_row("UF2", mapping_version="v2")], "una sola versión"),
        ([table_row("UF1", uf_mw=float("nan"))], "NaN o infinito"),
        ([table_row("UF1", best_similarity=float("inf"))], "NaN o infinito"),
    ],
    ids=["vacía", "código repetido", "dos versiones", "NaN", "infinito"],
)
def test_canonical_text_rejects_invalid_versions(rows: list[dict[str, object]], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        canonical_text(rows)


@pytest.mark.parametrize(
    "row",
    [
        table_row("UF1", listing_capture_date=datetime(2026, 10, 20, tzinfo=UTC)),
        table_row("UF1", uf_mw=b"12,5"),
    ],
    ids=["instante", "bytes"],
)
def test_canonical_text_rejects_values_without_canonical_form(row: dict[str, object]) -> None:
    with pytest.raises(TypeError, match=r"instante|sin forma canónica"):
        canonical_text([row])


def test_canonical_text_requires_every_hashed_column() -> None:
    row = table_row("UF1")
    del row["up_class"]
    with pytest.raises(KeyError, match="up_class"):
        canonical_text([row])
