"""Vigilante de las instantáneas de e·sios: qué días D tienen una captura válida.

Lógica pura, sin red: recibe los ficheros ya descargados del Volume y decide, para cada día
D e indicador, si hay una captura completa anterior al corte de decisión. La lectura de
Databricks, los issues y la copia privada van aparte. Lo que sale de aquí acaba en logs e
issues de un repositorio público, así que nunca lleva valores de Red Eléctrica: solo
estados, recuentos, instantes, rutas y huellas.
"""

import hashlib
import posixpath
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from ventormenta.esios import NATIVE_STEPS
from ventormenta.peninsular import decision_cutoff, last_decided_day
from ventormenta.snapshots import (
    Completeness,
    EnvelopeError,
    Status,
    check_completeness,
    read_envelope,
)

# Días D que revisa cada ejecución: si GitHub descarta una ejecución programada, la
# siguiente cubre ese día.
WINDOW_DAYS = 7

# Primer día D que capturó el job programado (primera ejecución: 11:00 peninsulares del
# 2026-10-15). Antes no había operación que vigilar: esos días solo darían avisos falsos.
OPERATIONS_START = date(2026, 10, 16)


def decided_days(
    now: datetime, window: int = WINDOW_DAYS, start: date = OPERATIONS_START
) -> list[date]:
    """Los ``window`` últimos días D cuyo corte ya ha pasado en ``now``, desde ``start``."""
    last = last_decided_day(now)
    days = [last - timedelta(days=offset) for offset in reversed(range(window))]
    return [day for day in days if day >= start]


class Verdict(StrEnum):
    """Resultado de un día D para un indicador, de mejor a peor."""

    OK = "ok"
    WARNING = "warning"
    FAILURE = "failure"


@dataclass(frozen=True)
class Capture:
    """Una instantánea leída del Volume y evaluada."""

    path: str
    indicator_id: int
    target_date: date
    received_at: datetime
    body_sha256: str
    completeness: Completeness

    @property
    def on_time(self) -> bool:
        """Si llegó estrictamente antes del corte de su día D: solo entonces sirve."""
        return self.received_at < decision_cutoff(self.target_date)


@dataclass(frozen=True)
class Corrupt:
    """Un fichero del Volume que no es un sobre válido, con el motivo."""

    path: str
    reason: str


def read_captures(files: Iterable[tuple[str, bytes]]) -> tuple[list[Capture], list[Corrupt]]:
    """Lee y evalúa cada fichero ``(ruta, contenido)``; los que no son válidos van aparte."""
    captures: list[Capture] = []
    corrupt: list[Corrupt] = []
    for path, data in files:
        try:
            raw, target_date = read_envelope(data)
        except EnvelopeError as err:
            corrupt.append(Corrupt(path, str(err)))
            continue
        step = NATIVE_STEPS.get(raw.indicator_id)
        if step is None:
            corrupt.append(Corrupt(path, f"indicador {raw.indicator_id} desconocido"))
            continue
        captures.append(
            Capture(
                path=path,
                indicator_id=raw.indicator_id,
                target_date=target_date,
                received_at=raw.received_at,
                body_sha256=hashlib.sha256(raw.body).hexdigest(),
                completeness=check_completeness(raw, target_date, step),
            )
        )
    return captures, corrupt


@dataclass(frozen=True)
class DayCheck:
    """Veredicto de un día D para un indicador, con la captura en que se basa."""

    day: date
    indicator_id: int
    verdict: Verdict
    reason: str
    capture: Capture | None


def check_day(day: date, indicator_id: int, captures: Iterable[Capture]) -> DayCheck:
    """Decide si el día D tiene una captura válida del indicador: completa y anterior al corte.

    Entre varias capturas cuenta la última, la más cercana a la hora de decisión. Una
    captura posterior al corte no sirve aunque esté completa: usarla sería una fuga.
    """
    own = sorted(
        (c for c in captures if c.indicator_id == indicator_id and c.target_date == day),
        key=lambda capture: capture.received_at,
    )
    on_time = [c for c in own if c.on_time]
    complete = [c for c in on_time if c.completeness.status is Status.COMPLETE]
    unexpected = [c for c in on_time if c.completeness.status is Status.UNEXPECTED]

    def result(verdict: Verdict, reason: str, capture: Capture | None) -> DayCheck:
        return DayCheck(day, indicator_id, verdict, reason, capture)

    if complete:
        return result(Verdict.OK, "captura completa antes del corte", complete[-1])
    if unexpected:
        return result(Verdict.WARNING, "solo capturas con recuento inesperado", unexpected[-1])
    if on_time:
        return result(Verdict.FAILURE, "ninguna captura completa antes del corte", on_time[-1])
    if own:
        return result(Verdict.FAILURE, "solo capturas posteriores al corte", own[-1])
    return result(Verdict.FAILURE, "sin capturas", None)


def check_window(days: Iterable[date], captures: Sequence[Capture]) -> list[DayCheck]:
    """Veredicto de cada día D para cada indicador conocido, por día y por indicador."""
    return [check_day(day, ind, captures) for day in days for ind in sorted(NATIVE_STEPS)]


def overall(checks: Iterable[DayCheck], corrupt: Sequence[Corrupt]) -> Verdict:
    """El peor veredicto de la ventana; un fichero que no es un sobre válido es un fallo."""
    verdicts = [check.verdict for check in checks]
    if corrupt:
        verdicts.append(Verdict.FAILURE)
    severity = list(Verdict)
    return max(verdicts, key=severity.index, default=Verdict.OK)


VERDICT_LABELS = {Verdict.OK: "✅ ok", Verdict.WARNING: "⚠️ aviso", Verdict.FAILURE: "❌ fallo"}


def render_report(checks: Iterable[DayCheck], corrupt: Sequence[Corrupt]) -> str:
    """Tabla en Markdown para el resumen de la ejecución y los issues.

    Solo metadatos: el repositorio es público y los datos de Red Eléctrica no se
    redistribuyen. La huella del cuerpo permite cotejar la copia privada sin mostrar nada.
    """
    lines = [
        "| Día D | Indicador | Veredicto | Motivo | Recuento | Recibida UTC | Fichero | Huella |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for check in checks:
        cells = [
            check.day.isoformat(),
            str(check.indicator_id),
            VERDICT_LABELS[check.verdict],
            check.reason,
        ]
        if check.capture is None:
            cells += ["—"] * 4
        else:
            capture = check.capture
            cells += [
                capture.completeness.detail,
                f"{capture.received_at:%Y-%m-%d %H:%M:%S}",
                f"`{posixpath.basename(capture.path)}`",
                f"`{capture.body_sha256[:12]}`",
            ]
        lines.append(f"| {' | '.join(cells)} |")
    if corrupt:
        lines += ["", "Ficheros que no son sobres válidos:", ""]
        lines += [f"- `{item.path}`: {item.reason}" for item in corrupt]
    return "\n".join(lines) + "\n"
