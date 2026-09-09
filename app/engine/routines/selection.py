"""Choosing one exercise for each slot.

Deterministic scoring (no randomness, so the same inputs always give the same
routine): preferred exercises first, then the slot's target muscle, the
expected mechanic for the role, loaded options over bodyweight when the user
owns the equipment, unilateral variants where the template asks for them, and
a penalty for exercises already used that week so the routine has variety.
Ties are broken by a stable hash of the slug.
"""

from __future__ import annotations

import zlib
from collections.abc import Iterable

from app.engine.enums import Mechanic, MovementPattern, TechnicalLevel
from app.engine.routines.catalog import LEVEL_RANK
from app.engine.routines.splits import ACCESSORY, ISOLATION, MAIN, SECONDARY, Slot
from app.engine.routines.types import ExerciseInfo, RoutineInputs

PREFERRED_BONUS = 100
STAPLE_BONUS = 25
BANDS_PENALTY = 8
EQUIPMENT_BONUS: dict[str, int] = {
    "barbell": 12,
    "trap_bar": 12,
    "smith_machine": 6,
    "dumbbells": 8,
    "cable_machine": 8,
    "lat_pulldown": 8,
    "seated_row_machine": 8,
    "leg_press": 8,
    "hack_squat": 8,
    "leg_extension": 8,
    "leg_curl": 8,
    "chest_press_machine": 7,
    "shoulder_press_machine": 7,
    "pec_deck": 7,
    "calf_raise_machine": 8,
    "ez_bar": 8,
    "kettlebell": 2,
}
# The coach's default picks: classic, well-studied movements that progress easily.
STAPLES: frozenset[str] = frozenset(
    {
        "barbell-squat",
        "front-barbell-squat",
        "leg-press",
        "hack-squat",
        "goblet-squat",
        "dumbbell-squat",
        "bodyweight-squat",
        "split-squat-with-dumbbells",
        "dumbbell-lunges",
        "dumbbell-step-ups",
        "bodyweight-walking-lunge",
        "barbell-deadlift",
        "romanian-deadlift",
        "stiff-legged-dumbbell-deadlift",
        "trap-bar-deadlift",
        "barbell-hip-thrust",
        "butt-lift-bridge",
        "single-leg-glute-bridge",
        "hyperextensions-back-extensions",
        "one-arm-kettlebell-swings",
        "kettlebell-one-legged-deadlift",
        "pull-through",
        "barbell-bench-press-medium-grip",
        "dumbbell-bench-press",
        "incline-dumbbell-press",
        "barbell-incline-bench-press-medium-grip",
        "machine-bench-press",
        "pushups",
        "push-ups-with-feet-elevated",
        "incline-push-up",
        "dips-chest-version",
        "cable-chest-press",
        "standing-military-press",
        "seated-barbell-military-press",
        "dumbbell-shoulder-press",
        "standing-dumbbell-press",
        "machine-shoulder-military-press",
        "arnold-dumbbell-press",
        "handstand-push-ups",
        "shoulder-press-with-bands",
        "pullups",
        "chin-up",
        "wide-grip-lat-pulldown",
        "close-grip-front-lat-pulldown",
        "v-bar-pulldown",
        "band-assisted-pull-up",
        "straight-arm-pulldown",
        "bent-over-barbell-row",
        "one-arm-dumbbell-row",
        "seated-cable-rows",
        "dumbbell-incline-row",
        "inverted-row",
        "bodyweight-mid-row",
        "suspended-row",
        "face-pull",
        "t-bar-row-with-handle",
        "leverage-iso-row",
        "band-pull-apart",
        "plank",
        "hanging-leg-raise",
        "ab-roller",
        "cable-crunch",
        "dead-bug",
        "pallof-press",
        "side-bridge",
        "barbell-curl",
        "ez-bar-curl",
        "dumbbell-bicep-curl",
        "hammer-curls",
        "incline-dumbbell-curl",
        "standing-biceps-cable-curl",
        "triceps-pushdown",
        "triceps-pushdown-rope-attachment",
        "lying-triceps-press",
        "cable-rope-overhead-triceps-extension",
        "standing-dumbbell-triceps-extension",
        "side-lateral-raise",
        "reverse-flyes",
        "cable-rear-delt-fly",
        "standing-low-pulley-deltoid-raise",
        "leg-extensions",
        "lying-leg-curls",
        "seated-leg-curl",
        "standing-calf-raises",
        "seated-calf-raise",
        "calf-press-on-the-leg-press-machine",
        "standing-dumbbell-calf-raise",
        "dumbbell-flyes",
        "cable-crossover",
        "butterfly",
    }
)
TARGET_PRIMARY_BONUS = 40
TARGET_SECONDARY_BONUS = 10
MECHANIC_BONUS = 20
UNILATERAL_BONUS = 15
UNILATERAL_MAIN_PENALTY = 10
BODYWEIGHT_PENALTY = 15
REUSE_PENALTY = 30
LEVEL_BONUS = 5


def matches_slot(exercise: ExerciseInfo, slot: Slot) -> bool:
    """Whether the exercise can fill the slot's pattern (isolation slots need the target muscle)."""
    if slot.pattern is MovementPattern.ISOLATION:
        return slot.target is not None and (
            exercise.primary is slot.target
            and (
                exercise.mechanic is Mechanic.ISOLATION
                or exercise.pattern is MovementPattern.ISOLATION
            )
        )
    return exercise.pattern is slot.pattern


def score(
    exercise: ExerciseInfo,
    slot: Slot,
    inputs: RoutineInputs,
    used: dict[str, int],
    loaded_available: bool,
) -> float:
    """Higher is better."""
    value = 0.0
    if exercise.slug in inputs.preferred_exercises:
        value += PREFERRED_BONUS
    if slot.target is not None:
        if exercise.primary is slot.target:
            value += TARGET_PRIMARY_BONUS
        elif slot.target in exercise.secondary:
            value += TARGET_SECONDARY_BONUS
    if slot.role in (MAIN, SECONDARY) and exercise.mechanic is Mechanic.COMPOUND:
        value += MECHANIC_BONUS
    if slot.role == ISOLATION and exercise.mechanic is Mechanic.ISOLATION:
        value += MECHANIC_BONUS
    if slot.role == MAIN:
        value += LEVEL_BONUS * LEVEL_RANK[exercise.level]
    if slot.unilateral and exercise.is_unilateral:
        value += UNILATERAL_BONUS
    elif exercise.is_unilateral and slot.role == MAIN:
        value -= UNILATERAL_MAIN_PENALTY
    if exercise.is_bodyweight and loaded_available and slot.role in (MAIN, SECONDARY, ACCESSORY):
        value -= BODYWEIGHT_PENALTY
    if exercise.slug in STAPLES:
        value += STAPLE_BONUS
    if loaded_available:
        value += max((EQUIPMENT_BONUS.get(code, 0) for code in exercise.equipment), default=0)
        if "resistance_bands" in exercise.equipment:
            value -= BANDS_PENALTY
    value -= REUSE_PENALTY * used.get(exercise.slug, 0)
    return value


def stable_key(slug: str) -> int:
    """Deterministic tie-breaker independent of hash randomisation."""
    return zlib.crc32(slug.encode("utf-8"))


def pick(
    pool: Iterable[ExerciseInfo],
    slot: Slot,
    inputs: RoutineInputs,
    used: dict[str, int],
    exclude: set[str] | None = None,
) -> ExerciseInfo | None:
    """Best exercise for ``slot`` from ``pool``, or ``None`` when nothing fits."""
    candidates = [
        exercise
        for exercise in pool
        if matches_slot(exercise, slot) and (exclude is None or exercise.slug not in exclude)
    ]
    if not candidates:
        return None
    loaded_available = any(
        not exercise.is_bodyweight and "resistance_bands" not in exercise.equipment
        for exercise in candidates
    )
    candidates.sort(
        key=lambda exercise: (
            -score(exercise, slot, inputs, used, loaded_available),
            stable_key(exercise.slug),
        )
    )
    return candidates[0]


def relaxed_ceiling(ceiling: TechnicalLevel) -> TechnicalLevel | None:
    """The next technical level up, used when nothing fits at the user's level."""
    order = [TechnicalLevel.BEGINNER, TechnicalLevel.INTERMEDIATE, TechnicalLevel.ADVANCED]
    index = order.index(ceiling)
    return order[index + 1] if index + 1 < len(order) else None
