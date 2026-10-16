"""Tests del vigilante: ventana de días D, veredicto por día e indicador, e informe."""

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from ventormenta.esios import NATIVE_STEPS, RawResponse, day_params
from ventormenta.peninsular import day_bounds, decision_cutoff
from ventormenta.snapshots import build_envelope
from ventormenta.watchdog import (
    OPERATIONS_START,
    WINDOW_DAYS,
    Capture,
    Corrupt,
    DayCheck,
    Verdict,
    check_day,
    check_window,
    decided_days,
    overall,
    read_captures,
    render_report,
)

DAY = date(2026, 10, 16)
LONG_DAY = date(2026, 10, 25)
# Hora del job (11:00 CEST del 15), una hora antes del corte del 16.
JOB_TIME = datetime(2026, 10, 15, 9, 0, 30, tzinfo=UTC)
# Valor con el que se comprueba que el informe no lleva datos de Red Eléctrica.
REE_VALUE = 98765.4321


def day_values(day: date, indicator_id: int, count: int | None = None) -> list[dict[str, Any]]:
    """Valores con la forma de e·sios, uno por intervalo desde el inicio del día."""
    # Un indicador desconocido usa cuartos de hora: solo importa que el sobre sea válido.
    step = NATIVE_STEPS.get(indicator_id, NATIVE_STEPS[541])
    start, end = (bound.astimezone(UTC) for bound in day_bounds(day))
    total = count if count is not None else (end - start) // step
    return [
        {"datetime_utc": (start + i * step).isoformat().replace("+00:00", "Z"), "value": REE_VALUE}
        for i in range(total)
    ]


def envelope(
    indicator_id: int = 541,
    day: date = DAY,
    received_at: datetime = JOB_TIME,
    count: int | None = None,
) -> bytes:
    """Sobre como los que escribe el job; ``count`` cambia cuántos valores trae."""
    body = {"indicator": {"id": indicator_id, "values": day_values(day, indicator_id, count)}}
    raw = RawResponse(
        indicator_id=indicator_id,
        url=f"https://api.esios.ree.es/indicators/{indicator_id}",
        params=day_params(day),
        status_code=200,
        body=json.dumps(body).encode(),
        server_date=None,
        requested_at=received_at - timedelta(seconds=1),
        received_at=received_at,
    )
    return build_envelope(raw, day)


def captures_from(*files: bytes) -> list[Capture]:
    captures, corrupt = read_captures((f"/v/{i}.json", data) for i, data in enumerate(files))
    assert corrupt == []
    return captures


# --- Ventana ---


# Inicio de operación anterior a todas las fechas de estos tests, para probar la ventana sola.
LONG_AGO = date(2026, 1, 1)


def test_decided_days_ends_at_the_last_decided_day() -> None:
    days = decided_days(datetime(2026, 10, 15, 10, 17, tzinfo=UTC), start=LONG_AGO)
    assert len(days) == WINDOW_DAYS
    assert days == [date(2026, 10, 10) + timedelta(days=i) for i in range(WINDOW_DAYS)]


def test_decided_days_before_the_cutoff_ends_today() -> None:
    now = datetime(2026, 10, 15, 9, 59, tzinfo=UTC)
    assert decided_days(now, window=2, start=LONG_AGO) == [
        date(2026, 10, 14),
        date(2026, 10, 15),
    ]


def test_decided_days_never_go_before_the_start_of_operations() -> None:
    now = datetime(2026, 10, 16, 10, 17, tzinfo=UTC)
    assert decided_days(now, start=date(2026, 10, 16)) == [date(2026, 10, 16), date(2026, 10, 17)]


def test_by_default_the_window_starts_with_the_first_scheduled_capture() -> None:
    assert date(2026, 10, 16) == OPERATIONS_START
    assert decided_days(datetime(2026, 10, 15, 10, 17, tzinfo=UTC)) == [date(2026, 10, 16)]


# --- Lectura ---


def test_read_captures_evaluates_each_envelope() -> None:
    (capture,) = captures_from(envelope())
    assert capture.indicator_id == 541
    assert capture.target_date == DAY
    assert capture.received_at == JOB_TIME
    assert capture.on_time
    assert capture.completeness.found == 96


def test_read_captures_sets_aside_invalid_files() -> None:
    captures, corrupt = read_captures(
        [("/v/roto.json", b"<html>mantenimiento</html>"), ("/v/999.json", envelope(999))]
    )
    assert captures == []
    assert [item.path for item in corrupt] == ["/v/roto.json", "/v/999.json"]
    assert "999" in corrupt[1].reason


# --- Veredicto ---


def test_complete_capture_before_cutoff_is_ok() -> None:
    check = check_day(DAY, 541, captures_from(envelope()))
    assert check.verdict is Verdict.OK
    assert check.capture is not None
    assert check.capture.received_at == JOB_TIME


def test_the_latest_complete_capture_before_cutoff_counts() -> None:
    retry = JOB_TIME + timedelta(minutes=10)
    captures = captures_from(envelope(count=0), envelope(received_at=retry))
    check = check_day(DAY, 541, captures)
    assert check.verdict is Verdict.OK
    assert check.capture is not None
    assert check.capture.received_at == retry


def test_complete_wins_over_a_later_unexpected_capture() -> None:
    later = JOB_TIME + timedelta(minutes=10)
    captures = captures_from(envelope(), envelope(received_at=later, count=95))
    check = check_day(DAY, 541, captures)
    assert check.verdict is Verdict.OK
    assert check.capture is not None
    assert check.capture.received_at == JOB_TIME


def test_only_unexpected_captures_is_a_warning() -> None:
    check = check_day(DAY, 541, captures_from(envelope(count=95)))
    assert check.verdict is Verdict.WARNING


def test_only_unpublished_captures_is_a_failure() -> None:
    check = check_day(DAY, 541, captures_from(envelope(count=0)))
    assert check.verdict is Verdict.FAILURE
    assert check.reason == "ninguna captura completa antes del corte"


def test_capture_received_exactly_at_cutoff_is_late() -> None:
    check = check_day(DAY, 541, captures_from(envelope(received_at=decision_cutoff(DAY))))
    assert check.verdict is Verdict.FAILURE
    assert check.reason == "solo capturas posteriores al corte"


def test_no_captures_is_a_failure() -> None:
    check = check_day(DAY, 541, [])
    assert check.verdict is Verdict.FAILURE
    assert check.reason == "sin capturas"
    assert check.capture is None


def test_captures_of_other_days_or_indicators_do_not_count() -> None:
    captures = captures_from(envelope(1777), envelope(day=DAY + timedelta(days=1)))
    assert check_day(DAY, 541, captures).verdict is Verdict.FAILURE


def test_25_hour_day_with_100_quarters_is_ok() -> None:
    received_at = datetime(2026, 10, 24, 9, tzinfo=UTC)
    captures = captures_from(envelope(day=LONG_DAY, received_at=received_at))
    assert check_day(LONG_DAY, 541, captures).verdict is Verdict.OK


def test_check_window_covers_every_day_and_known_indicator() -> None:
    days = [DAY, DAY + timedelta(days=1)]
    checks = check_window(days, captures_from(envelope(541), envelope(1777)))
    assert [(check.day, check.indicator_id) for check in checks] == [
        (DAY, 541),
        (DAY, 1777),
        (DAY + timedelta(days=1), 541),
        (DAY + timedelta(days=1), 1777),
    ]
    assert [check.verdict for check in checks] == [
        Verdict.OK,
        Verdict.OK,
        Verdict.FAILURE,
        Verdict.FAILURE,
    ]


# --- Veredicto global ---


def make_check(verdict: Verdict) -> DayCheck:
    return DayCheck(DAY, 541, verdict, "motivo", None)


@pytest.mark.parametrize(
    ("verdicts", "expected"),
    [
        ([], Verdict.OK),
        ([Verdict.OK, Verdict.OK], Verdict.OK),
        ([Verdict.OK, Verdict.WARNING], Verdict.WARNING),
        ([Verdict.WARNING, Verdict.FAILURE, Verdict.OK], Verdict.FAILURE),
    ],
)
def test_overall_is_the_worst_verdict(verdicts: list[Verdict], expected: Verdict) -> None:
    assert overall([make_check(verdict) for verdict in verdicts], []) is expected


def test_any_corrupt_file_is_a_failure() -> None:
    corrupt = [Corrupt("/v/roto.json", "no es un sobre JSON")]
    assert overall([make_check(Verdict.OK)], corrupt) is Verdict.FAILURE


# --- Informe ---


def test_report_has_metadata_and_no_ree_values() -> None:
    data = envelope()
    captures, _ = read_captures([("/v/541/capture_date=2026-10-15/20261015T090030Z.json", data)])
    checks = check_window([DAY], captures)
    report = render_report(checks, [Corrupt("/v/roto.json", "no es un sobre JSON")])

    assert "2026-10-16" in report
    assert "20261015T090030Z.json" in report
    assert captures[0].body_sha256[:12] in report
    assert "sin capturas" in report  # el 1777 no tiene captura
    assert "/v/roto.json" in report
    assert str(REE_VALUE) not in report
    assert "98765" not in report
