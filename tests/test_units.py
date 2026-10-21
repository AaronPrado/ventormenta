"""Tests de los listados de unidades, con registros sintéticos: nunca con datos de REE."""

import json

import pytest

from ventormenta.units import (
    UF_KEY,
    UP_KEY,
    ListingError,
    hybrid_wind_units,
    parse_listing,
    parse_mw,
    wind_units,
)


def up(code: str, kind: str) -> dict[str, str]:
    return {"Código de UP": code, "Tipo de producción": kind, "Potencia máxima MW": "10,0"}


def uf(code: str, kind: str, linked_up: str) -> dict[str, str]:
    return {"Código de UF": code, "Tipo de producción": kind, "Vinculación con UP": linked_up}


UPS = [
    up("EOL1", "Eólica terrestre"),
    up("EOL2", "Eólica marina"),
    up("HIB1", "Híbrida renovable"),
    up("HIB2", "Híbrida renovable-almacenamiento"),
    up("FV1", "Solar fotovoltaica"),
]
UFS = [
    uf("U1", "Eólica terrestre", "EOL1"),
    uf("U2", "Eólica terrestre", "EOL1"),
    uf("U3", "Eólica marina", "EOL2"),
    uf("U4", "Eólica terrestre", "HIB1"),
    uf("U5", "Solar fotovoltaica", "HIB1"),
    uf("U6", "Solar fotovoltaica", "HIB2"),
    uf("U7", "Solar fotovoltaica", "FV1"),
]


def test_parse_listing_returns_rows_under_key() -> None:
    data = json.dumps({UP_KEY: UPS}, ensure_ascii=False).encode("utf-8")
    assert parse_listing(data, UP_KEY) == UPS


@pytest.mark.parametrize(
    "data",
    [
        b"<html>mantenimiento</html>",
        json.dumps({UF_KEY: []}).encode(),
        json.dumps([{UP_KEY: []}]).encode(),
        json.dumps({UP_KEY: {"EOL1": "Eólica terrestre"}}).encode(),
        json.dumps({UP_KEY: [{"Código de UP": "EOL1", "Potencia máxima MW": 10.0}]}).encode(),
        json.dumps({UP_KEY: ["EOL1"]}).encode(),
    ],
    ids=["no-json", "otra-clave", "no-objeto", "no-lista", "valor-no-texto", "registro-no-objeto"],
)
def test_parse_listing_rejects_other_shapes(data: bytes) -> None:
    with pytest.raises(ListingError):
        parse_listing(data, UP_KEY)


@pytest.mark.parametrize(
    ("text", "mw"),
    [("3,8", 3.8), ("12", 12.0), ("9.999,0", 9999.0), ("1.234.567,5", 1234567.5), (" 2,0 ", 2.0)],
)
def test_parse_mw(text: str, mw: float) -> None:
    assert parse_mw(text) == pytest.approx(mw)


@pytest.mark.parametrize("text", ["", "   "])
def test_parse_mw_blank_is_none(text: str) -> None:
    assert parse_mw(text) is None


@pytest.mark.parametrize("text", ["9.999", "1,234.5", "3.8", "12,", "-1,0", "n/d"])
def test_parse_mw_rejects_ambiguous_or_other_formats(text: str) -> None:
    with pytest.raises(ValueError, match="formato inesperado"):
        parse_mw(text)


def test_wind_units_are_onshore_and_offshore_ups() -> None:
    assert wind_units(UPS) == {"EOL1", "EOL2"}


def test_wind_units_ignores_the_kind_of_the_ufs() -> None:
    # El tipo es el de la UP: una UF eólica no hace eólica a una UP híbrida.
    assert "HIB1" not in wind_units(UPS)


def test_hybrid_wind_units_are_non_wind_ups_with_a_wind_uf() -> None:
    assert hybrid_wind_units(UPS, UFS) == {"HIB1"}


def test_hybrid_wind_units_accepts_iterators() -> None:
    assert hybrid_wind_units(iter(UPS), iter(UFS)) == {"HIB1"}


def test_hybrid_wind_units_rejects_wind_uf_with_unknown_up() -> None:
    orphan = [*UFS, uf("U8", "Eólica terrestre", "BAJA1")]
    with pytest.raises(ListingError, match="U8"):
        hybrid_wind_units(UPS, orphan)


def test_hybrid_wind_units_ignores_non_wind_uf_with_unknown_up() -> None:
    orphan = [*UFS, uf("U8", "Solar fotovoltaica", "BAJA1")]
    assert hybrid_wind_units(UPS, orphan) == {"HIB1"}
