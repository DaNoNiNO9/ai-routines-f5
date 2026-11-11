"""Starting loads for a first session and load adjustments between sets.

Nobody should face an empty kg field. The first time an exercise appears, the
engine estimates a conservative working load; after each set it re-estimates
from what was actually lifted.

- Starting load: a novice one-rep max as a fraction of bodyweight by movement
  pattern (rounded figures from common strength standards: squat ~1.0x,
  deadlift ~1.25x, bench ~0.75x, overhead press ~0.5x, rows and pulldowns
  ~0.6x for men), scaled by sex and training experience, then 65 % of it,
  which sits above 10 reps at RIR 3: deliberately light, the next set corrects it.
- Dumbbells and kettlebells are loaded per hand: each one carries 40 % of the
  equivalent barbell load. Unilateral work takes half again.
- Between sets: Epley with reps in reserve, ``e1RM = kg x (1 + (reps + RIR) / 30)``
  (Epley 1985; RIR-based estimation as in Helms et al. 2016), solved for the
  load that leaves the target reps at the target RIR.
- Every load is rounded down to what the equipment can actually hold.
"""

from __future__ import annotations

import math

from app.engine.enums import Mechanic, MovementPattern, Sex, TrainingExperience
from app.engine.routines.prescription import BARBELL_LIKE, LOWER_BODY_PATTERNS
from app.engine.routines.types import ExerciseInfo

NOVICE_1RM_PER_KG: dict[MovementPattern, float] = {
    MovementPattern.KNEE_DOMINANT: 1.0,
    MovementPattern.HIP_DOMINANT: 1.25,
    MovementPattern.HORIZONTAL_PUSH: 0.75,
    MovementPattern.VERTICAL_PUSH: 0.5,
    MovementPattern.HORIZONTAL_PULL: 0.6,
    MovementPattern.VERTICAL_PULL: 0.6,
    MovementPattern.CORE: 0.2,
    MovementPattern.ISOLATION: 0.25,
}
ISOLATION_1RM_PER_KG = 0.25
EXPERIENCE_FACTOR: dict[TrainingExperience, float] = {
    TrainingExperience.NONE: 0.5,
    TrainingExperience.UNDER_6_MONTHS: 0.7,
    TrainingExperience.MONTHS_6_TO_24: 1.0,
    TrainingExperience.YEARS_2_TO_5: 1.35,
    TrainingExperience.OVER_5_YEARS: 1.6,
}
FEMALE_FACTOR_UPPER = 0.6
FEMALE_FACTOR_LOWER = 0.7
STARTING_FRACTION_OF_1RM = 0.65
PER_HAND_FRACTION = 0.4
UNILATERAL_FRACTION = 0.5
MAX_STEP_UP = 0.15
MAX_STEP_DOWN = 0.25
KEEP_BAND = 0.03  # about one rep either way: noise, not a signal

BAR_KG = {"barbell": 20.0, "trap_bar": 25.0, "ez_bar": 10.0, "smith_machine": 15.0}
FREE_WEIGHT_PER_HAND = {"dumbbells": 2.0, "kettlebell": 4.0}
NO_EXTERNAL_LOAD = {
    "body_only",
    "resistance_bands",
    "pull_up_bar",
    "dip_station",
    "suspension_trainer",
}
DEFAULT_STEP_KG = 2.5


def loads_weight(exercise: ExerciseInfo) -> bool:
    """Whether the exercise takes a load in kg at all."""
    return not exercise.is_bodyweight and not exercise.equipment <= NO_EXTERNAL_LOAD


def round_load(exercise: ExerciseInfo, kg: float) -> float:
    """Round down to a load the equipment can hold: plates, dumbbell pairs, stack steps."""
    bar = next((BAR_KG[code] for code in BAR_KG if code in exercise.equipment), None)
    if bar is not None:
        return max(bar, bar + math.floor((kg - bar) / 2.5) * 2.5)
    step = next(
        (FREE_WEIGHT_PER_HAND[code] for code in FREE_WEIGHT_PER_HAND if code in exercise.equipment),
        DEFAULT_STEP_KG,
    )
    return max(step, math.floor(kg / step) * step)


def starting_load(
    exercise: ExerciseInfo,
    sex: Sex,
    bodyweight_kg: float,
    experience: TrainingExperience,
) -> float | None:
    """Conservative working load for someone doing the exercise for the first time.

    ``None`` when the exercise has no external load (bodyweight, bands).
    """
    if not loads_weight(exercise):
        return None
    per_kg = (
        ISOLATION_1RM_PER_KG
        if exercise.mechanic is Mechanic.ISOLATION
        else NOVICE_1RM_PER_KG[exercise.pattern]
    )
    if sex is Sex.FEMALE:
        lower = exercise.pattern in LOWER_BODY_PATTERNS
        per_kg *= FEMALE_FACTOR_LOWER if lower else FEMALE_FACTOR_UPPER
    kg = bodyweight_kg * per_kg * EXPERIENCE_FACTOR[experience] * STARTING_FRACTION_OF_1RM
    if exercise.equipment & set(FREE_WEIGHT_PER_HAND) and not exercise.equipment & BARBELL_LIKE:
        kg *= PER_HAND_FRACTION
    if exercise.is_unilateral:
        kg *= UNILATERAL_FRACTION
    return round_load(exercise, kg)


def next_set_load(
    exercise: ExerciseInfo,
    weight_kg: float,
    reps: int,
    rir: int | None,
    target_reps: int,
    target_rir: int,
) -> float:
    """Load for the next set, re-estimated from the one just done.

    Without a reported RIR there is nothing to learn from: the load stays. A
    difference worth one rep or less is noise and keeps the load too. The
    change is capped (+15 % / -25 %) so one odd set never swings the session.
    """
    if rir is None or weight_kg <= 0 or reps <= 0:
        return weight_kg
    e1rm = weight_kg * (1 + (reps + rir) / 30)
    wanted = e1rm / (1 + (target_reps + target_rir) / 30)
    wanted = min(weight_kg * (1 + MAX_STEP_UP), max(weight_kg * (1 - MAX_STEP_DOWN), wanted))
    if abs(wanted - weight_kg) <= KEEP_BAND * weight_kg:
        return weight_kg
    return round_load(exercise, wanted)
