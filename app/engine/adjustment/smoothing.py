"""Weight smoothing and trend estimation.

Daily weights swing by 1-2 % with water and glycogen, so single days are never
compared (§3.8). Each day gets the average of the weigh-ins in the trailing
7-day window, and the trend is the least-squares slope of those smoothed
values over the review window, expressed in kg per week.

Weighing daily is not a requirement. With one weigh-in a week (or a month)
there is nothing to smooth, so the slope is fitted over the raw points across
a longer window: the same noise is there, but spread over enough weeks that
the signal beats it. That trend is marked as low confidence and ``smoothed``
False, and the rules act on it more slowly and more gently.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from app.engine.adjustment.types import (
    MIN_SPAN_DAYS,
    MIN_WEIGHT_DAYS,
    SPARSE_MIN_POINTS,
    SPARSE_MIN_SPAN_DAYS,
    TrendEstimate,
    WeightPoint,
)
from app.engine.enums import Confidence

WINDOW_DAYS = 7
MIN_POINTS_PER_WINDOW = 3
GOOD_COVERAGE = 0.7


def moving_average(
    weights: Sequence[WeightPoint], window_days: int = WINDOW_DAYS
) -> list[tuple[date, float]]:
    """Trailing average per logged day.

    A day only gets an average when its whole ``window_days`` window lies inside
    the logged history and holds at least ``MIN_POINTS_PER_WINDOW`` weigh-ins.
    """
    points = sorted(weights, key=lambda point: point.day)
    by_day: dict[date, float] = {}
    for point in points:
        by_day[point.day] = point.weight_kg
    if not by_day:
        return []
    first = min(by_day)
    smoothed: list[tuple[date, float]] = []
    for day in sorted(by_day):
        start = day - timedelta(days=window_days - 1)
        if start < first:
            # A partial window averages fewer days, so its centre of mass advances
            # at half speed and the fitted slope comes out flatter than reality.
            # That would under-report how fast someone is losing weight, which is
            # exactly the direction the safety cap must not err in.
            continue
        window = [by_day[other] for other in by_day if start <= other <= day]
        if len(window) >= MIN_POINTS_PER_WINDOW:
            smoothed.append((day, round(sum(window) / len(window), 2)))
    return smoothed


def slope_per_day(series: Sequence[tuple[date, float]]) -> float | None:
    """Ordinary least squares slope (kg/day) of ``series``; ``None`` with fewer than 2 points."""
    if len(series) < 2:
        return None
    origin = series[0][0]
    xs = [(day - origin).days for day, _ in series]
    ys = [value for _, value in series]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return None
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    return numerator / denominator


def estimate_trend(weights: Sequence[WeightPoint], start: date, end: date) -> TrendEstimate:
    """Weekly change between ``start`` and ``end`` from the smoothed series."""
    in_window = [point for point in weights if start <= point.day <= end]
    span = (end - start).days + 1
    smoothed = moving_average(in_window)
    weight_days = len({point.day for point in in_window})
    coverage = weight_days / span if span > 0 else 0.0

    smoothed_enough = weight_days >= MIN_WEIGHT_DAYS and span >= MIN_SPAN_DAYS
    slope = slope_per_day(smoothed) if smoothed_enough else None
    from_raw = False
    if slope is None and weight_days >= SPARSE_MIN_POINTS and span >= SPARSE_MIN_SPAN_DAYS:
        # Sin media móvil posible: la pendiente sale de los pesajes tal cual.
        raw = sorted((point.day, point.weight_kg) for point in in_window)
        slope = slope_per_day(raw)
        from_raw = slope is not None

    weekly = round(slope * 7, 2) if slope is not None else None
    if weekly is None or from_raw:
        confidence = Confidence.LOW
    elif coverage >= GOOD_COVERAGE and span >= 2 * MIN_SPAN_DAYS - 6:
        confidence = Confidence.HIGH
    else:
        confidence = Confidence.MEDIUM
    return TrendEstimate(
        start_day=start,
        end_day=end,
        span_days=span,
        weight_days=weight_days,
        start_average_kg=smoothed[0][1] if smoothed else None,
        end_average_kg=smoothed[-1][1] if smoothed else None,
        weekly_change_kg=weekly,
        confidence=confidence,
        smoothed=not from_raw,
    )
