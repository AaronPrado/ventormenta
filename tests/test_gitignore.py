"""Comprueba que ``.gitignore`` deja fuera del repositorio los ficheros sensibles o locales."""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Rutas de ejemplo: no tienen que existir, basta con que una regla de .gitignore las cubra.
IGNORED_PATHS = [
    ".env",
    ".envrc",
    ".venv/",
    ".claude/settings.json",
    ".databricks/bundle/state.json",
]


@pytest.mark.parametrize("path", IGNORED_PATHS)
def test_path_is_ignored(path: str) -> None:
    # --no-index evalúa solo las reglas, aunque la ruta llegara a estar en el índice.
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--no-index", path],
        cwd=REPO_ROOT,
        check=False,
    )
    # Códigos de git check-ignore: 0 ignorada, 1 no ignorada, 128 error.
    assert result.returncode == 0, f"{path} no está cubierta por .gitignore"
