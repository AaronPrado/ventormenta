"""Tests del cierre contra el 10010, con casos calculados a mano."""

from datetime import UTC, datetime, timedelta

import pytest

from ventormenta.closure import (
    MAX_CLOSURE_ERROR,
    WIND_WEIGHT,
    closure_error,
    closure_holds,
    residual,
    wind_by_weight,
)

T0 = datetime(2025, 1, 1, tzinfo=UTC)
T1 = T0 + timedelta(minutes=15)
T2 = T0 + timedelta(minutes=30)

# Residuo de 4 y 3 MWh: lo cierran A y B; S tiene otra forma y solo aporta en el primer cuarto.
REFERENCE = {T0: 10.0, T1: 10.0}
LISTED = {T0: 6.0, T1: 7.0}
PROFILES = {"A": {T0: 3.0, T1: 2.0}, "B": {T0: 1.0, T1: 1.0}, "S": {T0: 5.0}}


def test_rule_constants_match_the_documented_rule() -> None:
    assert (WIND_WEIGHT, MAX_CLOSURE_ERROR) == (0.5, 0.01)


def test_residual_is_reference_minus_listed() -> None:
    assert residual(REFERENCE, LISTED) == {T0: 4.0, T1: 3.0}


def test_residual_rejects_misaligned_series() -> None:
    with pytest.raises(ValueError, match="mismos cuartos"):
        residual({T0: 10.0, T1: 8.0}, {T0: 7.0, T2: 8.0})


def test_residual_rejects_naive_instants_against_utc_ones() -> None:
    # Instantes sin zona frente a los UTC de e·sios: no coinciden, y el error lo dice en vez
    # de restar cuartos distintos.
    with pytest.raises(ValueError, match="mismos cuartos"):
        residual({T0: 1.0}, {T0.replace(tzinfo=None): 1.0})


def test_residual_rejects_instants_without_time_zone() -> None:
    naive = T0.replace(tzinfo=None)
    with pytest.raises(ValueError, match="sin zona horaria"):
        residual({naive: 1.0}, {naive: 1.0})


@pytest.mark.parametrize(
    ("weight", "wind"), [(0.5, True), (0.49, False), (1.0, True), (0.0, False)]
)
def test_wind_threshold_is_inclusive(weight: float, wind: bool) -> None:
    assert ("U" in wind_by_weight({"U": weight})) is wind


def test_exact_closure_leaves_nothing() -> None:
    assert closure_error(REFERENCE, LISTED, PROFILES, {"A", "B"}) == pytest.approx(0.0)


def test_closure_error_is_absolute_residual_over_reference() -> None:
    # Solo con A falta 1 MWh en cada cuarto: 2 de 20.
    assert closure_error(REFERENCE, LISTED, PROFILES, {"A"}) == pytest.approx(2 / 20)


def test_excess_in_one_quarter_does_not_cancel_a_shortfall_in_another() -> None:
    # Con A y S sobran 4 MWh en el primer cuarto y falta 1 en el segundo: 5 de 20, no 3.
    assert closure_error(REFERENCE, LISTED, PROFILES, {"A", "S"}) == pytest.approx(5 / 20)


def test_missing_quarters_in_a_profile_are_zero() -> None:
    error = closure_error({T0: 5.0, T1: 5.0}, {T0: 5.0, T1: 3.0}, {"A": {T1: 2.0}}, {"A"})
    assert error == pytest.approx(0.0)


def test_repeated_wind_units_count_once() -> None:
    assert closure_error(REFERENCE, LISTED, PROFILES, ["A", "A", "B"]) == pytest.approx(0.0)


def test_closure_error_rejects_wind_unit_without_profile() -> None:
    with pytest.raises(ValueError, match="sin perfil"):
        closure_error(REFERENCE, LISTED, PROFILES, {"A", "X"})


def test_closure_error_rejects_profile_outside_the_month() -> None:
    with pytest.raises(ValueError, match="fuera del mes"):
        closure_error(REFERENCE, LISTED, {"A": {T2: 1.0}}, {"A"})


@pytest.mark.parametrize("energy", [0.0, -1.0])
def test_closure_error_rejects_reference_without_positive_energy(energy: float) -> None:
    with pytest.raises(ValueError, match="energía positiva"):
        closure_error({T0: energy}, {T0: 0.0}, {}, [])


@pytest.mark.parametrize(
    ("errors", "holds"), [([0.0, 0.005, 0.01], True), ([0.0, 0.0101], False), ([0.02], False)]
)
def test_closure_holds_only_if_every_month_closes(errors: list[float], holds: bool) -> None:
    assert closure_holds(errors) is holds


def test_closure_holds_needs_at_least_one_month() -> None:
    with pytest.raises(ValueError, match="sin meses"):
        closure_holds([])
