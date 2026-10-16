"""Copia privada de las instantáneas: escribe en una carpeta local los ficheros nuevos del Volume.

La carpeta es un clon del repositorio privado de la copia; el workflow hace después el
commit y el push. Como en el Volume, los ficheros son inmutables: uno que ya está en la
copia no se sobrescribe nunca, y si llega con otro contenido es un fallo de integridad,
porque alguien ha cambiado el fichero en el Volume o en la copia.
"""

import posixpath
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath


class BackupError(ValueError):
    """Una ruta del Volume que no se puede copiar con seguridad."""


@dataclass
class BackupResult:
    """Qué hizo la copia: ficheros añadidos, ya presentes y presentes con otro contenido."""

    added: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    mismatched: list[str] = field(default_factory=list)


def backup_path(volume_root: str, path: str, backup_dir: Path) -> Path:
    """Ruta en la copia de un fichero del Volume: ``<copia>/<nombre del Volume>/<ruta relativa>``.

    La ruta viene de un listado remoto, así que se normaliza y se exige que quede dentro de
    ``volume_root``: ninguna ruta puede escribir fuera de la carpeta de la copia.
    """
    root = posixpath.normpath(volume_root)
    normalized = posixpath.normpath(path)
    if not normalized.startswith(root + "/"):
        raise BackupError(f"ruta fuera del Volume {root}: {path}")
    relative = PurePosixPath(normalized.removeprefix(root + "/"))
    return backup_dir.joinpath(posixpath.basename(root), *relative.parts)


def sync_to_backup(
    files: Iterable[tuple[str, bytes]], volume_root: str, backup_dir: Path
) -> BackupResult:
    """Escribe en la copia los ficheros ``(ruta, contenido)`` que aún no están.

    No sobrescribe nunca: un fichero ya presente con el mismo contenido se deja como está, y
    uno con otro contenido se anota en ``mismatched`` sin tocarlo.
    """
    result = BackupResult()
    for path, data in files:
        target = backup_path(volume_root, path, backup_dir)
        if target.exists():
            same = target.read_bytes() == data
            (result.unchanged if same else result.mismatched).append(path)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        # "x": la creación falla si el fichero apareció entretanto, en vez de pisarlo.
        with target.open("xb") as handle:
            handle.write(data)
        result.added.append(path)
    return result
