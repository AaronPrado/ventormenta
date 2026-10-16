"""Instantáneas de e·sios: sobre JSON, ruta en el Volume, escritura inmutable y validación.

Cada captura se guarda en un fichero propio que no se sobrescribe nunca. El sobre lleva el
cuerpo de la respuesta literal y los instantes de la captura; ``received_at`` es su
``available_at`` (clase de disponibilidad observada).
"""

import base64
import hashlib
import json
import posixpath
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from io import BytesIO
from typing import BinaryIO, Protocol

from ventormenta.esios import RawResponse
from ventormenta.peninsular import day_bounds, intervals_in_day

# Sube si cambia la estructura del sobre, para que bronze sepa cómo leer cada fichero.
FORMAT_VERSION = 1


class FileUploader(Protocol):
    """Lo que la escritura necesita de la Files API de Databricks (``WorkspaceClient().files``).

    Definirlo aquí evita que el paquete dependa del SDK y permite un doble en los tests.
    """

    def create_directory(self, directory_path: str) -> object: ...

    def upload(
        self, file_path: str, contents: BinaryIO, *, overwrite: bool | None = None
    ) -> object: ...


def _as_utc(moment: datetime) -> datetime:
    if moment.utcoffset() is None:
        raise ValueError("el instante necesita zona horaria")
    return moment.astimezone(UTC)


def indicators_root(root: str) -> str:
    """Carpeta con una subcarpeta por indicador: ``<root>/indicators``."""
    return posixpath.join(root, "indicators")


def indicator_dir(root: str, indicator_id: int) -> str:
    """Carpeta de un indicador: ``<root>/indicators/<id>``."""
    return posixpath.join(indicators_root(root), str(indicator_id))


def capture_dir_name(capture_date: date) -> str:
    """Nombre de la carpeta de una fecha de captura UTC, en formato ``clave=valor``."""
    return f"capture_date={capture_date:%Y-%m-%d}"


def snapshot_path(root: str, indicator_id: int, received_at: datetime) -> str:
    """Ruta de la captura: ``<root>/indicators/<id>/capture_date=<fecha>/<instante>.json``.

    Fecha e instante van en UTC, así que no hay ambigüedad en los cambios de hora; el
    instante va en formato ISO 8601 básico porque los ``:`` dan problemas en las rutas.
    """
    moment = _as_utc(received_at)
    return posixpath.join(
        indicator_dir(root, indicator_id),
        capture_dir_name(moment.date()),
        f"{moment:%Y%m%dT%H%M%SZ}.json",
    )


def build_envelope(raw: RawResponse, target_date: date) -> bytes:
    """Sobre JSON de la captura, en UTF-8.

    El cuerpo va como texto literal, sin parsear, con el SHA-256 de sus bytes para poder
    comprobarlo. Si no es UTF-8 válido, va en base64: así se guarda cualquier respuesta sin
    perder nada. Las cabeceras de la petición no se guardan porque llevan el token.
    """
    try:
        body, encoding = raw.body.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        body, encoding = base64.b64encode(raw.body).decode("ascii"), "base64"
    envelope = {
        "format_version": FORMAT_VERSION,
        "source": "esios",
        "indicator_id": raw.indicator_id,
        "target_date": target_date.isoformat(),
        "request": {"method": "GET", "url": raw.url, "params": raw.params},
        "requested_at": _as_utc(raw.requested_at).isoformat(),
        "received_at": _as_utc(raw.received_at).isoformat(),
        "response": {
            "status_code": raw.status_code,
            "server_date": raw.server_date,
            "body_sha256": hashlib.sha256(raw.body).hexdigest(),
            "body_encoding": encoding,
            "body": body,
        },
    }
    return (json.dumps(envelope, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


class EnvelopeError(ValueError):
    """El fichero no es un sobre legible de esta versión, o su cuerpo no cuadra con el hash."""


# Inversas de las codificaciones del cuerpo que usa build_envelope.
_BODY_DECODERS: dict[str, Callable[[str], bytes]] = {
    "utf-8": lambda text: text.encode("utf-8"),
    "base64": lambda text: base64.b64decode(text, validate=True),
}


def read_envelope(data: bytes) -> tuple[RawResponse, date]:
    """Lee un sobre: devuelve la respuesta tal como llegó y el día D pedido.

    Es la inversa de ``build_envelope``, así que lo leído pasa por ``check_completeness``
    igual que en la captura. Lanza ``EnvelopeError`` si el fichero no es un sobre de la
    versión actual, si le falta algo o si el cuerpo no cuadra con ``body_sha256``: en ese
    caso no es la respuesta que se recibió.
    """
    try:
        envelope = json.loads(data)
        version = envelope["format_version"]
    except (KeyError, TypeError, ValueError) as err:
        raise EnvelopeError(f"no es un sobre JSON: {type(err).__name__}: {err}") from err
    if version != FORMAT_VERSION:
        raise EnvelopeError(f"format_version {version!r} no soportada (se espera {FORMAT_VERSION})")

    try:
        request, response = envelope["request"], envelope["response"]
        body = _BODY_DECODERS[response["body_encoding"]](response["body"])
        raw = RawResponse(
            indicator_id=envelope["indicator_id"],
            url=request["url"],
            params=request["params"],
            status_code=response["status_code"],
            body=body,
            server_date=response["server_date"],
            requested_at=_as_utc(datetime.fromisoformat(envelope["requested_at"])),
            received_at=_as_utc(datetime.fromisoformat(envelope["received_at"])),
        )
        target_date = date.fromisoformat(envelope["target_date"])
        expected_sha256 = response["body_sha256"]
    except (KeyError, TypeError, ValueError) as err:
        raise EnvelopeError(f"sobre ilegible: {type(err).__name__}: {err}") from err

    if hashlib.sha256(body).hexdigest() != expected_sha256:
        raise EnvelopeError("el cuerpo no cuadra con body_sha256")
    return raw, target_date


def write_snapshot(uploader: FileUploader, root: str, raw: RawResponse, target_date: date) -> str:
    """Escribe la captura en el Volume sin sobrescribir y devuelve su ruta.

    Si el fichero ya existe, la Files API devuelve un error y la escritura falla: una
    captura nunca reemplaza a otra.
    """
    path = snapshot_path(root, raw.indicator_id, raw.received_at)
    uploader.create_directory(posixpath.dirname(path))
    uploader.upload(path, BytesIO(build_envelope(raw, target_date)), overwrite=False)
    return path


class Status(StrEnum):
    """Resultado de comprobar si la captura trae el día D completo."""

    COMPLETE = "complete"
    NOT_PUBLISHED = "not_published"
    UNREADABLE = "unreadable"
    UNEXPECTED = "unexpected"


@dataclass(frozen=True)
class Completeness:
    """Recuento de valores del día D en una captura, frente a los esperados."""

    status: Status
    expected: int
    found: int
    detail: str

    @property
    def retryable(self) -> bool:
        """Si merece la pena repetir la petición.

        Sí cuando el día aún no está publicado o la respuesta no se puede leer (p. ej., una
        página de mantenimiento). No ante un recuento inesperado: repetir devolvería lo
        mismo y sería una petición redundante a e·sios.
        """
        return self.status in (Status.NOT_PUBLISHED, Status.UNREADABLE)


def check_completeness(raw: RawResponse, target_date: date, step: timedelta) -> Completeness:
    """Comprueba que la captura trae exactamente un valor por intervalo del día D.

    Los intervalos esperados salen de la duración real del día (23, 24 o 25 horas). Cuenta
    también los valores fuera del día y los instantes repetidos, que hacen el recuento
    inesperado aunque el total cuadre.
    """
    expected = intervals_in_day(target_date, step)
    start, end = (_as_utc(bound) for bound in day_bounds(target_date))
    try:
        values = json.loads(raw.body)["indicator"]["values"]
        moments = [datetime.fromisoformat(value["datetime_utc"]) for value in values]
        in_day = [moment for moment in moments if start <= moment < end]
    except (ValueError, KeyError, TypeError) as err:
        # Sin repr: el de UnicodeDecodeError incluye el cuerpo entero, y el detalle acaba en
        # logs e issues públicos.
        detail = f"respuesta ilegible: {type(err).__name__}: {err}"
        return Completeness(Status.UNREADABLE, expected, 0, detail)

    found = len(in_day)
    if not moments:
        return Completeness(Status.NOT_PUBLISHED, expected, 0, "sin valores")
    outside = len(moments) - found
    repeated = found - len(set(in_day))
    detail = f"{found} valores del día de {expected}, {outside} fuera del día, {repeated} repetidos"
    if found == expected and not outside and not repeated:
        return Completeness(Status.COMPLETE, expected, found, detail)
    return Completeness(Status.UNEXPECTED, expected, found, detail)
