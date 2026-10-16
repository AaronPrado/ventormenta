"""Lectura de las instantáneas del Volume con la Files API de Databricks.

El vigilante solo lee: recorre las carpetas de captura que pueden contener los días de la
ventana y descarga lo que haya dentro. Las llamadas pasan por ``FileReader``, con lo que se
usa de ``WorkspaceClient().files``: el paquete no depende del SDK y los tests usan un doble.
"""

import posixpath
from collections.abc import Iterable, Iterator
from datetime import date, timedelta
from typing import BinaryIO, Protocol

from ventormenta.esios import NATIVE_STEPS
from ventormenta.snapshots import capture_dir_name, indicator_dir, indicators_root

# Una captura válida para D se hace antes de las 12:00 peninsulares de D-1, que en UTC cae
# en D-1 o, entre la medianoche peninsular y la UTC, en D-2.
_CAPTURE_LEAD_DAYS = 2


class DirectoryEntry(Protocol):
    """Lo que se usa de una entrada de directorio de la Files API."""

    @property
    def name(self) -> str | None: ...

    @property
    def is_directory(self) -> bool | None: ...


class Download(Protocol):
    """Lo que se usa de la respuesta de una descarga."""

    @property
    def contents(self) -> BinaryIO | None: ...


class FileReader(Protocol):
    """Lo que la lectura necesita de la Files API (``WorkspaceClient().files``)."""

    def list_directory_contents(self, directory_path: str) -> Iterator[DirectoryEntry]: ...

    def download(self, file_path: str) -> Download: ...


class VolumeError(RuntimeError):
    """La Files API devolvió algo que no se puede usar."""


def capture_dates(days: Iterable[date]) -> list[date]:
    """Fechas UTC de las carpetas de captura que pueden contener sobres de ``days``.

    Van desde dos días antes del primero hasta el último: cubren las capturas válidas y las
    tardías, que el vigilante tiene que ver para decir que llegaron tarde.
    """
    ordered = sorted(days)
    if not ordered:
        return []
    first = ordered[0] - timedelta(days=_CAPTURE_LEAD_DAYS)
    return [first + timedelta(days=n) for n in range((ordered[-1] - first).days + 1)]


def _names(reader: FileReader, directory: str, *, directories: bool) -> list[str]:
    """Nombres ordenados de las carpetas (o de los ficheros) que hay en ``directory``."""
    names: list[str] = []
    for entry in reader.list_directory_contents(directory):
        if entry.name is not None and bool(entry.is_directory) == directories:
            names.append(entry.name)
    return sorted(names)


def _download(reader: FileReader, path: str) -> bytes:
    contents = reader.download(path).contents
    if contents is None:
        raise VolumeError(f"descarga sin contenido: {path}")
    with contents:
        return contents.read()


def download_window(reader: FileReader, root: str, days: Iterable[date]) -> list[tuple[str, bytes]]:
    """Descarga los ficheros de las carpetas de captura de ``days``, como ``(ruta, contenido)``.

    Primero lista lo que existe y solo entra ahí: un indicador o un día sin capturas no es
    un error de lectura, sino el resultado que el vigilante tiene que notificar. Se descarga
    cualquier fichero de esas carpetas, sea o no un sobre, para que nada ajeno pase
    inadvertido.
    """
    wanted = {capture_dir_name(day) for day in capture_dates(days)}
    present = set(_names(reader, indicators_root(root), directories=True))
    files: list[tuple[str, bytes]] = []
    for indicator_id in sorted(NATIVE_STEPS):
        if str(indicator_id) not in present:
            continue
        base = indicator_dir(root, indicator_id)
        for folder in _names(reader, base, directories=True):
            if folder not in wanted:
                continue
            directory = posixpath.join(base, folder)
            for name in _names(reader, directory, directories=False):
                path = posixpath.join(directory, name)
                files.append((path, _download(reader, path)))
    return files
