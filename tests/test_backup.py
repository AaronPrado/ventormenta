"""Tests de la copia privada: qué se escribe, qué no se toca y qué rutas se rechazan."""

from pathlib import Path

import pytest

from ventormenta.backup import BackupError, backup_path, sync_to_backup

ROOT = "/Volumes/ventormenta/raw/esios"
FILE_541 = f"{ROOT}/indicators/541/capture_date=2026-10-15/20261015T090052Z.json"
FILE_1777 = f"{ROOT}/indicators/1777/capture_date=2026-10-15/20261015T090032Z.json"


def test_backup_path_mirrors_the_volume_under_its_name(tmp_path: Path) -> None:
    expected = tmp_path / "esios/indicators/541/capture_date=2026-10-15/20261015T090052Z.json"
    assert backup_path(ROOT, FILE_541, tmp_path) == expected


@pytest.mark.parametrize(
    "path",
    [
        "/Volumes/ventormenta/raw/otro/indicators/541/x.json",
        f"{ROOT}/../otro/x.json",
        f"{ROOT}/indicators/../../otro/x.json",
        ROOT,
        "indicators/541/x.json",
    ],
    ids=["otro-volume", "sube-un-nivel", "sube-dos-niveles", "la-raiz", "relativa"],
)
def test_backup_path_rejects_paths_outside_the_volume(tmp_path: Path, path: str) -> None:
    with pytest.raises(BackupError, match="fuera del Volume"):
        backup_path(ROOT, path, tmp_path)


def test_new_files_are_written(tmp_path: Path) -> None:
    result = sync_to_backup([(FILE_541, b"a"), (FILE_1777, b"b")], ROOT, tmp_path)
    assert result.added == [FILE_541, FILE_1777]
    assert backup_path(ROOT, FILE_541, tmp_path).read_bytes() == b"a"
    assert backup_path(ROOT, FILE_1777, tmp_path).read_bytes() == b"b"


def test_files_already_in_the_backup_are_left_alone(tmp_path: Path) -> None:
    sync_to_backup([(FILE_541, b"a")], ROOT, tmp_path)
    result = sync_to_backup([(FILE_541, b"a")], ROOT, tmp_path)
    assert result.added == []
    assert result.unchanged == [FILE_541]
    assert result.mismatched == []


def test_a_file_with_other_contents_is_reported_and_not_overwritten(tmp_path: Path) -> None:
    sync_to_backup([(FILE_541, b"original")], ROOT, tmp_path)
    result = sync_to_backup([(FILE_541, b"cambiado")], ROOT, tmp_path)
    assert result.mismatched == [FILE_541]
    assert result.added == []
    assert backup_path(ROOT, FILE_541, tmp_path).read_bytes() == b"original"
