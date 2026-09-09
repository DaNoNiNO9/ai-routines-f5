"""Catalogue helpers: building ``ExerciseInfo`` and applying the hard filters.

The filters are the non-negotiable part of the selection (§3.7): equipment
the user actually has, no contraindicated exercise for their injuries, no
disliked exercise, and a technical level they can handle.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.engine.enums import (
    Force,
    InjuryArea,
    Mechanic,
    MovementPattern,
    MuscleGroup,
    Severity,
    TechnicalLevel,
    TrainingExperience,
)
from app.engine.routines.types import ExerciseInfo, InjuryInput, RoutineInputs

SEVERITY_RANK: dict[Severity, int] = {Severity.MILD: 1, Severity.MODERATE: 2, Severity.SEVERE: 3}
LEVEL_RANK: dict[TechnicalLevel, int] = {
    TechnicalLevel.BEGINNER: 0,
    TechnicalLevel.INTERMEDIATE: 1,
    TechnicalLevel.ADVANCED: 2,
}
ALLOWED_LEVEL: dict[TrainingExperience, TechnicalLevel] = {
    TrainingExperience.NONE: TechnicalLevel.BEGINNER,
    TrainingExperience.UNDER_6_MONTHS: TechnicalLevel.BEGINNER,
    TrainingExperience.MONTHS_6_TO_24: TechnicalLevel.INTERMEDIATE,
    TrainingExperience.YEARS_2_TO_5: TechnicalLevel.ADVANCED,
    TrainingExperience.OVER_5_YEARS: TechnicalLevel.ADVANCED,
}


def exercise_from_dict(row: Mapping[str, Any]) -> ExerciseInfo:
    """Build an ``ExerciseInfo`` from a seed JSON entry (or any mapping with the same keys)."""
    return ExerciseInfo(
        slug=str(row["slug"]),
        name=str(row.get("name_es") or row.get("name") or row["slug"]),
        primary=MuscleGroup(row["primary_muscle"]),
        secondary=tuple(MuscleGroup(m) for m in row.get("secondary_muscles", [])),
        pattern=MovementPattern(row["movement_pattern"]),
        mechanic=Mechanic(row["mechanic"]),
        force=Force(row["force"]),
        level=TechnicalLevel(row["technical_level"]),
        equipment=frozenset(str(code) for code in row.get("equipment", [])),
        contraindications=tuple(
            (InjuryArea(item["area"]), Severity(item["min_severity"]))
            for item in row.get("contraindications", [])
        ),
        is_unilateral=bool(row.get("is_unilateral", False)),
        is_bodyweight=bool(row.get("is_bodyweight", False)),
        alternatives=tuple(str(alt["slug"]) for alt in row.get("alternatives", [])),
    )


def allowed_level(experience: TrainingExperience) -> TechnicalLevel:
    """Highest technical level the user can be prescribed by default."""
    return ALLOWED_LEVEL[experience]


def is_contraindicated(exercise: ExerciseInfo, injuries: Iterable[InjuryInput]) -> bool:
    """True when any declared injury reaches the exercise's minimum severity for that area."""
    declared = {injury.area: SEVERITY_RANK[injury.severity] for injury in injuries}
    for area, min_severity in exercise.contraindications:
        if area in declared and declared[area] >= SEVERITY_RANK[min_severity]:
            return True
    return False


def equipment_available(exercise: ExerciseInfo, equipment: frozenset[str]) -> bool:
    """All the equipment the exercise needs is in the user's list."""
    return exercise.equipment <= equipment


def level_ok(exercise: ExerciseInfo, ceiling: TechnicalLevel) -> bool:
    """The exercise does not demand more skill than ``ceiling``."""
    return LEVEL_RANK[exercise.level] <= LEVEL_RANK[ceiling]


def usable_exercises(
    exercises: Iterable[ExerciseInfo], inputs: RoutineInputs, ceiling: TechnicalLevel
) -> list[ExerciseInfo]:
    """Apply every hard filter; the result is the pool the selection works with."""
    return [
        exercise
        for exercise in exercises
        if equipment_available(exercise, inputs.equipment)
        and not is_contraindicated(exercise, inputs.injuries)
        and exercise.slug not in inputs.disliked_exercises
        and level_ok(exercise, ceiling)
    ]


def has_shoulder_history(injuries: Iterable[InjuryInput]) -> bool:
    """Any declared shoulder issue shifts the push/pull balance towards pulling."""
    return any(injury.area is InjuryArea.SHOULDER for injury in injuries)
