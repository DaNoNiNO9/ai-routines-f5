"""Input and output structures of the nutrition engine.

Everything is an immutable dataclass so results can be stored as JSON
(``to_dict``) and reproduced later. ``NutritionInputs`` validates its own
ranges: the engine never trusts the caller.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any

from app.engine.enums import (
    ActivityIntensity,
    Aggressiveness,
    BmrMethod,
    BodyFatMethod,
    Confidence,
    Goal,
    JobActivity,
    MealTiming,
    Sex,
    TrainingExperience,
    TrainingTime,
)


class InputError(ValueError):
    """An input is outside the range the engine can work with."""


@dataclass(frozen=True)
class Note:
    """A message for the user or the log: a stable ``code`` plus parameters.

    ``level`` is ``info`` (explanation), ``warning`` (something to review) or
    ``error`` (a reason a plan was not produced). Templates live in
    ``app/engine/messages.py``.
    """

    code: str
    level: str = "info"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NutritionInputs:
    """Everything the nutrition engine needs, already converted to plain values."""

    sex: Sex
    age: int
    height_cm: float
    weight_kg: float
    goal: Goal
    training_days_per_week: int
    session_minutes: int
    training_experience: TrainingExperience
    job_activity: JobActivity
    sleep_hours: float
    stress_level: int
    meals_per_day: int
    neck_cm: float | None = None
    waist_cm: float | None = None
    hip_cm: float | None = None
    body_fat_pct: float | None = None
    body_fat_method: BodyFatMethod = BodyFatMethod.NONE
    daily_steps: int | None = None
    other_activity_sessions_per_week: int = 0
    other_activity_minutes: int = 0
    other_activity_intensity: ActivityIntensity | None = None
    aggressiveness: Aggressiveness = Aggressiveness.MODERATE
    target_weight_kg: float | None = None
    target_date: date | None = None
    today: date = field(default_factory=date.today)
    training_time: TrainingTime = TrainingTime.NONE
    wants_carb_cycling: bool = False
    is_pregnant_or_breastfeeding: bool = False
    has_eating_disorder_history: bool = False

    def __post_init__(self) -> None:
        """Reject values the formulas cannot handle (wide ranges, not clinical ones)."""
        _check(10 <= self.age <= 110, "age", self.age)
        _check(100 <= self.height_cm <= 250, "height_cm", self.height_cm)
        _check(25 <= self.weight_kg <= 350, "weight_kg", self.weight_kg)
        _check(
            0 <= self.training_days_per_week <= 7,
            "training_days_per_week",
            self.training_days_per_week,
        )
        _check(0 <= self.session_minutes <= 240, "session_minutes", self.session_minutes)
        _check(0 <= self.sleep_hours <= 16, "sleep_hours", self.sleep_hours)
        _check(1 <= self.stress_level <= 5, "stress_level", self.stress_level)
        _check(1 <= self.meals_per_day <= 8, "meals_per_day", self.meals_per_day)
        for name in ("neck_cm", "waist_cm", "hip_cm"):
            value = getattr(self, name)
            _check(value is None or 15 <= value <= 250, name, value)
        _check(
            self.body_fat_pct is None or 2 <= self.body_fat_pct <= 70,
            "body_fat_pct",
            self.body_fat_pct,
        )
        _check(
            self.daily_steps is None or 0 <= self.daily_steps <= 60000,
            "daily_steps",
            self.daily_steps,
        )
        _check(
            0 <= self.other_activity_sessions_per_week <= 14,
            "other_activity_sessions_per_week",
            self.other_activity_sessions_per_week,
        )
        _check(
            0 <= self.other_activity_minutes <= 300,
            "other_activity_minutes",
            self.other_activity_minutes,
        )
        _check(
            self.target_weight_kg is None or 25 <= self.target_weight_kg <= 350,
            "target_weight_kg",
            self.target_weight_kg,
        )
        if self.body_fat_pct is not None and self.body_fat_method is BodyFatMethod.NONE:
            object.__setattr__(self, "body_fat_method", BodyFatMethod.VISUAL)


def _check(condition: bool, name: str, value: Any) -> None:
    if not condition:
        raise InputError(f"{name}={value!r} is outside the supported range")


@dataclass(frozen=True)
class BodyComposition:
    """Body-fat estimate, lean mass and how much to trust them."""

    weight_kg: float
    height_cm: float
    bmi: float
    body_fat_pct: float | None
    body_fat_source: BodyFatMethod
    lean_mass_kg: float | None
    confidence: Confidence
    notes: tuple[Note, ...] = ()


@dataclass(frozen=True)
class BmrEstimate:
    """Basal metabolic rate: the selected value plus the range of all formulas."""

    selected_kcal: float
    method: BmrMethod
    estimates: dict[BmrMethod, float]
    low_kcal: float
    high_kcal: float
    notes: tuple[Note, ...] = ()


@dataclass(frozen=True)
class EnergyExpenditure:
    """TDEE built by components (BMR + NEAT + EAT + TEF) and the classic contrast."""

    bmr_kcal: float
    neat_kcal: float
    eat_kcal: float
    lifestyle_modifier: float
    base_kcal: float
    maintenance_kcal: float
    tef_at_maintenance_kcal: float
    steps_used: int
    steps_estimated: bool
    classic_factor: float
    classic_kcal: float
    divergence_pct: float
    notes: tuple[Note, ...] = ()


@dataclass(frozen=True)
class CalorieTarget:
    """Daily calorie goal and the energy balance it implies."""

    goal: Goal
    mode: str
    fraction: float
    maintenance_kcal: float
    target_kcal: int
    expenditure_at_target_kcal: float
    daily_balance_kcal: float
    expected_weekly_change_kg: float
    notes: tuple[Note, ...] = ()


@dataclass(frozen=True)
class Macros:
    """Daily macronutrients. ``calories`` may exceed the target when the carb floor forced it."""

    calories: int
    protein_g: int
    fat_g: int
    carbs_g: int
    fiber_g: int
    protein_per_kg: float
    protein_basis: str
    fat_fraction: float
    carb_floor_g: int
    calories_added_for_carb_floor: int
    notes: tuple[Note, ...] = ()


@dataclass(frozen=True)
class Hydration:
    """Water intake: baseline and extra on training days."""

    base_ml: int
    per_session_ml: int
    training_day_ml: int


@dataclass(frozen=True)
class MealSlot:
    """Calories and macros of one meal."""

    position: int
    name: str
    timing: MealTiming
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int


@dataclass(frozen=True)
class DayMacros:
    """Macros of one kind of day inside a carb cycle."""

    label: str
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int


@dataclass(frozen=True)
class CarbCycle:
    """High (training) and low (rest) days whose weekly average equals the base plan."""

    training_days: int
    rest_days: int
    high_day: DayMacros
    low_day: DayMacros
    weekly_average_carbs_g: float
    notes: tuple[Note, ...] = ()


@dataclass(frozen=True)
class NutritionPlan:
    """Full output of the nutrition engine (or the reasons it was blocked)."""

    status: str
    confidence: Confidence
    body: BodyComposition
    blocked_reasons: tuple[Note, ...] = ()
    bmr: BmrEstimate | None = None
    expenditure: EnergyExpenditure | None = None
    target: CalorieTarget | None = None
    macros: Macros | None = None
    hydration: Hydration | None = None
    meals: tuple[MealSlot, ...] = ()
    carb_cycle: CarbCycle | None = None
    notes: tuple[Note, ...] = ()
    disclaimer: bool = True

    @property
    def is_blocked(self) -> bool:
        """Whether safety stopped the plan."""
        return self.status == "blocked"

    def all_notes(self) -> tuple[Note, ...]:
        """Every note produced by every stage, in order."""
        parts: list[Note] = list(self.blocked_reasons)
        for stage in (
            self.body,
            self.bmr,
            self.expenditure,
            self.target,
            self.macros,
            self.carb_cycle,
        ):
            if stage is not None:
                parts.extend(stage.notes)
        parts.extend(self.notes)
        return tuple(parts)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation (enums as values, dates as ISO strings)."""
        return _jsonable(self)


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {_jsonable(k) if isinstance(k, Enum) else k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, set | frozenset):
        return sorted(_jsonable(item) for item in value)
    return value
