"""Instantáneas de e·sios: sobre JSON, ruta en el Volume, escritura inmutable y validación.

Cada captura se guarda en un fichero propio que no se sobrescribe nunca. El sobre lleva el
cuerpo de la respuesta literal y los instantes de la captura; ``received_at`` es su
``available_at`` (clase de disponibilidad observada).
"""

import base64
import hashlib
import json
import posixpath
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


def snapshot_path(root: str, indicator_id: int, received_at: datetime) -> str:
    """Ruta de la captura: ``<root>/indicators/<id>/capture_date=<fecha>/<instante>.json``.

    Fecha e instante van en UTC, así que no hay ambigüedad en los cambios de hora; el
    instante va en formato ISO 8601 básico porque los ``:`` dan problemas en las rutas.
    """
    moment = _as_utc(received_at)
    return posixpath.join(
        root,
        "indicators",
        str(indicator_id),
        f"capture_date={moment:%Y-%m-%d}",
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
        return Completeness(Status.UNREADABLE, expected, 0, f"respuesta ilegible: {err!r}")

    found = len(in_day)
    if not moments:
        return Completeness(Status.NOT_PUBLISHED, expected, 0, "sin valores")
    outside = len(moments) - found
    repeated = found - len(set(in_day))
    detail = f"{found} valores del día de {expected}, {outside} fuera del día, {repeated} repetidos"
    if found == expected and not outside and not repeated:
        return Completeness(Status.COMPLETE, expected, found, detail)
    return Completeness(Status.UNEXPECTED, expected, found, detail)
