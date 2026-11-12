"""Arrival date: when, at the current pace, the target weight is reached.

The pace is the trend the review already uses (least-squares slope of the
7-day average over the last four weeks). The date comes with a band: the slope
of the raw weigh-ins has a standard error, and the earliest and latest dates
are the ones the slope gives at plus and minus 1.28 standard errors (an 80 %
interval). The raw points are used for the error because the moving average
is autocorrelated and would make the band look narrower than the truth. Every
weigh-in narrows it.

Without enough weigh-ins for a trend the date comes from the plan's expected
weekly change, and says so. A pace that is flat, goes the wrong way or needs
more than two years gets a plain status instead of an absurd date.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from app.engine.adjustment.smoothing import estimate_trend
from app.engine.adjustment.types import WeightPoint
from app.engine.enums import Confidence

WINDOW_DAYS = 28
Z_80 = 1.2816
MAX_WEEKS = 104
FLAT_KG_PER_WEEK = 0.05
REACHED_MARGIN_KG = 0.3


class ArrivalStatus(StrEnum):
    """What the projection can honestly say."""

    ON_TRACK = "on_track"
    FROM_PLAN = "from_plan"
    REACHED = "reached"
    FLAT = "flat"
    AWAY = "away"
    TOO_FAR = "too_far"
    NO_TARGET = "no_target"


@dataclass(frozen=True)
class Arrival:
    """Projected arrival at the target weight."""

    status: ArrivalStatus
    target_kg: float | None
    current_kg: float | None
    weekly_change_kg: float | None
    planned_weekly_kg: float
    arrival: date | None = None
    earliest: date | None = None
    latest: date | None = None
    confidence: Confidence | None = None

    @property
    def remaining_kg(self) -> float | None:
        """Signed kilos still to go (negative when losing)."""
        if self.target_kg is None or self.current_kg is None:
            return None
        return round(self.target_kg - self.current_kg, 2)


def slope_standard_error(series: Sequence[tuple[date, float]]) -> float | None:
    """Standard error (kg/day) of the least-squares slope; ``None`` with fewer than 3 points."""
    n = len(series)
    if n < 3:
        return None
    origin = series[0][0]
    xs = [(day - origin).days for day, _ in series]
    ys = [value for _, value in series]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / sxx
    intercept = mean_y - slope * mean_x
    residuals = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys, strict=True))
    return math.sqrt(residuals / (n - 2) / sxx)


def _date_after(today: date, remaining_kg: float, weekly_kg: float) -> date | None:
    """Day the target is reached at ``weekly_kg``; ``None`` if never or beyond the cap."""
    if weekly_kg == 0 or (remaining_kg > 0) != (weekly_kg > 0):
        return None
    weeks = remaining_kg / weekly_kg
    if weeks > MAX_WEEKS:
        return None
    return today + timedelta(days=round(weeks * 7))


def project_arrival(
    weights: Sequence[WeightPoint],
    today: date,
    target_kg: float | None,
    planned_weekly_kg: float,
    fallback_current_kg: float | None = None,
) -> Arrival:
    """Project when ``target_kg`` is reached from the weigh-ins up to ``today``."""
    start = today - timedelta(days=WINDOW_DAYS - 1)
    recent = sorted((p for p in weights if start <= p.day <= today), key=lambda p: p.day)
    trend = estimate_trend(recent, start, today)
    current = trend.end_average_kg
    if current is None:
        current = recent[-1].weight_kg if recent else fallback_current_kg

    def result(status: ArrivalStatus, **extra: object) -> Arrival:
        return Arrival(
            status=status,
            target_kg=target_kg,
            current_kg=current,
            weekly_change_kg=trend.weekly_change_kg,
            planned_weekly_kg=planned_weekly_kg,
            **extra,  # type: ignore[arg-type]
        )

    if target_kg is None or current is None:
        return result(ArrivalStatus.NO_TARGET)
    remaining = target_kg - current
    if abs(remaining) <= REACHED_MARGIN_KG:
        return result(ArrivalStatus.REACHED)

    weekly = trend.weekly_change_kg
    if weekly is None:
        planned_date = _date_after(today, remaining, planned_weekly_kg)
        if planned_date is None:
            return result(ArrivalStatus.FLAT)
        return result(ArrivalStatus.FROM_PLAN, arrival=planned_date)

    if abs(weekly) < FLAT_KG_PER_WEEK:
        return result(ArrivalStatus.FLAT, confidence=trend.confidence)
    if (remaining > 0) != (weekly > 0):
        return result(ArrivalStatus.AWAY, confidence=trend.confidence)
    arrival = _date_after(today, remaining, weekly)
    if arrival is None:
        return result(ArrivalStatus.TOO_FAR, confidence=trend.confidence)

    earliest = latest = None
    error = slope_standard_error([(p.day, p.weight_kg) for p in recent])
    if error is not None:
        spread = Z_80 * error * 7
        faster = weekly + spread if weekly > 0 else weekly - spread
        slower = weekly - spread if weekly > 0 else weekly + spread
        earliest = _date_after(today, remaining, faster)
        latest = _date_after(today, remaining, slower)
    return result(
        ArrivalStatus.ON_TRACK,
        arrival=arrival,
        earliest=earliest,
        latest=latest,
        confidence=trend.confidence,
    )
