"""Tests del punto de entrada del vigilante: copia, veredicto, issues, informe y salida."""

import json
from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import responses
from responses import matchers

from ventormenta import watchdog_main
from ventormenta.esios import NATIVE_STEPS, RawResponse, day_params
from ventormenta.issues import LABEL, Issue
from ventormenta.peninsular import day_bounds
from ventormenta.snapshots import build_envelope, snapshot_path
from ventormenta.watchdog import Verdict
from ventormenta.watchdog_main import Workspace, main, run

ROOT = "/Volumes/ventormenta/raw/esios"
DAY = date(2026, 10, 16)
JOB_TIME = datetime(2026, 10, 15, 9, 0, 30, tzinfo=UTC)
RUN_URL = "https://github.com/AaronPrado/ventormenta/actions/runs/1"
ISSUES_URL = "https://api.github.com/repos/AaronPrado/ventormenta/issues"


def capture(indicator_id: int, day: date = DAY) -> tuple[str, bytes]:
    """Captura completa del día, como la escribe el job: ``(ruta en el Volume, sobre)``."""
    step = NATIVE_STEPS[indicator_id]
    start, end = (bound.astimezone(UTC) for bound in day_bounds(day))
    values = [
        {"datetime_utc": (start + i * step).isoformat(), "value": 1.0}
        for i in range((end - start) // step)
    ]
    raw = RawResponse(
        indicator_id=indicator_id,
        url=f"https://api.esios.ree.es/indicators/{indicator_id}",
        params=day_params(day),
        status_code=200,
        body=json.dumps({"indicator": {"values": values}}).encode(),
        server_date=None,
        requested_at=JOB_TIME - timedelta(seconds=1),
        received_at=JOB_TIME,
    )
    return snapshot_path(ROOT, indicator_id, JOB_TIME), build_envelope(raw, day)


class RecordingPublisher:
    """Doble del publicador de issues: guarda lo que recibe y devuelve URL ficticias."""

    def __init__(self) -> None:
        self.received: list[Issue] = []

    def __call__(self, issues: list[Issue]) -> list[str]:
        self.received += issues
        return [f"https://github.com/x/issues/{n}" for n in range(len(issues))]


# --- run ---


def test_all_ok_opens_no_issues() -> None:
    publisher = RecordingPublisher()
    outcome = run([capture(541), capture(1777)], [DAY], ROOT, None, publisher, RUN_URL)
    assert outcome.verdict is Verdict.OK
    assert publisher.received == []
    assert outcome.report.startswith("## Vigilante de instantáneas: ✅")


def test_a_missing_indicator_opens_the_day_issue() -> None:
    publisher = RecordingPublisher()
    outcome = run([capture(541)], [DAY], ROOT, None, publisher, RUN_URL)
    assert outcome.verdict is Verdict.FAILURE
    assert [issue.title for issue in publisher.received] == [
        "Vigilante: instantáneas del 2026-10-16"
    ]
    assert outcome.created == ["https://github.com/x/issues/0"]


def test_dry_run_lists_the_issues_without_opening_them() -> None:
    outcome = run([capture(541)], [DAY], ROOT, None, None, RUN_URL)
    assert outcome.created == []
    assert "En seco" in outcome.report
    assert "Vigilante: instantáneas del 2026-10-16" in outcome.report


def test_backup_is_written_and_a_changed_file_is_a_failure(tmp_path: Path) -> None:
    path, data = capture(541)
    first = run([(path, data), capture(1777)], [DAY], ROOT, tmp_path, None, RUN_URL)
    assert first.verdict is Verdict.OK
    assert "2 ficheros nuevos" in first.report

    publisher = RecordingPublisher()
    second = run([(path, data + b" "), capture(1777)], [DAY], ROOT, tmp_path, publisher, RUN_URL)
    assert second.verdict is Verdict.FAILURE
    assert [issue.title for issue in publisher.received] == [
        f"Vigilante: la copia privada no coincide con el Volume: {path}"
    ]


def test_the_job_diagnosis_goes_into_the_report() -> None:
    diagnosis = {DAY: "ejecución 7 (2026-10-15 09:00 UTC): SUCCESS"}
    outcome = run([capture(541)], [DAY], ROOT, None, None, RUN_URL, diagnosis)
    assert "- 2026-10-16: ejecución 7 (2026-10-15 09:00 UTC): SUCCESS" in outcome.report


# --- main ---


@pytest.fixture
def no_github_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Quita las variables que GitHub Actions define, para que la CI no cambie los tests."""
    for name in ("GITHUB_REPOSITORY", "GITHUB_TOKEN", "GITHUB_STEP_SUMMARY", "GITHUB_RUN_ID"):
        monkeypatch.delenv(name, raising=False)


def failing_workspace() -> Workspace:
    raise PermissionError("mensaje con datos de la cuenta")


def test_access_failure_in_dry_run_exits_with_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], no_github_env: None
) -> None:
    monkeypatch.setattr(watchdog_main, "_workspace", failing_workspace)
    assert main(["--dry-run", "--target-date", "2026-10-16"]) == 1
    error = capsys.readouterr().err
    assert "PermissionError" in error
    assert "datos de la cuenta" not in error


@pytest.fixture
def mocked() -> Iterator[responses.RequestsMock]:
    with responses.RequestsMock(assert_all_requests_are_fired=True) as rsps:
        yield rsps


def test_access_failure_opens_the_access_issue(
    monkeypatch: pytest.MonkeyPatch, mocked: responses.RequestsMock, no_github_env: None
) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "AaronPrado/ventormenta")
    monkeypatch.setenv("GITHUB_TOKEN", "token-de-prueba")
    monkeypatch.setattr(watchdog_main, "_workspace", failing_workspace)
    mocked.get(ISSUES_URL, json=[])
    mocked.post(
        ISSUES_URL,
        match=[matchers.json_params_matcher({"labels": [LABEL, "fallo"]}, strict_match=False)],
        json={"html_url": "https://github.com/x/issues/1"},
        status=201,
    )
    assert main(["--target-date", "2026-10-16"]) == 1


def test_without_github_variables_only_dry_run_is_allowed(no_github_env: None) -> None:
    with pytest.raises(SystemExit, match="--dry-run"):
        main(["--target-date", "2026-10-16"])


def test_report_goes_to_the_step_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, no_github_env: None
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr(watchdog_main, "_workspace", lambda: NoJobsWorkspace())

    def fake_download(reader: object, root: str, days: Sequence[date]) -> list[tuple[str, bytes]]:
        assert days == [DAY]
        return [capture(541), capture(1777)]

    monkeypatch.setattr(watchdog_main, "download_window", fake_download)
    assert main(["--dry-run", "--target-date", "2026-10-16"]) == 0
    text = summary.read_text(encoding="utf-8")
    assert "| 2026-10-16 | 541 |" in text
    assert "2026-10-16: el job esios_snapshots no existe o el vigilante no puede verlo" in text


class NoJobs:
    """API de Jobs sin ningún job visible, como antes de conceder ``CAN_VIEW``."""

    def list(self, *, name: str | None = None) -> Iterator[object]:
        return iter([])


class NoJobsWorkspace:
    files = object()
    jobs = NoJobs()


class BrokenJobs:
    def list(self, *, name: str | None = None) -> Iterator[object]:
        raise PermissionError("mensaje con datos de la cuenta")


class BrokenJobsWorkspace:
    files = object()
    jobs = BrokenJobs()


def test_a_jobs_api_failure_does_not_hide_the_verdict(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], no_github_env: None
) -> None:
    monkeypatch.setattr(watchdog_main, "_workspace", lambda: BrokenJobsWorkspace())
    monkeypatch.setattr(
        watchdog_main, "download_window", lambda reader, root, days: [capture(541), capture(1777)]
    )
    assert main(["--dry-run", "--target-date", "2026-10-16"]) == 0
    output = capsys.readouterr().out
    assert "diagnóstico no disponible (PermissionError)" in output
    assert "datos de la cuenta" not in output
