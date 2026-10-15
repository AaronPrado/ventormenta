"""Issues del vigilante: uno por cada día D con problemas y uno por cada fallo de integridad.

El título identifica el problema y no se repite nunca: antes de abrir un issue se leen los
que ya existen, abiertos o cerrados, así que revisar el mismo día varias veces (la ventana
del vigilante) no duplica avisos. Los cuerpos llevan solo metadatos, nunca valores de Red
Eléctrica, porque el repositorio es público.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import requests

from ventormenta.esios import USER_AGENT
from ventormenta.watchdog import Corrupt, DayCheck, Verdict, overall, render_report

GITHUB_API = "https://api.github.com"
TIMEOUT_SECONDS = 30
# Etiqueta común de los issues del vigilante: es por la que se buscan los que ya existen.
LABEL = "vigilante"
_SEVERITY_LABELS = {Verdict.WARNING: "aviso", Verdict.FAILURE: "fallo"}


@dataclass(frozen=True)
class Issue:
    """Un issue por abrir: el título es su identidad."""

    title: str
    body: str
    labels: tuple[str, ...]


def _footer(run_url: str) -> str:
    return f"\n---\nAbierto por el vigilante en la ejecución {run_url}\n"


def day_issues(checks: Sequence[DayCheck], run_url: str) -> list[Issue]:
    """Un issue por cada día D en el que algún indicador no está ``ok``."""
    issues: list[Issue] = []
    for day in sorted({check.day for check in checks}):
        own = [check for check in checks if check.day == day]
        worst = overall(own, [])
        if worst is Verdict.OK:
            continue
        summary = (
            "No hay una captura completa anterior al corte"
            if worst is Verdict.FAILURE
            else "Solo hay capturas con un recuento inesperado"
        )
        cutoff_day = day - timedelta(days=1)
        body = (
            f"{summary} para el día D {day} (corte: 12:00 peninsulares del {cutoff_day}).\n\n"
            f"{render_report(own, [])}{_footer(run_url)}"
        )
        title = f"Vigilante: instantáneas del {day}"
        issues.append(Issue(title, body, (LABEL, _SEVERITY_LABELS[worst])))
    return issues


def integrity_issues(
    corrupt: Sequence[Corrupt], mismatched: Sequence[str], run_url: str
) -> list[Issue]:
    """Un issue por cada fichero que no es un sobre válido o que no coincide con la copia."""
    issues = [
        Issue(
            f"Vigilante: fichero no válido en el Volume: {item.path}",
            f"`{item.path}` no es un sobre válido: {item.reason}.\n{_footer(run_url)}",
            (LABEL, "fallo"),
        )
        for item in corrupt
    ]
    issues += [
        Issue(
            f"Vigilante: la copia privada no coincide con el Volume: {path}",
            f"`{path}` ya estaba en la copia privada con otro contenido. Los ficheros son "
            "inmutables, así que alguien ha cambiado el Volume o la copia. No se ha "
            f"sobrescrito nada.\n{_footer(run_url)}",
            (LABEL, "fallo"),
        )
        for path in mismatched
    ]
    return issues


def access_issue(run_date: date, error_class: str, run_url: str) -> Issue:
    """Issue de un día en el que el vigilante no pudo leer Databricks.

    Solo lleva la clase del error: los mensajes del SDK incluyen datos de la cuenta, y el
    issue es público. El detalle se reproduce ejecutando el vigilante en local.
    """
    body = (
        f"El vigilante no pudo leer el Volume ({error_class}). Causas probables: Databricks "
        "caído, secreto del service principal caducado o revocado, o permisos cambiados.\n"
        f"{_footer(run_url)}"
    )
    return Issue(f"Vigilante: sin acceso a Databricks el {run_date}", body, (LABEL, "fallo"))


class GitHubError(RuntimeError):
    """Falló una llamada a la API de GitHub: red, tiempo de espera o código HTTP de error."""


class GitHubIssues:
    """Lo que usa el vigilante de la API REST de issues de GitHub."""

    def __init__(
        self, session: requests.Session, repository: str, token: str, api_url: str = GITHUB_API
    ) -> None:
        self._session = session
        self._url = f"{api_url}/repos/{repository}/issues"
        self._headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
    ) -> requests.Response:
        try:
            response = self._session.request(
                method,
                url,
                params=params,
                json=json,
                headers=self._headers,
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.RequestException as err:
            # Sin las cabeceras: llevan el token.
            raise GitHubError(f"GitHub, {method} {url}: {type(err).__name__}: {err}") from err
        return response

    def titles(self, label: str) -> set[str]:
        """Títulos de los issues con ``label``, abiertos o cerrados, de todas las páginas."""
        titles: set[str] = set()
        url: str | None = self._url
        params: dict[str, str] | None = {"state": "all", "labels": label, "per_page": "100"}
        while url is not None:
            response = self._request("GET", url, params=params)
            titles.update(item["title"] for item in response.json())
            url = response.links.get("next", {}).get("url")
            # La URL de la página siguiente ya lleva los parámetros.
            params = None
        return titles

    def create(self, issue: Issue) -> str:
        """Abre el issue y devuelve su URL."""
        payload: dict[str, object] = {
            "title": issue.title,
            "body": issue.body,
            "labels": list(issue.labels),
        }
        return str(self._request("POST", self._url, json=payload).json()["html_url"])


def publish(client: GitHubIssues, issues: Iterable[Issue]) -> list[str]:
    """Abre los issues cuyo título aún no existe y devuelve las URL de los que ha abierto."""
    existing = client.titles(LABEL)
    created: list[str] = []
    for issue in issues:
        if issue.title in existing:
            continue
        created.append(client.create(issue))
        existing.add(issue.title)
    return created
