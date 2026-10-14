"""Comprueba que las herramientas fijadas en más de un sitio usan la misma versión."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _betterleaks_hook_version() -> str:
    config = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    match = re.search(
        r"repo: https://github\.com/betterleaks/betterleaks\s+rev: \S+\s+#\s*frozen:\s*v(\S+)",
        config,
    )
    assert match, "no se encuentra el hook de betterleaks con su comentario frozen"
    return match.group(1)


def _betterleaks_ci_version() -> str:
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    match = re.search(r'BETTERLEAKS_VERSION: "(\S+)"', workflow)
    assert match, "no se encuentra BETTERLEAKS_VERSION en el workflow de CI"
    return match.group(1)


def test_betterleaks_version_matches_between_hook_and_ci() -> None:
    # Dependabot actualiza el rev del hook, pero no la versión ni el hash fijados en la CI.
    assert _betterleaks_hook_version() == _betterleaks_ci_version()
