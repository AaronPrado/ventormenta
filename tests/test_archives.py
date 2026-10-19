"""Tests de la descarga de archivos de e·sios, con HTTP simulado: nunca se llama a e·sios."""

import hashlib
import json
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from io import BytesIO
from typing import Any, BinaryIO

import pytest
import requests
import responses
from databricks.sdk import WorkspaceClient
from responses import matchers

from ventormenta.archives import (
    FORMAT_VERSION,
    PAUSE_SECONDS,
    ArchiveError,
    DayState,
    IncompleteDayError,
    VolumeFiles,
    day_dir,
    day_state,
    detail_params,
    download_day,
    parse_detail,
)
from ventormenta.esios import ACCEPT, USER_AGENT, Clock, EsiosError

TOKEN = "token-de-prueba"  # noqa: S105  (valor ficticio para los tests)
ROOT = "/Volumes/ventormenta/raw/esios"
DAY = date(2025, 1, 15)
DETAIL_URL = "https://api.esios.ree.es/archives/34"
DOWNLOAD_PATH = "/archives/34/download"
DOWNLOAD_QUERY = "date=2025-01-15T23%3A59%3A59T%2B00%3A00&date_type=datos&locale=es"
DOWNLOAD_URL = f"https://api.esios.ree.es{DOWNLOAD_PATH}"
DAY_DIR = f"{ROOT}/archives/34/data_date=2025-01-15"
MOMENTS = (
    datetime(2026, 10, 19, 11, 0, 0, tzinfo=UTC),
    datetime(2026, 10, 19, 11, 0, 1, tzinfo=UTC),
    datetime(2026, 10, 19, 11, 0, 3, tzinfo=UTC),
    datetime(2026, 10, 19, 11, 0, 9, tzinfo=UTC),
)
STEM = "20261019T110009Z"


def fixed_clock(*moments: datetime) -> Clock:
    """Reloj que devuelve los instantes dados, en orden."""
    remaining = iter(moments)
    return lambda: next(remaining)


def detail_body(
    *,
    archive_id: int = 34,
    day: str = "2025-01-15",
    url: str = f"{DOWNLOAD_PATH}?{DOWNLOAD_QUERY}",
) -> bytes:
    """Ficha con la forma que devuelve e·sios para el I90."""
    archive = {
        "name": "I90DIA",
        "id": archive_id,
        "horizon": "D",
        "archive_type": "zip",
        "download": {"name": "I90DIA", "url": url},
        "date": {"date": f"{day}T23:59:59.000+00:00"},
        "date_times": [],
        "publication_date": ["2025-12-29"],
    }
    return json.dumps({"archive": archive}).encode()


def zip_bytes() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("I90DIA_20250115.xls", b"contenido de prueba")
    return buffer.getvalue()


@dataclass
class Entry:
    name: str
    path: str
    is_directory: bool


@dataclass
class Download:
    contents: BinaryIO | None


class FakeVolume:
    """Doble de la Files API: carpetas y ficheros en memoria, sin sobrescribir.

    Como la real, falla al listar una carpeta que no existe. ``fail_on`` simula que falla
    la escritura de los ficheros con ese sufijo.
    """

    def __init__(self, files: dict[str, bytes] | None = None, fail_on: str | None = None) -> None:
        self.files = dict(files or {})
        self.directories: set[str] = set()
        self.fail_on = fail_on

    def create_directory(self, directory_path: str) -> None:
        self.directories.add(directory_path)

    def upload(self, file_path: str, contents: BinaryIO, *, overwrite: bool | None = None) -> None:
        if self.fail_on and file_path.endswith(self.fail_on):
            raise OSError(f"escritura fallida: {file_path}")
        if file_path in self.files and not overwrite:
            raise FileExistsError(file_path)
        self.files[file_path] = contents.read()

    def list_directory_contents(self, directory_path: str) -> Iterator[Entry]:
        prefix = directory_path.rstrip("/") + "/"
        children: dict[str, bool] = {}
        for path in self.files:
            if path.startswith(prefix):
                name, _, rest = path.removeprefix(prefix).partition("/")
                children[name] = bool(rest)
        if not children and directory_path not in self.directories:
            raise FileNotFoundError(directory_path)
        for name, is_directory in sorted(children.items()):
            yield Entry(name, prefix + name, is_directory)

    def download(self, file_path: str) -> Download:
        return Download(BytesIO(self.files[file_path]))


def _sdk_files_api_is_volume_files(client: WorkspaceClient) -> None:
    """No se ejecuta: mypy comprueba que la Files API real cumple ``VolumeFiles``."""
    files: VolumeFiles = client.files
    del files


@pytest.fixture
def mocked() -> Iterator[responses.RequestsMock]:
    # Falla si alguna respuesta registrada no se llega a pedir, y cualquier petición sin
    # respuesta registrada es un error: así se ve cualquier petición de más.
    with responses.RequestsMock(assert_all_requests_are_fired=True) as rsps:
        yield rsps


def register_detail(mocked: responses.RequestsMock, body: bytes | None = None) -> None:
    mocked.get(
        DETAIL_URL,
        body=body if body is not None else detail_body(),
        match=[
            matchers.query_param_matcher(detail_params(DAY)),
            matchers.header_matcher(
                {"Accept": ACCEPT, "User-Agent": USER_AGENT, "x-api-key": TOKEN}
            ),
        ],
    )


def register_download(mocked: responses.RequestsMock, body: bytes | None = None) -> None:
    mocked.get(
        DOWNLOAD_URL,
        body=body if body is not None else zip_bytes(),
        match=[
            matchers.query_string_matcher(DOWNLOAD_QUERY),
            matchers.header_matcher({"User-Agent": USER_AGENT, "x-api-key": TOKEN}),
        ],
    )


def run(volume: FakeVolume, sleeps: list[float] | None = None) -> str | None:
    with requests.Session() as session:
        return download_day(
            session,
            volume,
            ROOT,
            DAY,
            TOKEN,
            clock=fixed_clock(*MOMENTS),
            sleep=(sleeps if sleeps is not None else []).append,
        )


def sidecar(volume: FakeVolume) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(volume.files[f"{DAY_DIR}/{STEM}.json"])
    return result


# --- Rutas, parámetros y estado de la carpeta ---


def test_day_dir_is_by_data_date() -> None:
    assert day_dir(ROOT, 34, DAY) == DAY_DIR


def test_detail_params_ask_by_data_date() -> None:
    assert detail_params(DAY) == {
        "date_type": "datos",
        "date": "2025-01-15T00:00:00",
        "locale": "es",
    }


@pytest.mark.parametrize(
    ("names", "state"),
    [
        ([], DayState.MISSING),
        (["a.json", "a.zip"], DayState.COMPLETE),
        (["a.json", "a.zip", "b.json", "b.zip"], DayState.COMPLETE),
        (["a.zip"], DayState.PARTIAL),
        (["a.json"], DayState.PARTIAL),
        (["a.json", "a.zip", "b.zip"], DayState.PARTIAL),
        (["notas.txt"], DayState.PARTIAL),
    ],
)
def test_day_state(names: list[str], state: DayState) -> None:
    assert day_state(names) is state


# --- Ficha ---


def test_parse_detail_reads_url_and_publication_date() -> None:
    detail = parse_detail(detail_body(), 34, DAY)
    assert detail.name == "I90DIA"
    assert detail.download_url == f"{DOWNLOAD_URL}?{DOWNLOAD_QUERY}"
    assert detail.publication_dates == ["2025-12-29"]


@pytest.mark.parametrize(
    "url",
    [
        f"https://otro.example{DOWNLOAD_PATH}?{DOWNLOAD_QUERY}",
        f"//otro.example{DOWNLOAD_PATH}?{DOWNLOAD_QUERY}",
        f"https://api.esios.ree.es{DOWNLOAD_PATH}?{DOWNLOAD_QUERY}",
        f"/archives/35/download?{DOWNLOAD_QUERY}",
        "/indicators/541",
    ],
)
def test_parse_detail_rejects_urls_outside_the_download_path(url: str) -> None:
    # Una URL absoluta, aunque sea de e·sios, tampoco: la ficha solo puede dar la ruta.
    with pytest.raises(ArchiveError, match="URL"):
        parse_detail(detail_body(url=url), 34, DAY)


@pytest.mark.parametrize(
    "body",
    [
        detail_body(archive_id=35),
        detail_body(day="2025-01-16"),
    ],
)
def test_parse_detail_rejects_another_archive_or_day(body: bytes) -> None:
    with pytest.raises(ArchiveError, match="se pidió"):
        parse_detail(body, 34, DAY)


@pytest.mark.parametrize(
    "body",
    [b"<html>mantenimiento</html>", b'{"archives": []}', b'{"archive": {"id": 34}}', b"\xff"],
)
def test_parse_detail_rejects_unreadable_bodies(body: bytes) -> None:
    with pytest.raises(ArchiveError, match="ilegible"):
        parse_detail(body, 34, DAY)


# --- Descarga ---


def test_download_writes_zip_and_sidecar(mocked: responses.RequestsMock) -> None:
    register_detail(mocked)
    register_download(mocked)
    volume = FakeVolume()
    sleeps: list[float] = []

    path = run(volume, sleeps)

    assert path == f"{DAY_DIR}/{STEM}.zip"
    assert volume.files[f"{DAY_DIR}/{STEM}.zip"] == zip_bytes()
    assert sorted(volume.files) == [f"{DAY_DIR}/{STEM}.json", f"{DAY_DIR}/{STEM}.zip"]
    assert sleeps == [PAUSE_SECONDS]


def test_sidecar_keeps_the_detail_literal_and_the_timings(mocked: responses.RequestsMock) -> None:
    register_detail(mocked)
    register_download(mocked)
    volume = FakeVolume()
    run(volume)

    data = sidecar(volume)
    assert data["format_version"] == FORMAT_VERSION
    assert data["archive_id"] == 34
    assert data["data_date"] == "2025-01-15"

    detail = data["detail"]
    assert detail["body"] == detail_body().decode()
    assert detail["body_sha256"] == hashlib.sha256(detail_body()).hexdigest()
    assert json.loads(detail["body"])["archive"]["publication_date"] == ["2025-12-29"]
    assert detail["request"]["params"] == detail_params(DAY)
    assert detail["requested_at"] == MOMENTS[0].isoformat()
    assert detail["received_at"] == MOMENTS[1].isoformat()
    assert detail["redirected_to"] is None

    file = data["file"]
    assert file["request"]["url"] == f"{DOWNLOAD_URL}?{DOWNLOAD_QUERY}"
    assert file["requested_at"] == MOMENTS[2].isoformat()
    assert file["received_at"] == MOMENTS[3].isoformat()
    assert file["size"] == len(zip_bytes())
    assert file["sha256"] == hashlib.sha256(zip_bytes()).hexdigest()


def test_token_is_never_written(mocked: responses.RequestsMock) -> None:
    register_detail(mocked)
    register_download(mocked)
    volume = FakeVolume()
    run(volume)
    assert all(TOKEN.encode() not in content for content in volume.files.values())


def test_complete_day_is_not_requested_again(mocked: responses.RequestsMock) -> None:
    volume = FakeVolume({f"{DAY_DIR}/a.zip": zip_bytes(), f"{DAY_DIR}/a.json": b"{}"})
    assert run(volume) is None
    assert len(mocked.calls) == 0


@pytest.mark.parametrize("name", ["a.zip", "a.json", "notas.txt"])
def test_partial_day_fails_without_requests(mocked: responses.RequestsMock, name: str) -> None:
    volume = FakeVolume({f"{DAY_DIR}/{name}": b"x"})
    with pytest.raises(IncompleteDayError, match="a medias"):
        run(volume)
    assert len(mocked.calls) == 0


def test_failed_sidecar_write_leaves_a_partial_day(mocked: responses.RequestsMock) -> None:
    register_detail(mocked)
    register_download(mocked)
    volume = FakeVolume(fail_on=".json")
    with pytest.raises(OSError, match="escritura fallida"):
        run(volume)

    # El siguiente intento no vuelve a pedir nada: la carpeta está a medias.
    volume.fail_on = None
    with pytest.raises(IncompleteDayError):
        run(volume)
    assert len(mocked.calls) == 2


def test_invalid_detail_stops_before_the_download(mocked: responses.RequestsMock) -> None:
    register_detail(mocked, detail_body(day="2025-01-16"))
    volume = FakeVolume()
    with pytest.raises(ArchiveError):
        run(volume)
    assert volume.files == {}


def test_non_zip_body_is_not_written(mocked: responses.RequestsMock) -> None:
    register_detail(mocked)
    register_download(mocked, b"<html>mantenimiento</html>")
    volume = FakeVolume()
    with pytest.raises(ArchiveError, match="no es un zip"):
        run(volume)
    assert volume.files == {}


@pytest.mark.parametrize("status", [404, 500])
def test_http_error_is_an_esios_error(mocked: responses.RequestsMock, status: int) -> None:
    mocked.get(DETAIL_URL, status=status)
    volume = FakeVolume()
    with pytest.raises(EsiosError):
        run(volume)
    assert volume.files == {}


# --- Redirecciones ---

STORAGE_URL = "https://almacen.example/i90/I90DIA_20250115.zip"
SIGNED_QUERY = "X-Amz-Signature=firma-de-prueba"


def test_redirect_is_followed_without_the_token(mocked: responses.RequestsMock) -> None:
    register_detail(mocked)
    mocked.get(
        DOWNLOAD_URL,
        status=307,
        headers={"Location": f"{STORAGE_URL}?{SIGNED_QUERY}"},
        match=[matchers.query_string_matcher(DOWNLOAD_QUERY)],
    )
    mocked.get(
        STORAGE_URL,
        body=zip_bytes(),
        match=[matchers.query_string_matcher(SIGNED_QUERY)],
    )
    volume = FakeVolume()
    run(volume)

    storage_request = mocked.calls[2].request
    assert "x-api-key" not in {key.lower() for key in storage_request.headers}
    assert storage_request.headers["User-Agent"] == USER_AGENT
    # Sin la query: la de una URL prefirmada lleva la firma.
    assert sidecar(volume)["file"]["redirected_to"] == STORAGE_URL


def test_non_https_redirect_is_refused(mocked: responses.RequestsMock) -> None:
    register_detail(mocked)
    mocked.get(DOWNLOAD_URL, status=302, headers={"Location": "http://almacen.example/i90.zip"})
    volume = FakeVolume()
    with pytest.raises(EsiosError, match="HTTPS"):
        run(volume)
    assert volume.files == {}
