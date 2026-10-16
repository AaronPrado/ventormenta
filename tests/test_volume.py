"""Tests de la lectura del Volume: qué carpetas se recorren y qué se descarga."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from io import BytesIO
from typing import BinaryIO

import pytest
from databricks.sdk import WorkspaceClient

from ventormenta.snapshots import FileUploader, snapshot_path
from ventormenta.volume import FileReader, VolumeError, capture_dates, download_window

ROOT = "/Volumes/ventormenta/raw/esios"
DAY = date(2026, 10, 16)


def at(day: int, hour: int = 9, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


@dataclass
class Entry:
    name: str
    path: str
    is_directory: bool


@dataclass
class Download:
    contents: BinaryIO | None


class FakeReader:
    """Doble de la Files API sobre un diccionario ``ruta → contenido``.

    Como la real, falla al listar una carpeta que no existe; anota qué carpetas se listan.
    """

    def __init__(self, files: dict[str, bytes], empty: frozenset[str] = frozenset()) -> None:
        self.files = files
        self.empty = empty
        self.listed: list[str] = []

    def list_directory_contents(self, directory_path: str) -> Iterator[Entry]:
        self.listed.append(directory_path)
        prefix = directory_path.rstrip("/") + "/"
        children: dict[str, bool] = {}
        for path in self.files:
            if path.startswith(prefix):
                name, _, rest = path.removeprefix(prefix).partition("/")
                children[name] = bool(rest)
        if not children:
            raise FileNotFoundError(directory_path)
        for name, is_directory in sorted(children.items()):
            yield Entry(name, prefix + name, is_directory)

    def download(self, file_path: str) -> Download:
        if file_path in self.empty:
            return Download(None)
        return Download(BytesIO(self.files[file_path]))


def _sdk_files_api_is_a_reader_and_an_uploader(client: WorkspaceClient) -> None:
    """No se ejecuta: mypy comprueba que la Files API real cumple los dos Protocol.

    Si una versión del SDK cambia las firmas que usa el paquete, falla el lint y no el job.
    """
    reader: FileReader = client.files
    uploader: FileUploader = client.files
    del reader, uploader


# --- Fechas de captura ---


def test_capture_dates_start_two_days_before_the_first_day() -> None:
    days = [DAY, date(2026, 10, 17)]
    assert capture_dates(days) == [date(2026, 10, d) for d in (14, 15, 16, 17)]


# --- Descarga ---


def test_download_window_reads_only_folders_of_the_window() -> None:
    inside = snapshot_path(ROOT, 541, at(15))
    retry = snapshot_path(ROOT, 541, at(15, minute=10))
    other_indicator = snapshot_path(ROOT, 1777, at(15))
    outside = snapshot_path(ROOT, 541, at(1))
    reader = FakeReader({inside: b"a", retry: b"b", other_indicator: b"c", outside: b"d"})

    files = download_window(reader, ROOT, [DAY])

    assert files == [(inside, b"a"), (retry, b"b"), (other_indicator, b"c")]
    listed_folders = {path.rsplit("/", 1)[-1] for path in reader.listed}
    assert "capture_date=2026-10-01" not in listed_folders


def test_days_without_folders_are_not_listed_nor_an_error() -> None:
    reader = FakeReader({snapshot_path(ROOT, 541, at(1)): b"d"})
    assert download_window(reader, ROOT, [DAY]) == []
    assert all("capture_date=" not in path for path in reader.listed)


def test_indicator_without_captures_is_not_an_error() -> None:
    only_1777 = snapshot_path(ROOT, 1777, at(15))
    reader = FakeReader({only_1777: b"c"})
    assert download_window(reader, ROOT, [DAY]) == [(only_1777, b"c")]


def test_any_file_in_a_capture_folder_is_downloaded() -> None:
    """Un fichero ajeno no se ignora: el vigilante lo marcará como sobre no válido."""
    folder = snapshot_path(ROOT, 541, at(15)).rsplit("/", 1)[0]
    stray = f"{folder}/notas.txt"
    reader = FakeReader({stray: b"no es un sobre"})
    assert download_window(reader, ROOT, [DAY]) == [(stray, b"no es un sobre")]


def test_missing_volume_root_is_an_error() -> None:
    with pytest.raises(FileNotFoundError):
        download_window(FakeReader({}), ROOT, [DAY])


def test_empty_download_is_an_error() -> None:
    path = snapshot_path(ROOT, 541, at(15))
    reader = FakeReader({path: b"a"}, empty=frozenset({path}))
    with pytest.raises(VolumeError, match="sin contenido"):
        download_window(reader, ROOT, [DAY])
