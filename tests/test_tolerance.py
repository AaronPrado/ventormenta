"""Tests de la regla de la tolerancia mensual, con casos calculados a mano."""

from collections.abc import Callable, Sequence

import pytest

from ventormenta.tolerance import (
    CAP,
    MAPPING_MARGIN,
    margin_reduced,
    relative_difference,
    tolerance,
)


def test_rule_constants_match_the_documented_rule() -> None:
    assert (MAPPING_MARGIN, CAP) == (0.03, 0.05)


@pytest.mark.parametrize(
    ("program", "measured", "difference"),
    [(105.0, 100.0, 0.05), (95.0, 100.0, -0.05), (100.0, 100.0, 0.0), (0.0, 50.0, -1.0)],
)
def test_relative_difference_keeps_sign(program: float, measured: float, difference: float) -> None:
    assert relative_difference(program, measured) == pytest.approx(difference)


@pytest.mark.parametrize("measured", [0.0, -1.0])
def test_relative_difference_rejects_non_positive_measure(measured: float) -> None:
    with pytest.raises(ValueError, match="no positiva"):
        relative_difference(100.0, measured)


def test_tolerance_uses_worst_month_in_absolute_value() -> None:
    # El peor mes es el negativo: |-1,5 %| + 3 puntos.
    assert tolerance([0.01, -0.015, 0.005]) == pytest.approx(0.045)


def test_tolerance_is_capped() -> None:
    assert tolerance([0.01, -0.025]) == CAP


def test_tolerance_reaches_cap_exactly_at_two_points() -> None:
    assert tolerance([0.02]) == pytest.approx(CAP)


def test_tolerance_of_perfect_months_is_the_margin() -> None:
    assert tolerance([0.0, 0.0, 0.0]) == pytest.approx(MAPPING_MARGIN)


@pytest.mark.parametrize("function", [tolerance, margin_reduced])
def test_rule_needs_at_least_one_month(function: Callable[[Sequence[float]], object]) -> None:
    with pytest.raises(ValueError, match="sin diferencias"):
        function([])


@pytest.mark.parametrize(
    ("differences", "reduced"),
    [([0.019], False), ([0.02], False), ([-0.021], True), ([0.0, 0.03], True)],
)
def test_margin_reduced_only_above_two_points(differences: list[float], reduced: bool) -> None:
    assert margin_reduced(differences) is reduced
