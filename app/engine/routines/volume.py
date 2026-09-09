"""Weekly volume targets and accounting.

Effective weekly sets per muscle group by experience (§3.7): beginners 8-12,
intermediates 12-18, advanced 16-22 (in line with the dose-response
meta-analysis of Schoenfeld, Ogborn & Krieger 2017 and Israetel's landmark
ranges). Priority muscles get +27.5 % and the other major groups are scaled
down so the weekly total stays constant. A set counts fully for the primary
muscle and half for each secondary muscle.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from app.engine.enums import MuscleGroup, TrainingExperience
from app.engine.routines.types import ExerciseInfo, VolumeEntry

TIER_BY_EXPERIENCE: dict[TrainingExperience, str] = {
    TrainingExperience.NONE: "beginner",
    TrainingExperience.UNDER_6_MONTHS: "beginner",
    TrainingExperience.MONTHS_6_TO_24: "intermediate",
    TrainingExperience.YEARS_2_TO_5: "intermediate",
    TrainingExperience.OVER_5_YEARS: "advanced",
}
VOLUME_RANGES: dict[str, tuple[int, int]] = {
    "beginner": (8, 12),
    "intermediate": (12, 18),
    "advanced": (16, 22),
}
MAJOR_MUSCLES: tuple[MuscleGroup, ...] = (
    MuscleGroup.CHEST,
    MuscleGroup.BACK,
    MuscleGroup.SHOULDERS,
    MuscleGroup.QUADS,
    MuscleGroup.HAMSTRINGS,
    MuscleGroup.GLUTES,
    MuscleGroup.BICEPS,
    MuscleGroup.TRICEPS,
    MuscleGroup.CALVES,
    MuscleGroup.ABS,
)
PRIORITY_FACTOR = 1.275
SECONDARY_CREDIT = 0.5
LOW_TOLERANCE = 0.75


def experience_tier(experience: TrainingExperience) -> str:
    """``beginner``, ``intermediate`` or ``advanced``."""
    return TIER_BY_EXPERIENCE[experience]


def volume_targets(
    experience: TrainingExperience, priorities: Iterable[MuscleGroup]
) -> dict[MuscleGroup, tuple[int, int]]:
    """Target (min, max) weekly sets per major muscle, with priorities compensated."""
    low, high = VOLUME_RANGES[experience_tier(experience)]
    priority = [muscle for muscle in priorities if muscle in MAJOR_MUSCLES]
    others = [muscle for muscle in MAJOR_MUSCLES if muscle not in priority]
    if not priority:
        return dict.fromkeys(MAJOR_MUSCLES, (low, high))
    # Keep the weekly total constant: what priorities gain, the rest give up.
    total_low = low * len(MAJOR_MUSCLES)
    total_high = high * len(MAJOR_MUSCLES)
    priority_low = round(low * PRIORITY_FACTOR)
    priority_high = round(high * PRIORITY_FACTOR)
    other_low = max(4, math.floor((total_low - priority_low * len(priority)) / len(others)))
    other_high = max(
        other_low + 2, math.floor((total_high - priority_high * len(priority)) / len(others))
    )
    targets = dict.fromkeys(others, (other_low, other_high))
    targets.update(dict.fromkeys(priority, (priority_low, priority_high)))
    return targets


def set_credit(exercise: ExerciseInfo, sets: int) -> dict[MuscleGroup, float]:
    """Effective sets credited to each muscle by one exercise."""
    credit: dict[MuscleGroup, float] = {exercise.primary: float(sets)}
    for muscle in exercise.secondary:
        credit[muscle] = credit.get(muscle, 0.0) + sets * SECONDARY_CREDIT
    return credit


def weekly_volume(week: Iterable[tuple[ExerciseInfo, int]]) -> dict[MuscleGroup, float]:
    """Sum the effective sets of every (exercise, sets) pair over the week."""
    totals: dict[MuscleGroup, float] = {}
    for exercise, sets in week:
        for muscle, value in set_credit(exercise, sets).items():
            totals[muscle] = totals.get(muscle, 0.0) + value
    return totals


def volume_table(
    week: Iterable[tuple[ExerciseInfo, int]],
    targets: dict[MuscleGroup, tuple[int, int]],
    priorities: Iterable[MuscleGroup],
) -> tuple[VolumeEntry, ...]:
    """Planned versus target volume for every major muscle."""
    totals = weekly_volume(week)
    priority = set(priorities)
    entries: list[VolumeEntry] = []
    for muscle in MAJOR_MUSCLES:
        low, high = targets[muscle]
        planned = round(totals.get(muscle, 0.0), 1)
        if planned < low * LOW_TOLERANCE:
            status = "low"
        elif planned > high:
            status = "high"
        else:
            status = "ok"
        entries.append(
            VolumeEntry(
                muscle=muscle,
                planned_sets=planned,
                target_min=low,
                target_max=high,
                is_priority=muscle in priority,
                status=status,
            )
        )
    return tuple(entries)
