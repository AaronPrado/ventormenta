"""Tests de la lectura del P48 de los I90, con hojas sintéticas: nunca con datos de REE.

Las hojas imitan la forma de las reales (tres filas de cabecera, la fila de columnas y una
fila por unidad) en las dos épocas: texto con coma decimal en el CSV y tipos nativos en el XLS.
"""

import zipfile
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from itertools import pairwise

import pytest

from ventormenta import i90
from ventormenta.i90 import (
    P48_SHEET,
    I90FormatError,
    Row,
    csv_rows,
    number,
    p48_rows,
    parse_p48,
    report_day,
    xls_rows,
)

DAY = date(2026, 1, 14)
# 2026-01-14 empieza a las 23:00 UTC del día anterior (invierno, UTC+1).
DAY_START = datetime(2026, 1, 13, 23, 0, tzinfo=UTC)
LONG_DAY = date(2026, 10, 25)
SHORT_DAY = date(2026, 3, 29)


def csv_sheet(
    units: Sequence[tuple[str, str, list[str]]],
    *,
    day_label: str = "14-enero-2026",
    quarters: int = 96,
    total: str | None = None,
) -> bytes:
    """Hoja del P48 en CSV: UTF-8 con BOM, ``;`` y fin de línea CRLF, como las reales."""
    width = 4 + quarters
    lines = [
        ";;Indicadores;" + ";".join(["Programa (MWh)"] * (quarters + 1)),
        ";;Dia;" + ";".join([day_label] * (quarters + 1)),
        ";;Programa;" + ";".join(["P48"] * (quarters + 1)),
        "Unidad de Programación;Tipo Oferta;Cuarto de Hora del dia;Total;"
        + ";".join(str(n) for n in range(1, quarters + 1)),
    ]
    for unit, offer_type, values in units:
        row_total = total if total is not None else f"{sum(number(v) for v in values):.3f}"
        lines.append(";".join([unit, offer_type, "", row_total.replace(".", ","), *values]))
    assert all(len(line.split(";")) == width for line in lines)
    return ("\r\n".join(lines) + "\r\n").encode("utf-8-sig")


def constant(value: str, quarters: int = 96) -> list[str]:
    return [value] * quarters


def xls_like_rows(units: Sequence[tuple[str, float, list[float]]]) -> list[list[object]]:
    """Filas como las devuelve python-calamine de un XLS: números nativos, fecha nativa y
    filas rellenas con celdas vacías hasta el ancho de la hoja."""
    padding: list[object] = ["", ""]
    rows: list[list[object]] = [
        ["", "", "Indicadores", "Programa (MWh)", *[""] * 96, *padding],
        ["", "", "Dia", DAY, *[""] * 96, *padding],
        ["", "", "Programa", "P48", *[""] * 96, *padding],
        [*i90.FIXED_COLUMNS, *[float(n) for n in range(1, 97)], *padding],
    ]
    for unit, offer_type, values in units:
        rows.append([unit, offer_type, "", sum(values), *values, *padding])
    rows.append([""] * 102)
    return rows


def parse_csv(data: bytes, day: date = DAY) -> list[i90.P48Value]:
    return parse_p48(csv_rows(data), day)


# --- Celdas ---


@pytest.mark.parametrize(
    ("cell", "value"),
    [("0,025", 0.025), ("1.234,5", 1234.5), (" 12 ", 12.0), ("", 0.0), (2.5, 2.5), (3, 3.0)],
)
def test_number(cell: object, value: float) -> None:
    assert number(cell) == pytest.approx(value)


@pytest.mark.parametrize("cell", ["abc", True])
def test_number_rejects_non_numbers(cell: object) -> None:
    with pytest.raises(I90FormatError):
        number(cell)


@pytest.mark.parametrize(
    "cell",
    ["14-enero-2026", "14-Enero-2026", DAY, datetime(2026, 1, 14, 0, 0)],  # noqa: DTZ001
)
def test_report_day(cell: object) -> None:
    assert report_day(cell) == DAY


@pytest.mark.parametrize("cell", ["14-january-2026", "14/01/2026", ""])
def test_report_day_rejects_other_formats(cell: object) -> None:
    with pytest.raises(I90FormatError, match="fecha"):
        report_day(cell)


def test_csv_rows_drop_the_bom_and_split_by_semicolon() -> None:
    rows = csv_rows("﻿a;b\r\nc;d\r\n".encode())
    assert rows == [["a", "b"], ["c", "d"]]


def test_csv_rows_reject_non_utf8() -> None:
    with pytest.raises(I90FormatError, match="UTF-8"):
        csv_rows(b"\xff\xfe;")


# --- Hoja del P48 ---


def test_csv_sheet_gives_one_value_per_unit_and_quarter() -> None:
    values = parse_csv(
        csv_sheet([("EOL1", "1", constant("0,025")), ("EOL2", "2", constant("1,5"))])
    )

    assert len(values) == 2 * 96
    first, last = values[0], values[95]
    assert (first.unit, first.offer_type) == ("EOL1", 1)
    assert first.mwh == pytest.approx(0.025)
    assert first.valid_time == DAY_START
    assert last.valid_time == DAY_START + 95 * timedelta(minutes=15)
    assert {v.unit for v in values[96:]} == {"EOL2"}
    assert values[96].mwh == pytest.approx(1.5)


def test_xls_rows_give_the_same_values_as_csv() -> None:
    csv_values = parse_csv(csv_sheet([("EOL1", "1", constant("0,025"))]))
    xls_values = parse_p48(xls_like_rows([("EOL1", 1.0, [0.025] * 96)]), DAY)
    assert xls_values == csv_values


def test_blank_quarter_is_a_null_program() -> None:
    values = parse_csv(csv_sheet([("EOL1", "1", ["", *constant("1,0", 95)])]))
    assert values[0].mwh == 0.0
    assert values[1].mwh == 1.0


@pytest.mark.parametrize(("day", "quarters"), [(LONG_DAY, 100), (SHORT_DAY, 92)])
def test_days_with_a_clock_change_have_their_real_number_of_quarters(
    day: date, quarters: int
) -> None:
    label = f"{day.day}-{('marzo', 'octubre')[day.month == 10]}-{day.year}"
    sheet = csv_sheet([("EOL1", "1", constant("1", quarters))], day_label=label, quarters=quarters)
    values = parse_csv(sheet, day)

    assert len(values) == quarters
    # Los cuartos van seguidos en UTC: el cambio de hora no deja huecos ni repeticiones.
    steps = {b.valid_time - a.valid_time for a, b in pairwise(values)}
    assert steps == {timedelta(minutes=15)}


def test_a_normal_day_with_100_quarters_is_rejected() -> None:
    sheet = csv_sheet([("EOL1", "1", constant("1", 100))], quarters=100)
    with pytest.raises(I90FormatError, match="se esperan 96"):
        parse_csv(sheet)


def test_sheet_of_another_day_is_rejected() -> None:
    sheet = csv_sheet([("EOL1", "1", constant("1"))], day_label="15-enero-2026")
    with pytest.raises(I90FormatError, match="no del 2026-01-14"):
        parse_csv(sheet)


def test_total_that_does_not_match_is_rejected() -> None:
    sheet = csv_sheet([("EOL1", "1", constant("1"))], total="95.000")
    with pytest.raises(I90FormatError, match="total"):
        parse_csv(sheet)


def test_repeated_unit_is_rejected() -> None:
    sheet = csv_sheet([("EOL1", "1", constant("1")), ("EOL1", "2", constant("1"))])
    with pytest.raises(I90FormatError, match="repetida"):
        parse_csv(sheet)


def test_sheet_without_column_row_is_rejected() -> None:
    with pytest.raises(I90FormatError, match="sin fila de columnas"):
        parse_p48([["", "", "Dia", "14-enero-2026"]], DAY)


def test_unexpected_columns_are_rejected() -> None:
    rows: list[Row] = [["Unidad de Programación", "Tipo", "Cuarto de Hora del dia", "Total"]]
    with pytest.raises(I90FormatError, match="columnas"):
        parse_p48(rows, DAY)


# --- Zip ---


def zip_with(files: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_p48_rows_read_the_csv_of_the_p48_sheet() -> None:
    sheet = csv_sheet([("EOL1", "1", constant("1"))])
    data = zip_with({"I90DIA00_20260114.csv": b"indice", f"{P48_SHEET}_20260114.csv": sheet})
    assert p48_rows(data, DAY) == csv_rows(sheet)


def test_p48_rows_read_the_p48_sheet_of_the_xls(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[bytes, str]] = []

    def fake_xls_rows(data: bytes, sheet: str) -> Sequence[Row]:
        calls.append((data, sheet))
        return [["fila"]]

    monkeypatch.setattr(i90, "xls_rows", fake_xls_rows)
    assert p48_rows(zip_with({"I90DIA_20250115.xls": b"libro"}), date(2025, 1, 15)) == [["fila"]]
    assert calls == [(b"libro", P48_SHEET)]


def test_p48_rows_reject_a_zip_without_the_p48() -> None:
    with pytest.raises(I90FormatError, match="no tiene"):
        p48_rows(zip_with({"I90DIA00_20260114.csv": b"indice"}), DAY)


def test_p48_rows_reject_a_non_zip() -> None:
    with pytest.raises(I90FormatError, match="zip"):
        p48_rows(b"<html>mantenimiento</html>", DAY)


def test_xls_rows_reject_a_non_xls() -> None:
    with pytest.raises(I90FormatError, match="XLS"):
        xls_rows(b"no es un libro", P48_SHEET)
