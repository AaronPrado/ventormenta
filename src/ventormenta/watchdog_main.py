"""Punto de entrada del vigilante: ``python -m ventormenta.watchdog_main``.

Lee la ventana de instantáneas del Volume, actualiza la copia privada, decide el veredicto,
escribe el informe en el resumen de la ejecución y abre los issues. Es el único módulo que
importa el SDK de Databricks: el resto del paquete trabaja con ``Protocol`` y se prueba sin
él. Las credenciales de Databricks las lee el SDK de las variables de entorno.
"""

import argparse
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from functools import partial
from pathlib import Path
from typing import Protocol

import requests
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config

from ventormenta.backup import sync_to_backup
from ventormenta.esios import utc_now
from ventormenta.issues import (
    GitHubIssues,
    Issue,
    access_issue,
    day_issues,
    integrity_issues,
    publish,
)
from ventormenta.jobs import JobsReader, diagnose
from ventormenta.peninsular import MADRID
from ventormenta.volume import FileReader, download_window
from ventormenta.watchdog import (
    VERDICT_LABELS,
    Verdict,
    check_window,
    decided_days,
    overall,
    read_captures,
    render_report,
)

# Los scopes del secreto del service principal: el SDK pide «all-apis» por defecto y el
# secreto lo rechaza. Son además el límite de lo que podría hacer el token si se filtrara.
SCOPES = ["files", "jobs"]
VOLUME_ROOT = "/Volumes/ventormenta/raw/esios"

Publisher = Callable[[list[Issue]], list[str]]


@dataclass(frozen=True)
class Outcome:
    """Resultado de una ejecución: veredicto global, informe e issues."""

    verdict: Verdict
    report: str
    issues: list[Issue]
    created: list[str]


def run(
    files: list[tuple[str, bytes]],
    days: Sequence[date],
    volume_root: str,
    backup_dir: Path | None,
    publisher: Publisher | None,
    run_url: str,
    diagnosis: Mapping[date, str] | None = None,
) -> Outcome:
    """Copia, evalúa y avisa a partir de los ficheros ya descargados de la ventana.

    Sin ``backup_dir`` no se toca la copia; sin ``publisher`` no se abre ningún issue
    (ejecución en seco) y el informe dice cuáles se abrirían.
    """
    mismatched: list[str] = []
    backup_line = "Copia privada: no actualizada (sin carpeta de copia)."
    if backup_dir is not None:
        backup = sync_to_backup(files, volume_root, backup_dir)
        mismatched = backup.mismatched
        backup_line = (
            f"Copia privada: {len(backup.added)} ficheros nuevos, {len(backup.unchanged)} ya "
            f"copiados, {len(mismatched)} con otro contenido."
        )

    captures, corrupt = read_captures(files)
    checks = check_window(days, captures)
    issues = day_issues(checks, run_url, diagnosis)
    issues += integrity_issues(corrupt, mismatched, run_url)
    created = publisher(issues) if publisher is not None and issues else []

    verdict = Verdict.FAILURE if mismatched else overall(checks, corrupt)
    lines = [f"## Vigilante de instantáneas: {VERDICT_LABELS[verdict]}", ""]
    lines += [render_report(checks, corrupt), backup_line]
    if diagnosis:
        lines += ["", "Ejecuciones del job antes del corte:"]
        lines += [f"- {day}: {diagnosis[day]}" for day in sorted(diagnosis)]
    if publisher is None and issues:
        lines += ["", "En seco: se abrirían, si no existen ya:"]
        lines += [f"- {issue.title}" for issue in issues]
    elif created:
        lines += ["", "Issues abiertos:", *(f"- {url}" for url in created)]
    return Outcome(verdict, "\n".join(lines) + "\n", issues, created)


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m ventormenta.watchdog_main",
        description="Vigilante de las instantáneas de e·sios.",
    )
    parser.add_argument("--volume-root", default=VOLUME_ROOT)
    parser.add_argument(
        "--backup-dir", type=Path, help="clon del repositorio de la copia; sin él no se copia"
    )
    parser.add_argument(
        "--target-date",
        type=date.fromisoformat,
        help="revisa solo este día D (AAAA-MM-DD) en vez de la ventana",
    )
    parser.add_argument("--dry-run", action="store_true", help="no abre issues: los lista")
    return parser.parse_args(argv)


def _run_url(env: Mapping[str, str]) -> str:
    try:
        server, repository, run_id = (
            env["GITHUB_SERVER_URL"],
            env["GITHUB_REPOSITORY"],
            env["GITHUB_RUN_ID"],
        )
    except KeyError:
        return "(ejecución local)"
    return f"{server}/{repository}/actions/runs/{run_id}"


class Workspace(Protocol):
    """Lo que el vigilante usa del cliente de Databricks: un token para las dos APIs."""

    @property
    def files(self) -> FileReader: ...

    @property
    def jobs(self) -> JobsReader: ...


def _workspace() -> Workspace:
    return WorkspaceClient(config=Config(scopes=SCOPES))


def _write_summary(report: str) -> None:
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write(report)


def main(argv: Sequence[str] | None = None) -> int:
    """Ejecuta el vigilante y devuelve el código de salida: 1 si hay algún fallo."""
    args = _parse(argv)
    days = [args.target_date] if args.target_date else decided_days(utc_now())
    run_url = _run_url(os.environ)
    with requests.Session() as session:
        publisher: Publisher | None = None
        if not args.dry_run:
            try:
                repository, token = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"]
            except KeyError as err:
                raise SystemExit(f"falta la variable {err}; en local, usa --dry-run") from err
            publisher = partial(publish, GitHubIssues(session, repository, token))

        try:
            workspace = _workspace()
            files = download_window(workspace.files, args.volume_root, days)
        except Exception as err:
            # Cualquier fallo al leer Databricks es el aviso de «sin acceso». Solo la clase:
            # el mensaje del SDK lleva datos de la cuenta, y el log y el issue son públicos.
            error_class = type(err).__name__
            print(f"Sin acceso a Databricks: {error_class}", file=sys.stderr)
            if publisher is not None:
                today = utc_now().astimezone(MADRID).date()
                publisher([access_issue(today, error_class, run_url)])
            return 1

        try:
            diagnosis = diagnose(workspace.jobs, days)
        except Exception as err:
            # El diagnóstico es contexto: si falla, el veredicto de los ficheros sigue valiendo.
            diagnosis = dict.fromkeys(days, f"diagnóstico no disponible ({type(err).__name__})")

        outcome = run(files, days, args.volume_root, args.backup_dir, publisher, run_url, diagnosis)
    _write_summary(outcome.report)
    return 1 if outcome.verdict is Verdict.FAILURE else 0


if __name__ == "__main__":
    sys.exit(main())
