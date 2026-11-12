"""Arrival date: pace, band and the honest statuses."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.engine.adjustment.projection import (
    MAX_WEEKS,
    ArrivalStatus,
    project_arrival,
    slope_standard_error,
)
from app.engine.adjustment.types import WeightPoint

TODAY = date(2026, 11, 12)


def _daily(
    start_kg: float, weekly_kg: float, days: int = 28, noise: float = 0.0
) -> list[WeightPoint]:
    """One weigh-in a day ending today, on a straight line plus an alternating wobble."""
    points = []
    for index in range(days):
        day = TODAY - timedelta(days=days - 1 - index)
        wobble = noise if index % 2 else -noise
        points.append(
            WeightPoint(day=day, weight_kg=round(start_kg + weekly_kg * index / 7 + wobble, 2))
        )
    return points


def test_a_steady_loss_gives_a_date_and_a_band_around_it() -> None:
    weights = _daily(70.0, -0.5, noise=0.3)
    arrival = project_arrival(weights, TODAY, target_kg=64.0, planned_weekly_kg=-0.4)
    assert arrival.status is ArrivalStatus.ON_TRACK
    assert arrival.weekly_change_kg == pytest.approx(-0.5, abs=0.05)
    assert arrival.arrival is not None
    assert arrival.earliest is not None
    assert arrival.latest is not None
    assert arrival.earliest < arrival.arrival < arrival.latest
    # Unas 8 semanas desde ~68,1 kg hasta 64 kg a medio kilo por semana.
    assert 45 <= (arrival.arrival - TODAY).days <= 70


def test_noise_widens_the_band() -> None:
    calm = project_arrival(_daily(70.0, -0.5, noise=0.1), TODAY, 64.0, -0.4)
    noisy = project_arrival(_daily(70.0, -0.5, noise=0.8), TODAY, 64.0, -0.4)
    assert calm.earliest
    assert calm.latest
    assert noisy.earliest
    calm_width = (calm.latest - calm.earliest).days
    noisy_width = ((noisy.latest or TODAY + timedelta(weeks=MAX_WEEKS)) - noisy.earliest).days
    assert noisy_width > calm_width


def test_gaining_towards_a_higher_target_works_too() -> None:
    arrival = project_arrival(_daily(60.0, 0.25, noise=0.2), TODAY, 63.0, 0.25)
    assert arrival.status is ArrivalStatus.ON_TRACK
    assert arrival.arrival is not None
    assert arrival.arrival > TODAY


def test_without_a_trend_the_date_comes_from_the_plan() -> None:
    weights = [WeightPoint(day=TODAY - timedelta(days=1), weight_kg=70.0)]
    arrival = project_arrival(weights, TODAY, 66.0, planned_weekly_kg=-0.5)
    assert arrival.status is ArrivalStatus.FROM_PLAN
    assert arrival.arrival == TODAY + timedelta(weeks=8)
    assert arrival.earliest is None


def test_no_weigh_ins_use_the_profile_weight() -> None:
    arrival = project_arrival([], TODAY, 66.0, -0.5, fallback_current_kg=70.0)
    assert arrival.status is ArrivalStatus.FROM_PLAN
    assert arrival.current_kg == 70.0


def test_close_enough_counts_as_reached() -> None:
    arrival = project_arrival(_daily(64.2, 0.0), TODAY, 64.0, -0.4)
    assert arrival.status is ArrivalStatus.REACHED


def test_a_flat_trend_does_not_invent_a_date() -> None:
    arrival = project_arrival(_daily(70.0, 0.0, noise=0.2), TODAY, 64.0, -0.4)
    assert arrival.status is ArrivalStatus.FLAT
    assert arrival.arrival is None


def test_going_the_wrong_way_is_said_plainly() -> None:
    arrival = project_arrival(_daily(70.0, 0.4), TODAY, 64.0, -0.4)
    assert arrival.status is ArrivalStatus.AWAY
    assert arrival.arrival is None


def test_more_than_two_years_is_too_far() -> None:
    arrival = project_arrival(_daily(90.0, -0.1), TODAY, 70.0, -0.1)
    assert arrival.status is ArrivalStatus.TOO_FAR


def test_no_target_no_projection() -> None:
    arrival = project_arrival(_daily(70.0, -0.5), TODAY, None, -0.4)
    assert arrival.status is ArrivalStatus.NO_TARGET


def test_a_maintenance_plan_without_trend_is_flat() -> None:
    arrival = project_arrival([], TODAY, 66.0, planned_weekly_kg=0.0, fallback_current_kg=70.0)
    assert arrival.status is ArrivalStatus.FLAT


def test_slope_error_is_zero_on_a_perfect_line_and_none_with_two_points() -> None:
    line = [(TODAY + timedelta(days=i), 70 - 0.1 * i) for i in range(10)]
    assert slope_standard_error(line) == pytest.approx(0.0, abs=1e-9)
    assert slope_standard_error(line[:2]) is None
    assert slope_standard_error([(TODAY, 70.0)] * 3) is None
