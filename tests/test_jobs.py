"""Tests del diagnóstico del job con la API de Jobs, con un doble en memoria."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum

from databricks.sdk import WorkspaceClient

from ventormenta.jobs import JOB_NAME, JobsReader, diagnose
from ventormenta.peninsular import decision_cutoff
from ventormenta.watchdog_main import Workspace

DAY = date(2026, 10, 16)
JOB_ID = 42


class Result(Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class LifeCycle(Enum):
    RUNNING = "RUNNING"
    TERMINATED = "TERMINATED"


@dataclass
class State:
    life_cycle_state: Enum | None
    result_state: Enum | None


@dataclass
class Run:
    run_id: int | None
    start_time: int | None
    state: State | None


@dataclass
class Job:
    job_id: int | None


def ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def started(hour: int, minute: int = 0) -> int:
    """Inicio de una ejecución el 15 de octubre, en milisegundos (como la API)."""
    return ms(datetime(2026, 10, 15, hour, minute, tzinfo=UTC))


class FakeJobs:
    """Doble de la API de Jobs: filtra las ejecuciones por inicio, como la real."""

    def __init__(self, job_ids: list[int], runs: list[Run]) -> None:
        self.job_ids = job_ids
        self.runs = runs
        self.windows: list[tuple[int | None, int | None]] = []

    def list(self, *, name: str | None = None) -> Iterator[Job]:
        assert name == JOB_NAME
        return iter([Job(job_id) for job_id in self.job_ids])

    def list_runs(
        self,
        *,
        job_id: int | None = None,
        start_time_from: int | None = None,
        start_time_to: int | None = None,
    ) -> Iterator[Run]:
        assert job_id in self.job_ids
        self.windows.append((start_time_from, start_time_to))
        low, high = start_time_from or 0, start_time_to or 2**63
        return iter([run for run in self.runs if low <= (run.start_time or 0) <= high])


def _sdk_workspace_conforms(client: WorkspaceClient) -> None:
    """No se ejecuta: mypy comprueba que el cliente real cumple los Protocol del vigilante."""
    jobs: JobsReader = client.jobs
    workspace: Workspace = client
    del jobs, workspace


def test_the_window_goes_from_the_start_of_d_minus_1_to_the_cutoff() -> None:
    api = FakeJobs([JOB_ID], [])
    diagnose(api, [DAY])
    # Medianoche peninsular del 15 (22:00 UTC del 14) y corte (10:00 UTC del 15).
    assert api.windows == [(ms(datetime(2026, 10, 14, 22, tzinfo=UTC)), ms(decision_cutoff(DAY)))]


def test_a_finished_run_shows_its_id_time_and_result() -> None:
    run = Run(7, started(9), State(LifeCycle.TERMINATED, Result.SUCCESS))
    assert diagnose(FakeJobs([JOB_ID], [run]), [DAY]) == {
        DAY: "ejecución 7 (2026-10-15 09:00 UTC): SUCCESS"
    }


def test_a_running_run_shows_its_life_cycle_state() -> None:
    run = Run(8, started(9), State(LifeCycle.RUNNING, None))
    assert diagnose(FakeJobs([JOB_ID], [run]), [DAY])[DAY].endswith("RUNNING")


def test_runs_are_listed_in_start_order() -> None:
    retry = Run(2, started(9, 30), State(LifeCycle.TERMINATED, Result.SUCCESS))
    first = Run(1, started(9), State(LifeCycle.TERMINATED, Result.FAILED))
    description = diagnose(FakeJobs([JOB_ID], [retry, first]), [DAY])[DAY]
    assert description.index("ejecución 1") < description.index("ejecución 2")


def test_no_runs_before_the_cutoff() -> None:
    late = Run(9, started(13), State(LifeCycle.TERMINATED, Result.SUCCESS))
    assert diagnose(FakeJobs([JOB_ID], [late]), [DAY]) == {
        DAY: "ninguna ejecución del job antes del corte"
    }


def test_a_missing_or_invisible_job_is_said_for_every_day() -> None:
    days = [DAY, date(2026, 10, 17)]
    diagnosis = diagnose(FakeJobs([], []), days)
    assert set(diagnosis) == set(days)
    assert all("no existe o el vigilante no puede verlo" in text for text in diagnosis.values())
