"""Observed expenditure from energy balance.

    TDEE_observed = mean intake + (-weight change x 7700 kcal/kg) / days

The theoretical estimate is replaced progressively by the observed one as
data accumulates (full trust after ``FULL_TRUST_DAYS`` days of logs), which is
what turns the calculator into something that learns from the person (§3.8).
Observed values far from the theoretical one are clamped: they usually mean
missing intake logs, not a 40 % metabolic surprise.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from app.engine.adjustment.types import IntakePoint, TdeeEstimate, TrendEstimate
from app.engine.enums import Confidence

KCAL_PER_KG = 7700
FULL_TRUST_DAYS = 28
MIN_INTAKE_COVERAGE = 0.7
MAX_DEVIATION = 0.25


def mean_intake(intakes: Sequence[IntakePoint], start: date, end: date) -> tuple[float | None, int]:
    """Average logged calories in the window and how many days were logged."""
    values = [point.calories for point in intakes if start <= point.day <= end]
    if not values:
        return None, 0
    return sum(values) / len(values), len(values)


def mean_adherence(intakes: Sequence[IntakePoint], start: date, end: date) -> float | None:
    """Average self-reported adherence in the window, if any was reported."""
    values = [
        point.adherence_pct
        for point in intakes
        if start <= point.day <= end and point.adherence_pct is not None
    ]
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def observed_tdee(intake_kcal: float, weekly_change_kg: float) -> float:
    """Energy balance: what was eaten minus what the weight change accounts for."""
    daily_change = weekly_change_kg / 7
    return intake_kcal - daily_change * KCAL_PER_KG


def estimate_tdee(
    theoretical_kcal: float,
    intakes: Sequence[IntakePoint],
    trend: TrendEstimate,
) -> TdeeEstimate:
    """Blend the theoretical TDEE with the observed one according to the data available."""
    intake, intake_days = mean_intake(intakes, trend.start_day, trend.end_day)
    coverage = intake_days / trend.span_days if trend.span_days else 0.0
    observed: float | None = None
    if (
        intake is not None
        and trend.weekly_change_kg is not None
        and coverage >= MIN_INTAKE_COVERAGE
    ):
        raw = observed_tdee(intake, trend.weekly_change_kg)
        low = theoretical_kcal * (1 - MAX_DEVIATION)
        high = theoretical_kcal * (1 + MAX_DEVIATION)
        observed = round(min(high, max(low, raw)))

    if observed is None:
        return TdeeEstimate(
            theoretical_kcal=round(theoretical_kcal),
            observed_kcal=None,
            blended_kcal=round(theoretical_kcal),
            data_days=trend.span_days,
            intake_days=intake_days,
            weight=0.0,
            confidence=Confidence.LOW,
        )
    weight = min(1.0, trend.span_days / FULL_TRUST_DAYS)
    blended = round((1 - weight) * theoretical_kcal + weight * observed)
    if weight >= 0.75 and trend.confidence is Confidence.HIGH:
        confidence = Confidence.HIGH
    elif weight >= 0.4:
        confidence = Confidence.MEDIUM
    else:
        confidence = Confidence.LOW
    return TdeeEstimate(
        theoretical_kcal=round(theoretical_kcal),
        observed_kcal=observed,
        blended_kcal=blended,
        data_days=trend.span_days,
        intake_days=intake_days,
        weight=round(weight, 2),
        confidence=confidence,
    )
