"""Input and output structures of the adjustment engine (pure dataclasses)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.engine.enums import AdjustmentReason, Confidence, Goal, Sex
from app.engine.types import InputError, Note, _jsonable

DEFAULT_REVIEW_INTERVAL_DAYS = 14
MIN_WEIGHT_DAYS = 8
MIN_SPAN_DAYS = 10


@dataclass(frozen=True)
class WeightPoint:
    """One morning weigh-in."""

    day: date
    weight_kg: float


@dataclass(frozen=True)
class IntakePoint:
    """Calories actually eaten in a day, optionally with self-reported adherence."""

    day: date
    calories: float
    adherence_pct: float | None = None


@dataclass(frozen=True)
class AdjustmentInputs:
    """State of the current plan plus the logs since it started."""

    sex: Sex
    goal: Goal
    mode: str
    plan_calories: int
    plan_started_on: date
    expected_weekly_change_kg: float
    bmr_kcal: float
    theoretical_tdee_kcal: float
    weights: tuple[WeightPoint, ...]
    intakes: tuple[IntakePoint, ...] = ()
    today: date = field(default_factory=date.today)
    steps_target: int = 8000
    weeks_in_deficit: int = 0
    last_adjustment_on: date | None = None
    review_interval_days: int = DEFAULT_REVIEW_INTERVAL_DAYS
    stalled_reviews: int = 0

    def __post_init__(self) -> None:
        """Reject impossible states."""
        if self.mode not in ("deficit", "surplus", "maintenance"):
            raise InputError(f"mode={self.mode!r} must be deficit, surplus or maintenance")
        if not 500 <= self.plan_calories <= 10000:
            raise InputError(f"plan_calories={self.plan_calories!r} out of range")
        if self.review_interval_days < 7:
            raise InputError("review_interval_days must be at least 7")
        if not 0 <= self.steps_target <= 30000:
            raise InputError(f"steps_target={self.steps_target!r} out of range")
        if self.weeks_in_deficit < 0 or self.stalled_reviews < 0:
            raise InputError("counters cannot be negative")
        for point in self.weights:
            if not 25 <= point.weight_kg <= 350:
                raise InputError(f"weight {point.weight_kg!r} on {point.day} out of range")
        for point in self.intakes:
            if not 0 <= point.calories <= 20000:
                raise InputError(f"intake {point.calories!r} on {point.day} out of range")

    @property
    def current_weight_kg(self) -> float:
        """Latest logged weight, or the first one if nothing else."""
        if not self.weights:
            raise InputError("at least one weight is required")
        return max(self.weights, key=lambda point: point.day).weight_kg


@dataclass(frozen=True)
class TrendEstimate:
    """Weight trend from the smoothed series."""

    start_day: date
    end_day: date
    span_days: int
    weight_days: int
    start_average_kg: float | None
    end_average_kg: float | None
    weekly_change_kg: float | None
    confidence: Confidence


@dataclass(frozen=True)
class TdeeEstimate:
    """Observed expenditure from energy balance, blended with the theoretical value."""

    theoretical_kcal: float
    observed_kcal: float | None
    blended_kcal: float
    data_days: int
    intake_days: int
    weight: float
    confidence: Confidence


@dataclass(frozen=True)
class AdjustmentDecision:
    """What to do at this review and why."""

    action: str
    reason: AdjustmentReason
    review_due: bool
    new_calories: int
    calorie_delta: int
    steps_delta: int
    new_steps_target: int
    observed_weekly_change_kg: float | None
    expected_weekly_change_kg: float
    adherence_pct: float | None
    trend: TrendEstimate | None
    tdee: TdeeEstimate | None
    next_review_on: date
    notes: tuple[Note, ...] = ()

    @property
    def changes_plan(self) -> bool:
        """Whether calories or steps change."""
        return self.calorie_delta != 0 or self.steps_delta != 0

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return _jsonable(self)
