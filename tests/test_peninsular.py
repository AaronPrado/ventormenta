"""Tests de la hora peninsular, con los días de cambio de hora de 2026 y 2027."""

from datetime import UTC, date, datetime, timedelta

import pytest

from ventormenta.peninsular import (
    day_bounds,
    day_length,
    decision_cutoff,
    intervals_in_day,
    last_decided_day,
    local_midnight,
    target_day,
)

NORMAL_DAY = date(2026, 10, 14)
# Último domingo de octubre de 2026: a las 03:00 CEST vuelven a ser las 02:00 CET.
LONG_DAY = date(2026, 10, 25)
# Último domingo de marzo de 2027: a las 02:00 CET pasan a ser las 03:00 CEST.
SHORT_DAY = date(2027, 3, 28)

QUARTER_HOUR = timedelta(minutes=15)
HOUR = timedelta(hours=1)


@pytest.mark.parametrize(
    ("day", "offset"),
    [(NORMAL_DAY, timedelta(hours=2)), (date(2026, 12, 1), timedelta(hours=1))],
)
def test_local_midnight_uses_offset_of_that_day(day: date, offset: timedelta) -> None:
    assert local_midnight(day).utcoffset() == offset


def test_day_bounds_are_consecutive_midnights() -> None:
    start, end = day_bounds(LONG_DAY)
    assert start == local_midnight(LONG_DAY)
    assert end == local_midnight(date(2026, 10, 26))


@pytest.mark.parametrize(
    ("day", "hours"),
    [(NORMAL_DAY, 24), (LONG_DAY, 25), (SHORT_DAY, 23)],
)
def test_day_length_counts_real_hours(day: date, hours: int) -> None:
    assert day_length(day) == timedelta(hours=hours)


@pytest.mark.parametrize(
    ("day", "quarters", "hours"),
    [(NORMAL_DAY, 96, 24), (LONG_DAY, 100, 25), (SHORT_DAY, 92, 23)],
)
def test_intervals_in_day(day: date, quarters: int, hours: int) -> None:
    assert intervals_in_day(day, QUARTER_HOUR) == quarters
    assert intervals_in_day(day, HOUR) == hours


@pytest.mark.parametrize("step", [timedelta(0), -HOUR, timedelta(minutes=7)])
def test_intervals_in_day_rejects_invalid_step(step: timedelta) -> None:
    with pytest.raises(ValueError, match="no divide"):
        intervals_in_day(NORMAL_DAY, step)


@pytest.mark.parametrize(
    ("captured_at", "expected"),
    [
        # 11:05 CEST del 14 de octubre: la captura de la mañana apunta al 15.
        (datetime(2026, 10, 14, 9, 5, tzinfo=UTC), date(2026, 10, 15)),
        # 00:30 CEST del 15 en la península, aunque en UTC aún sea el 14.
        (datetime(2026, 10, 14, 22, 30, tzinfo=UTC), date(2026, 10, 16)),
        # El 24 de octubre se captura el día de 25 horas.
        (datetime(2026, 10, 24, 9, 5, tzinfo=UTC), LONG_DAY),
    ],
)
def test_target_day_is_next_peninsular_day(captured_at: datetime, expected: date) -> None:
    assert target_day(captured_at) == expected


def test_target_day_rejects_naive_datetime() -> None:
    naive = datetime(2026, 10, 14, 11, 5)  # noqa: DTZ001  (ingenuo a propósito)
    with pytest.raises(ValueError, match="zona horaria"):
        target_day(naive)


# --- Corte de decisión ---


@pytest.mark.parametrize(
    ("day", "cutoff_utc"),
    [
        # Verano (CEST): las 12:00 peninsulares de D-1 son las 10:00 UTC.
        (date(2026, 10, 16), datetime(2026, 10, 15, 10, tzinfo=UTC)),
        # D es el día de 25 horas, pero su D-1 aún es CEST.
        (LONG_DAY, datetime(2026, 10, 24, 10, tzinfo=UTC)),
        # D-1 es el día de 25 horas: a las 12:00 ya es CET.
        (date(2026, 10, 26), datetime(2026, 10, 25, 11, tzinfo=UTC)),
        # Invierno (CET): las 11:00 UTC.
        (date(2026, 12, 2), datetime(2026, 12, 1, 11, tzinfo=UTC)),
        # D-1 es el día de 23 horas: a las 12:00 ya es CEST.
        (date(2027, 3, 29), datetime(2027, 3, 28, 10, tzinfo=UTC)),
    ],
)
def test_decision_cutoff_is_noon_of_previous_peninsular_day(
    day: date, cutoff_utc: datetime
) -> None:
    cutoff = decision_cutoff(day)
    assert cutoff == cutoff_utc
    assert cutoff.utcoffset() is not None


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # Un microsegundo antes del corte del 16: el último D decidido es aún el 15.
        (datetime(2026, 10, 15, 9, 59, 59, 999999, tzinfo=UTC), date(2026, 10, 15)),
        # Justo en el corte, ya está decidido: solo cuenta lo anterior a las 12:00.
        (datetime(2026, 10, 15, 10, tzinfo=UTC), date(2026, 10, 16)),
        # Hora del vigilante, 12:17 CEST.
        (datetime(2026, 10, 15, 10, 17, tzinfo=UTC), date(2026, 10, 16)),
        # 00:30 CEST del 16: en UTC aún es el 15, y el corte del 17 no ha llegado.
        (datetime(2026, 10, 15, 22, 30, tzinfo=UTC), date(2026, 10, 16)),
        # 12:17 CET del día de 25 horas.
        (datetime(2026, 10, 25, 11, 17, tzinfo=UTC), date(2026, 10, 26)),
    ],
)
def test_last_decided_day(now: datetime, expected: date) -> None:
    assert last_decided_day(now) == expected


def test_last_decided_day_switches_exactly_at_each_cutoff_all_year() -> None:
    """Propiedad sobre un año entero, con sus dos cambios de hora."""
    tick = timedelta(microseconds=1)
    for offset in range(366):
        day = date(2026, 6, 1) + timedelta(days=offset)
        cutoff = decision_cutoff(day)
        assert last_decided_day(cutoff) == day
        assert last_decided_day(cutoff - tick) == day - timedelta(days=1)


def test_last_decided_day_rejects_naive_datetime() -> None:
    naive = datetime(2026, 10, 15, 12, 17)  # noqa: DTZ001  (ingenuo a propósito)
    with pytest.raises(ValueError, match="zona horaria"):
        last_decided_day(naive)
