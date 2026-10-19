"""Lectura del programa P48 de los ficheros I90 de e·sios.

El P48 está en la hoja ``I90DIA02``, con la misma forma en las dos épocas del fichero: un
XLS con todas las hojas (como los de 2025) o un CSV por hoja (como los de 2026). Un adaptador por
contenedor convierte la hoja en filas de celdas y ``parse_p48`` las interpreta igual en los
dos casos: tres filas de cabecera, la fila de columnas (unidad de programación, tipo de
oferta, cuarto de hora, total y un número por cuarto de hora) y una fila por unidad, con la
energía programada en MWh en cada cuarto de hora del día peninsular.
"""

import csv
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from io import BytesIO

from python_calamine import CalamineWorkbook

from ventormenta.peninsular import day_bounds, intervals_in_day

P48_SHEET = "I90DIA02"
QUARTER = timedelta(minutes=15)
FIXED_COLUMNS = ("Unidad de Programación", "Tipo Oferta", "Cuarto de Hora del dia", "Total")
# Diferencia admitida entre la columna Total y la suma de los cuartos: los valores llevan
# tres decimales, así que cualquier error de lectura es mucho mayor.
TOTAL_TOLERANCE_MWH = 1e-6

_MONTHS = {
    name: number
    for number, name in enumerate(
        (
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        ),
        start=1,
    )
}

Row = Sequence[object]


class I90FormatError(ValueError):
    """El fichero o la hoja no tienen la forma esperada."""


@dataclass(frozen=True)
class P48Value:
    """Energía programada de una unidad en un cuarto de hora.

    ``valid_time`` es el inicio del cuarto de hora, en UTC.
    """

    unit: str
    offer_type: int
    valid_time: datetime
    mwh: float


def csv_rows(data: bytes) -> list[list[str]]:
    """Filas de una hoja en CSV: UTF-8 con BOM, separada por ``;``."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as err:
        raise I90FormatError(f"CSV que no es UTF-8: {err}") from err
    return list(csv.reader(text.splitlines(), delimiter=";"))


def xls_rows(data: bytes, sheet: str) -> Sequence[Row]:
    """Filas de una hoja de un libro XLS, con los tipos nativos de Excel."""
    try:
        workbook = CalamineWorkbook.from_filelike(BytesIO(data))
        rows = workbook.get_sheet_by_name(sheet).to_python()
    except Exception as err:
        # python-calamine no expone una jerarquía de excepciones propia: cualquier fallo al
        # abrir el libro o la hoja es un fichero que no tiene la forma esperada.
        raise I90FormatError(f"XLS ilegible ({sheet}): {type(err).__name__}: {err}") from err
    return rows


def p48_rows(zip_data: bytes, day: date) -> Sequence[Row]:
    """Filas de la hoja del P48 de un zip de I90, sea de la época XLS o de la CSV."""
    csv_name = f"{P48_SHEET}_{day:%Y%m%d}.csv"
    xls_name = f"I90DIA_{day:%Y%m%d}.xls"
    try:
        with zipfile.ZipFile(BytesIO(zip_data)) as archive:
            names = set(archive.namelist())
            if csv_name in names:
                return csv_rows(archive.read(csv_name))
            if xls_name in names:
                return xls_rows(archive.read(xls_name), P48_SHEET)
    except zipfile.BadZipFile as err:
        raise I90FormatError(f"zip ilegible: {err}") from err
    raise I90FormatError(f"el zip no tiene {csv_name} ni {xls_name}")


def number(cell: object) -> float:
    """Valor numérico de una celda: nativo en el XLS, texto con coma decimal en el CSV.

    Una celda vacía es un programa nulo (0 MWh). En el texto se quitan los puntos antes de
    cambiar la coma por punto, por si hubiera separador de miles.
    """
    if isinstance(cell, bool):
        raise I90FormatError(f"celda booleana donde se esperaba un número: {cell}")
    if isinstance(cell, int | float):
        return float(cell)
    text = str(cell).strip()
    if not text:
        return 0.0
    try:
        return float(text.replace(".", "").replace(",", "."))
    except ValueError as err:
        raise I90FormatError(f"no es un número: {text!r}") from err


def report_day(cell: object) -> date:
    """Día del informe: fecha nativa en el XLS, ``14-enero-2026`` en el CSV."""
    if isinstance(cell, datetime):
        return cell.date()
    if isinstance(cell, date):
        return cell
    try:
        day, month, year = str(cell).strip().split("-")
        return date(int(year), _MONTHS[month.lower()], int(day))
    except (KeyError, ValueError) as err:
        raise I90FormatError(f"fecha del informe ilegible: {cell!r}") from err


def _text(cell: object) -> str:
    return str(cell).strip()


def _trimmed(row: Row) -> list[object]:
    """La fila sin las celdas vacías del final (un XLS rellena las filas hasta el ancho)."""
    cells = list(row)
    while cells and _text(cells[-1]) == "":
        cells.pop()
    return cells


def parse_p48(rows: Sequence[Row], day: date) -> list[P48Value]:
    """Valores del P48 de la hoja ``rows`` del día peninsular ``day``.

    Comprueba que la hoja es del día pedido, que tiene un cuarto de hora por cada intervalo
    real del día (92, 96 o 100), que cada unidad aparece una sola vez y que el total de cada
    fila cuadra con la suma de sus cuartos. Lanza ``I90FormatError`` si algo no cuadra: un
    fichero con otra forma no se interpreta a medias.
    """
    header_at = next(
        (i for i, row in enumerate(rows) if row and _text(row[0]) == FIXED_COLUMNS[0]), None
    )
    if header_at is None:
        raise I90FormatError("sin fila de columnas")
    header = _trimmed(rows[header_at])
    if tuple(_text(cell) for cell in header[:4]) != FIXED_COLUMNS:
        raise I90FormatError(f"columnas inesperadas: {header[:4]}")

    report_cells = [row[3] for row in rows[:header_at] if len(row) > 3 and _text(row[2]) == "Dia"]
    if not report_cells:
        raise I90FormatError("sin día del informe")
    if report_day(report_cells[0]) != day:
        raise I90FormatError(f"la hoja es del {report_day(report_cells[0])}, no del {day}")

    expected = intervals_in_day(day, QUARTER)
    periods = [number(cell) for cell in header[4:]]
    if periods != [float(n) for n in range(1, expected + 1)]:
        raise I90FormatError(
            f"{len(periods)} cuartos de hora en la cabecera, se esperan {expected}"
        )

    start = day_bounds(day)[0].astimezone(UTC)
    values: list[P48Value] = []
    seen: set[str] = set()
    for row in rows[header_at + 1 :]:
        cells = list(row)
        unit = _text(cells[0]) if cells else ""
        if not unit:
            continue
        if unit in seen:
            raise I90FormatError(f"unidad repetida: {unit}")
        seen.add(unit)
        quarters = [number(cell) for cell in cells[4 : 4 + expected]]
        if len(quarters) != expected:
            raise I90FormatError(f"{unit}: {len(quarters)} cuartos de hora, se esperan {expected}")
        if abs(number(cells[3]) - sum(quarters)) > TOTAL_TOLERANCE_MWH:
            raise I90FormatError(f"{unit}: el total no cuadra con la suma de cuartos")
        offer_type = int(number(cells[1]))
        values.extend(
            P48Value(unit, offer_type, start + n * QUARTER, mwh) for n, mwh in enumerate(quarters)
        )
    return values
