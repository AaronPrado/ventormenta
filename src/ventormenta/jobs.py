"""Diagnóstico del job de instantáneas con la API de Jobs: si se ejecutó antes del corte y cómo.

Es contexto para los avisos, no la fuente de verdad: el veredicto sale de los ficheros. No
lleva ``run_page_url`` ni ``state_message``: el primero incluye la URL del workspace y el
segundo es texto libre de error, y los dos acabarían en issues públicos, donde no llega el
enmascarado de secretos de GitHub. El identificador basta para encontrar la ejecución.
"""

from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from typing import Protocol

from ventormenta.peninsular import decision_cutoff, local_midnight

JOB_NAME = "esios_snapshots"


class RunState(Protocol):
    """Lo que se usa del estado de una ejecución."""

    @property
    def life_cycle_state(self) -> Enum | None: ...

    @property
    def result_state(self) -> Enum | None: ...


class Run(Protocol):
    """Lo que se usa de una ejecución."""

    @property
    def run_id(self) -> int | None: ...

    @property
    def start_time(self) -> int | None: ...

    @property
    def state(self) -> RunState | None: ...


class Job(Protocol):
    """Lo que se usa de un job."""

    @property
    def job_id(self) -> int | None: ...


class JobsReader(Protocol):
    """Lo que el diagnóstico necesita de la API de Jobs (``WorkspaceClient().jobs``)."""

    def list(self, *, name: str | None = None) -> Iterator[Job]: ...

    def list_runs(
        self,
        *,
        job_id: int | None = None,
        start_time_from: int | None = None,
        start_time_to: int | None = None,
    ) -> Iterator[Run]: ...


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _describe(run: Run) -> str:
    started = "hora desconocida"
    if run.start_time is not None:
        started = f"{datetime.fromtimestamp(run.start_time / 1000, UTC):%Y-%m-%d %H:%M} UTC"
    status = None
    if run.state is not None:
        status = run.state.result_state or run.state.life_cycle_state
    label = status.value if status is not None else "sin estado"
    return f"ejecución {run.run_id} ({started}): {label}"


def diagnose(jobs: JobsReader, days: Sequence[date], job_name: str = JOB_NAME) -> dict[date, str]:
    """Para cada día D, las ejecuciones del job que empezaron entre el inicio de D-1 y el corte.

    Son las que podían dejar una captura válida para D. Si no hay ninguna, el job no llegó a
    ejecutarse a tiempo: estaba pausado o borrado, o falló el planificador.
    """
    job_ids = [job.job_id for job in jobs.list(name=job_name) if job.job_id is not None]
    if not job_ids:
        return dict.fromkeys(days, f"el job {job_name} no existe o el vigilante no puede verlo")
    diagnosis: dict[date, str] = {}
    for day in days:
        start, end = local_midnight(day - timedelta(days=1)), decision_cutoff(day)
        runs = sorted(
            (
                run
                for job_id in job_ids
                for run in jobs.list_runs(
                    job_id=job_id, start_time_from=_ms(start), start_time_to=_ms(end)
                )
            ),
            key=lambda run: run.start_time or 0,
        )
        described = "; ".join(_describe(run) for run in runs)
        diagnosis[day] = described or "ninguna ejecución del job antes del corte"
    return diagnosis
