"""Input and output structures of the routine generator (pure dataclasses)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.engine.enums import (
    Force,
    Goal,
    InjuryArea,
    Mechanic,
    MovementPattern,
    MuscleGroup,
    Severity,
    Sex,
    SplitType,
    TechnicalLevel,
    TrainingExperience,
    TrainingLocation,
)
from app.engine.types import InputError, Note, _jsonable

MAX_PRIORITY_MUSCLES = 2


@dataclass(frozen=True)
class ExerciseInfo:
    """Catalogue entry as the generator sees it (built from the DB rows or the seed JSON)."""

    slug: str
    name: str
    primary: MuscleGroup
    secondary: tuple[MuscleGroup, ...]
    pattern: MovementPattern
    mechanic: Mechanic
    force: Force
    level: TechnicalLevel
    equipment: frozenset[str]
    contraindications: tuple[tuple[InjuryArea, Severity], ...] = ()
    is_unilateral: bool = False
    is_bodyweight: bool = False
    alternatives: tuple[str, ...] = ()


@dataclass(frozen=True)
class InjuryInput:
    """An injury declared in the questionnaire."""

    area: InjuryArea
    severity: Severity


@dataclass(frozen=True)
class RoutineInputs:
    """Everything the routine generator needs."""

    sex: Sex
    goal: Goal
    training_experience: TrainingExperience
    training_days_per_week: int
    session_minutes: int
    training_location: TrainingLocation
    equipment: frozenset[str]
    weight_kg: float = 75.0
    injuries: tuple[InjuryInput, ...] = ()
    priority_muscles: tuple[MuscleGroup, ...] = ()
    disliked_exercises: frozenset[str] = frozenset()
    preferred_exercises: frozenset[str] = frozenset()
    daily_steps: int | None = None
    extra_deficit_kcal_per_day: float = 0.0
    reported_fatigue: int | None = None

    def __post_init__(self) -> None:
        """Reject values outside the supported ranges."""
        if not 0 <= self.training_days_per_week <= 7:
            raise InputError(f"training_days_per_week={self.training_days_per_week!r} out of range")
        if not 0 <= self.session_minutes <= 240:
            raise InputError(f"session_minutes={self.session_minutes!r} out of range")
        if len(self.priority_muscles) > MAX_PRIORITY_MUSCLES:
            raise InputError("at most two priority muscles are allowed")
        if not 25 <= self.weight_kg <= 350:
            raise InputError(f"weight_kg={self.weight_kg!r} out of range")
        if self.daily_steps is not None and not 0 <= self.daily_steps <= 60000:
            raise InputError(f"daily_steps={self.daily_steps!r} out of range")
        if self.reported_fatigue is not None and not 1 <= self.reported_fatigue <= 5:
            raise InputError(f"reported_fatigue={self.reported_fatigue!r} out of range")
        if self.extra_deficit_kcal_per_day < 0:
            raise InputError("extra_deficit_kcal_per_day cannot be negative")


@dataclass(frozen=True)
class ExercisePrescription:
    """One exercise inside a training day, fully prescribed."""

    slug: str
    name: str
    pattern: MovementPattern
    primary: MuscleGroup
    role: str
    sets: int
    rep_min: int
    rep_max: int
    rir_start: int
    rir_end: int
    rest_seconds: int
    tempo: str
    load_increment_kg: float
    is_unilateral: bool
    notes: tuple[Note, ...] = ()


@dataclass(frozen=True)
class RoutineDayPlan:
    """A training day."""

    index: int
    name: str
    focus: tuple[MuscleGroup, ...]
    exercises: tuple[ExercisePrescription, ...]
    estimated_minutes: int
    notes: tuple[Note, ...] = ()


@dataclass(frozen=True)
class VolumeEntry:
    """Weekly effective sets planned for a muscle group versus its target range."""

    muscle: MuscleGroup
    planned_sets: float
    target_min: int
    target_max: int
    is_priority: bool
    status: str


@dataclass(frozen=True)
class CardioPrescription:
    """Steps target and LISS/HIIT sessions."""

    daily_steps_target: int
    liss_sessions: int
    liss_minutes: int
    hiit_sessions: int
    hiit_minutes: int
    weekly_kcal_estimate: int
    notes: tuple[Note, ...] = ()


@dataclass(frozen=True)
class RoutinePlan:
    """Full output of the routine generator (or the reasons it was blocked)."""

    status: str
    split_type: SplitType | None
    days_per_week: int
    mesocycle_weeks: int
    deload_every_weeks: int
    weekly_rir: tuple[int, ...]
    days: tuple[RoutineDayPlan, ...] = ()
    volume: tuple[VolumeEntry, ...] = ()
    push_sets: int = 0
    pull_sets: int = 0
    pull_to_push_ratio: float = 0.0
    cardio: CardioPrescription | None = None
    blocked_reasons: tuple[Note, ...] = ()
    notes: tuple[Note, ...] = field(default_factory=tuple)

    @property
    def is_blocked(self) -> bool:
        """Whether no routine could be produced."""
        return self.status == "blocked"

    def all_notes(self) -> tuple[Note, ...]:
        """Every note from every day and stage, in order."""
        parts: list[Note] = list(self.blocked_reasons)
        for day in self.days:
            parts.extend(day.notes)
            for exercise in day.exercises:
                parts.extend(exercise.notes)
        if self.cardio is not None:
            parts.extend(self.cardio.notes)
        parts.extend(self.notes)
        return tuple(parts)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return _jsonable(self)
