"""Archivos zip de e·sios (como el I90): ficha, descarga y escritura en el Volume, una sola vez.

El archivo de un día se pide en dos pasos: la ficha (``/archives/<id>``), que dice desde dónde
se descarga y cuándo se publicó, y el fichero. Los dos se guardan juntos en una carpeta por día
de datos: el zip tal como llega y, al lado, un JSON con la ficha literal y los instantes de cada
petición. Un día que ya tiene algo en su carpeta no se vuelve a pedir.
"""

import hashlib
import json
import posixpath
import time
import zipfile
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from io import BytesIO
from typing import Any, Protocol
from urllib.parse import urlsplit

import requests

from ventormenta.esios import ACCEPT, TIMEOUT_SECONDS, USER_AGENT, Clock, EsiosError, utc_now
from ventormenta.snapshots import FileUploader
from ventormenta.volume import FileReader

ESIOS_BASE_URL = "https://api.esios.ree.es"
I90_ARCHIVE_ID = 34
# Sube si cambia la estructura del JSON lateral, para que bronze sepa cómo leerlo.
FORMAT_VERSION = 1
# Entre la ficha y el fichero: dos peticiones seguidas a e·sios, con pausa (uso responsable).
PAUSE_SECONDS = 2.0
# Tope de días por ejecución: como mucho dos peticiones a e·sios por día, 62 por ejecución.
MAX_DAYS_PER_RUN = 31
# Retraso con el que se publica el I90 de un día: uno más reciente aún no puede estar
# publicado, y pedirlo sería pedir algo que no existe.
PUBLICATION_LAG = timedelta(days=90)
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})

Sleep = Callable[[float], None]


class VolumeFiles(FileUploader, FileReader, Protocol):
    """Lo que la descarga necesita de la Files API: listar y escribir."""


class ArchiveError(ValueError):
    """La ficha o el fichero no tienen la forma esperada."""


class IncompleteDayError(RuntimeError):
    """La carpeta del día tiene ficheros, pero no un zip con su JSON: se revisa a mano."""


@dataclass(frozen=True)
class Fetched:
    """Respuesta de e·sios sin interpretar, con los instantes de petición y recepción en UTC.

    ``redirected_to`` es el origen y la ruta a los que redirigió e·sios, si lo hizo, sin la
    query: en una URL prefirmada lleva la firma.
    """

    url: str
    params: dict[str, str]
    status_code: int
    body: bytes
    server_date: str | None
    requested_at: datetime
    received_at: datetime
    redirected_to: str | None = None


@dataclass(frozen=True)
class ArchiveDetail:
    """Lo que se usa de la ficha de un archivo para un día."""

    name: str
    download_url: str
    publication_dates: list[str]


class DayState(StrEnum):
    """Qué hay en la carpeta de un día."""

    MISSING = "missing"
    COMPLETE = "complete"
    PARTIAL = "partial"


def detail_params(day: date) -> dict[str, str]:
    """Parámetros de la ficha del día ``day``, por fecha de los datos (no de publicación)."""
    return {"date_type": "datos", "date": f"{day.isoformat()}T00:00:00", "locale": "es"}


def archive_dir(root: str, archive_id: int) -> str:
    """Carpeta de un archivo: ``<root>/archives/<id>``."""
    return posixpath.join(root, "archives", str(archive_id))


def day_dir(root: str, archive_id: int, day: date) -> str:
    """Carpeta de un día de datos: ``<root>/archives/<id>/data_date=<AAAA-MM-DD>``.

    Va por día de datos y no por fecha de descarga, al revés que las instantáneas: cada día
    tiene un solo fichero, y así saber si ya se descargó es listar una carpeta.
    """
    return posixpath.join(archive_dir(root, archive_id), f"data_date={day.isoformat()}")


def _stem(moment: datetime) -> str:
    """Instante UTC en ISO 8601 básico, sin ``:``, que da problemas en las rutas."""
    if moment.utcoffset() is None:
        raise ValueError("el instante necesita zona horaria")
    return f"{moment.astimezone(UTC):%Y%m%dT%H%M%SZ}"


def day_state(names: list[str]) -> DayState:
    """Estado de la carpeta de un día a partir de los nombres de sus ficheros.

    Completa si cada zip tiene su JSON con el mismo nombre y no hay nada más; vacía si no hay
    nada. Cualquier otra cosa es una escritura a medias o un fichero ajeno.
    """
    if not names:
        return DayState.MISSING
    stems: dict[str, set[str]] = {}
    for name in names:
        stem, _, extension = name.rpartition(".")
        stems.setdefault(stem, set()).add(extension)
    if all(extensions == {"zip", "json"} for extensions in stems.values()):
        return DayState.COMPLETE
    return DayState.PARTIAL


def parse_detail(body: bytes, archive_id: int, day: date) -> ArchiveDetail:
    """Lee la ficha y comprueba que es la del archivo y el día pedidos.

    La URL de descarga tiene que ser una ruta de e·sios (``/archives/<id>/download``): se le
    antepone el origen fijo de la API. Seguir una URL absoluta de la ficha enviaría el token
    al host que dijera. Lanza ``ArchiveError`` si algo no cuadra.
    """
    try:
        archive = json.loads(body.decode("utf-8"))["archive"]
        found_id = archive["id"]
        found_day = datetime.fromisoformat(archive["date"]["date"]).date()
        url = archive["download"]["url"]
        detail = ArchiveDetail(
            name=archive["name"],
            download_url=ESIOS_BASE_URL + url,
            publication_dates=list(archive["publication_date"]),
        )
    except (KeyError, TypeError, ValueError) as err:
        raise ArchiveError(f"ficha ilegible: {type(err).__name__}: {err}") from err
    if found_id != archive_id or found_day != day:
        raise ArchiveError(f"ficha de {found_id} ({found_day}), se pidió {archive_id} ({day})")
    parts = urlsplit(url)
    if parts.scheme or parts.netloc or parts.path != f"/archives/{archive_id}/download":
        raise ArchiveError(f"URL de descarga inesperada: {url}")
    return detail


def _without_query(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def _get(
    session: requests.Session,
    url: str,
    params: dict[str, str],
    token: str,
    clock: Clock,
) -> Fetched:
    """GET a e·sios con el token, siguiendo como mucho una redirección y sin el token.

    e·sios puede redirigir la descarga a otro host (un almacén de ficheros con URL
    prefirmada). ``requests`` reenvía las cabeceras propias al seguir una redirección, así
    que el token llegaría a ese host: la redirección se sigue a mano y sin él.
    """
    headers = {"Accept": ACCEPT, "User-Agent": USER_AGENT, "x-api-key": token}
    requested_at = clock()
    redirected_to = None
    try:
        response = session.get(
            url, params=params, headers=headers, timeout=TIMEOUT_SECONDS, allow_redirects=False
        )
        if response.status_code in _REDIRECT_CODES:
            location = response.headers.get("Location", "")
            if urlsplit(location).scheme != "https":
                raise EsiosError(f"e·sios, {url}: redirección no HTTPS")
            redirected_to = _without_query(location)
            response = session.get(
                location,
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT_SECONDS,
                allow_redirects=False,
            )
        response.raise_for_status()
    except requests.RequestException as err:
        raise EsiosError(f"e·sios, {url}: {err}") from err
    if response.status_code != requests.codes.ok:
        raise EsiosError(f"e·sios, {url}: código {response.status_code}")
    return Fetched(
        url=url,
        params=params,
        status_code=response.status_code,
        body=response.content,
        server_date=response.headers.get("Date"),
        requested_at=requested_at,
        received_at=clock(),
        redirected_to=redirected_to,
    )


def _timing(fetched: Fetched) -> dict[str, Any]:
    return {
        "request": {"method": "GET", "url": fetched.url, "params": fetched.params},
        "redirected_to": fetched.redirected_to,
        "requested_at": fetched.requested_at.astimezone(UTC).isoformat(),
        "received_at": fetched.received_at.astimezone(UTC).isoformat(),
        "status_code": fetched.status_code,
        "server_date": fetched.server_date,
    }


def build_sidecar(archive_id: int, day: date, detail: Fetched, file: Fetched) -> bytes:
    """JSON lateral del zip, en UTF-8: la ficha literal y los datos de las dos peticiones.

    La ficha va como texto, sin parsear, con el SHA-256 de sus bytes: conserva la fecha de
    publicación y todo lo demás tal como llegó. Del zip, su tamaño y su SHA-256. Las
    cabeceras de las peticiones no se guardan porque llevan el token.
    """
    sidecar = {
        "format_version": FORMAT_VERSION,
        "source": "esios",
        "archive_id": archive_id,
        "data_date": day.isoformat(),
        "detail": {
            **_timing(detail),
            "body_sha256": hashlib.sha256(detail.body).hexdigest(),
            "body": detail.body.decode("utf-8"),
        },
        "file": {
            **_timing(file),
            "size": len(file.body),
            "sha256": hashlib.sha256(file.body).hexdigest(),
        },
    }
    return (json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _file_names(reader: FileReader, directory: str) -> list[str]:
    return sorted(
        entry.name
        for entry in reader.list_directory_contents(directory)
        if entry.name is not None and not entry.is_directory
    )


def download_day(
    session: requests.Session,
    files: VolumeFiles,
    root: str,
    day: date,
    token: str,
    *,
    archive_id: int = I90_ARCHIVE_ID,
    clock: Clock = utc_now,
    sleep: Sleep = time.sleep,
) -> str | None:
    """Descarga el archivo del día ``day`` al Volume si aún no está, y devuelve la ruta del zip.

    Devuelve ``None`` sin hacer ninguna petición si el día ya está descargado. Si la carpeta
    está a medias, lanza ``IncompleteDayError`` y tampoco pide nada: nunca se repite una
    descarga de forma automática. La ficha y el zip se validan antes de guardar nada, porque
    una respuesta errónea guardada bloquearía la buena. El JSON se escribe el último: un zip
    sin JSON es una escritura a medias.
    """
    directory = day_dir(root, archive_id, day)
    # Crearla antes de listar: así existe aunque esté vacía, y listarla no falla.
    files.create_directory(directory)
    state = day_state(_file_names(files, directory))
    if state is DayState.COMPLETE:
        return None
    if state is DayState.PARTIAL:
        raise IncompleteDayError(f"{directory}: descarga a medias, revisar a mano")

    detail_url = f"{ESIOS_BASE_URL}/archives/{archive_id}"
    detail = _get(session, detail_url, detail_params(day), token, clock)
    parsed = parse_detail(detail.body, archive_id, day)
    sleep(PAUSE_SECONDS)
    file = _get(session, parsed.download_url, {}, token, clock)
    if not zipfile.is_zipfile(BytesIO(file.body)):
        raise ArchiveError(f"{parsed.download_url}: la respuesta no es un zip")

    stem = _stem(file.received_at)
    zip_path = posixpath.join(directory, f"{stem}.zip")
    files.upload(zip_path, BytesIO(file.body), overwrite=False)
    sidecar = build_sidecar(archive_id, day, detail, file)
    files.upload(posixpath.join(directory, f"{stem}.json"), BytesIO(sidecar), overwrite=False)
    return zip_path


def plan_days(start: date, end: date, today: date) -> list[date]:
    """Días de ``start`` a ``end``, ambos incluidos, que puede pedir una ejecución.

    Lanza ``ValueError`` si el rango está invertido, si pasa de ``MAX_DAYS_PER_RUN`` días o
    si llega a días que aún no pueden estar publicados (más recientes que ``today`` menos
    ``PUBLICATION_LAG``). Se valida todo antes de la primera petición.
    """
    if end < start:
        raise ValueError(f"rango invertido: {start} > {end}")
    count = (end - start).days + 1
    if count > MAX_DAYS_PER_RUN:
        raise ValueError(f"{count} días: el tope por ejecución es {MAX_DAYS_PER_RUN}")
    latest = today - PUBLICATION_LAG
    if end > latest:
        raise ValueError(f"{end} aún no puede estar publicado: el último día posible es {latest}")
    return [start + timedelta(days=n) for n in range(count)]


def download_days(
    session: requests.Session,
    files: VolumeFiles,
    root: str,
    days: Iterable[date],
    token: str,
    *,
    archive_id: int = I90_ARCHIVE_ID,
    clock: Clock = utc_now,
    sleep: Sleep = time.sleep,
) -> Iterator[tuple[date, str | None]]:
    """Descarga los días en orden y va dando ``(día, ruta del zip o None si ya estaba)``.

    Pausa antes de cada día que sigue a uno con peticiones; los días ya descargados no hacen
    ninguna y no esperan. El primer error corta la serie: los días siguientes no se piden, y
    al repetir la ejecución la guarda de ``download_day`` salta los que ya están.
    """
    requested = False
    for day in days:
        if requested:
            sleep(PAUSE_SECONDS)
        path = download_day(
            session, files, root, day, token, archive_id=archive_id, clock=clock, sleep=sleep
        )
        requested = path is not None
        yield day, path
