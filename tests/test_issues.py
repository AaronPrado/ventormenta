"""Tests de los issues del vigilante: contenido, deduplicación y llamadas a la API de GitHub."""

from collections.abc import Iterator
from datetime import date

import pytest
import requests
import responses
from responses import matchers

from ventormenta.issues import (
    LABEL,
    GitHubError,
    GitHubIssues,
    Issue,
    access_issue,
    day_issues,
    integrity_issues,
    publish,
)
from ventormenta.watchdog import Corrupt, DayCheck, Verdict

TOKEN = "token-de-prueba"  # noqa: S105  (valor ficticio para los tests)
REPOSITORY = "AaronPrado/ventormenta"
ISSUES_URL = f"https://api.github.com/repos/{REPOSITORY}/issues"
RUN_URL = f"https://github.com/{REPOSITORY}/actions/runs/1"
DAY = date(2026, 10, 16)


def check(day: date, indicator_id: int, verdict: Verdict, reason: str = "motivo") -> DayCheck:
    return DayCheck(day, indicator_id, verdict, reason, None)


@pytest.fixture
def mocked() -> Iterator[responses.RequestsMock]:
    # Falla si alguna respuesta registrada no se llega a pedir.
    with responses.RequestsMock(assert_all_requests_are_fired=True) as rsps:
        yield rsps


@pytest.fixture
def client() -> Iterator[GitHubIssues]:
    with requests.Session() as session:
        yield GitHubIssues(session, REPOSITORY, TOKEN)


# --- Contenido ---


def test_one_issue_per_day_with_problems() -> None:
    checks = [
        check(DAY, 541, Verdict.OK),
        check(DAY, 1777, Verdict.FAILURE, "sin capturas"),
        check(date(2026, 10, 17), 541, Verdict.OK),
        check(date(2026, 10, 17), 1777, Verdict.OK),
    ]
    (issue,) = day_issues(checks, RUN_URL)
    assert issue.title == "Vigilante: instantáneas del 2026-10-16"
    assert issue.labels == (LABEL, "fallo")
    assert "12:00 peninsulares del 2026-10-15" in issue.body
    assert "sin capturas" in issue.body
    assert RUN_URL in issue.body


def test_a_day_with_only_warnings_gets_the_warning_label() -> None:
    (issue,) = day_issues([check(DAY, 541, Verdict.WARNING), check(DAY, 1777, Verdict.OK)], RUN_URL)
    assert issue.labels == (LABEL, "aviso")


def test_failure_wins_over_warning_in_the_same_day() -> None:
    checks = [check(DAY, 541, Verdict.WARNING), check(DAY, 1777, Verdict.FAILURE)]
    (issue,) = day_issues(checks, RUN_URL)
    assert issue.labels == (LABEL, "fallo")


def test_integrity_issues_name_the_file() -> None:
    corrupt = [Corrupt("/v/541/a.json", "no es un sobre JSON")]
    mismatched = ["/v/1777/b.json"]
    issues = integrity_issues(corrupt, mismatched, RUN_URL)
    assert [issue.title for issue in issues] == [
        "Vigilante: fichero no válido en el Volume: /v/541/a.json",
        "Vigilante: la copia privada no coincide con el Volume: /v/1777/b.json",
    ]
    assert all(issue.labels == (LABEL, "fallo") for issue in issues)
    assert "no es un sobre JSON" in issues[0].body


def test_access_issue_names_only_the_error_class() -> None:
    issue = access_issue(DAY, "PermissionDenied", RUN_URL)
    assert issue.title == "Vigilante: sin acceso a Databricks el 2026-10-16"
    assert "PermissionDenied" in issue.body


# --- API de GitHub ---


def test_titles_reads_every_page(mocked: responses.RequestsMock, client: GitHubIssues) -> None:
    next_page = f"{ISSUES_URL}?page=2"
    mocked.get(
        ISSUES_URL,
        match=[
            matchers.query_param_matcher({"state": "all", "labels": LABEL, "per_page": "100"}),
            matchers.header_matcher({"Authorization": f"Bearer {TOKEN}"}),
        ],
        json=[{"title": "uno"}],
        headers={"Link": f'<{next_page}>; rel="next"'},
    )
    mocked.get(next_page, json=[{"title": "dos"}])
    assert client.titles(LABEL) == {"uno", "dos"}


def test_create_posts_title_body_and_labels(
    mocked: responses.RequestsMock, client: GitHubIssues
) -> None:
    issue = Issue("título", "cuerpo", (LABEL, "fallo"))
    mocked.post(
        ISSUES_URL,
        match=[
            matchers.json_params_matcher(
                {"title": "título", "body": "cuerpo", "labels": [LABEL, "fallo"]}
            )
        ],
        json={"html_url": f"https://github.com/{REPOSITORY}/issues/7"},
        status=201,
    )
    assert client.create(issue) == f"https://github.com/{REPOSITORY}/issues/7"


def test_publish_skips_existing_titles_and_repeats(
    mocked: responses.RequestsMock, client: GitHubIssues
) -> None:
    mocked.get(ISSUES_URL, json=[{"title": "ya existe"}])
    mocked.post(
        ISSUES_URL,
        match=[matchers.json_params_matcher({"title": "nuevo"}, strict_match=False)],
        json={"html_url": "https://github.com/x/issues/8"},
        status=201,
    )
    issues = [
        Issue("ya existe", "", (LABEL,)),
        Issue("nuevo", "", (LABEL,)),
        Issue("nuevo", "", (LABEL,)),
    ]
    assert publish(client, issues) == ["https://github.com/x/issues/8"]


def test_http_error_raises_without_the_token(
    mocked: responses.RequestsMock, client: GitHubIssues
) -> None:
    mocked.get(ISSUES_URL, status=500)
    with pytest.raises(GitHubError) as excinfo:
        client.titles(LABEL)
    assert TOKEN not in str(excinfo.value)
