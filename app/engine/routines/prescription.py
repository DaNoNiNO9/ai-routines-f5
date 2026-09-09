"""Sets, reps, RIR, rest, tempo, progression, mesocycle and time estimates.

- Rep ranges by role (§3.7): heavy compounds 3-6 (performance goal and
  experienced lifters), main compounds 6-10, accessories 10-15, isolation
  12-20.
- RIR descends across the mesocycle from 3 to 0-1 (Helms et al. 2016 on
  RPE/RIR-based autoregulation; Zourdos et al. 2016).
- Rest: never under two minutes, 3 min on the main compounds (Schoenfeld et
  al. 2016 found longer rests favour hypertrophy). A minute of rest looks
  efficient on paper and is not: the following sets lose reps, so the
  effective volume of the session drops even though the plan says otherwise.
- Double progression: reach the top of the rep range in every set at the
  target RIR, then add the load increment and return to the bottom.
- Deload every 4-8 weeks depending on experience and reported fatigue.
"""

from __future__ import annotations

from app.engine.enums import Goal, MovementPattern, Sex
from app.engine.routines.splits import ACCESSORY, ISOLATION, MAIN, SECONDARY
from app.engine.routines.types import ExerciseInfo

DEFAULT_SETS: dict[str, dict[str, int]] = {
    "beginner": {MAIN: 3, SECONDARY: 3, ACCESSORY: 2, ISOLATION: 2},
    "intermediate": {MAIN: 4, SECONDARY: 3, ACCESSORY: 3, ISOLATION: 3},
    "advanced": {MAIN: 4, SECONDARY: 4, ACCESSORY: 3, ISOLATION: 3},
}
MIN_SETS = 2
MAX_SETS = 5

REP_RANGES: dict[str, tuple[int, int]] = {
    MAIN: (6, 10),
    SECONDARY: (6, 10),
    ACCESSORY: (10, 15),
    ISOLATION: (12, 20),
}
HEAVY_RANGE = (3, 6)
CORE_RANGE = (10, 15)

MIN_REST_SECONDS = 120
REST_SECONDS: dict[str, int] = {MAIN: 180, SECONDARY: 180, ACCESSORY: 150, ISOLATION: 120}
BODYWEIGHT_REST_SECONDS: dict[str, int] = {
    MAIN: 150,
    SECONDARY: 150,
    ACCESSORY: 120,
    ISOLATION: 120,
}
TEMPO_COMPOUND = "2-0-1-0"
TEMPO_ISOLATION = "3-1-1-0"

MESOCYCLE_WEEKS: dict[str, int] = {"beginner": 6, "intermediate": 5, "advanced": 4}
DELOAD_EVERY_WEEKS: dict[str, int] = {"beginner": 8, "intermediate": 6, "advanced": 4}
HIGH_FATIGUE = 4

WARM_UP_MINUTES = 8
TRANSITION_SECONDS = 60
SECONDS_PER_REP = 3
UNILATERAL_WORK_FACTOR = 1.8

LOWER_BODY_PATTERNS = {MovementPattern.KNEE_DOMINANT, MovementPattern.HIP_DOMINANT}
BARBELL_LIKE = {"barbell", "trap_bar", "smith_machine", "ez_bar"}
MACHINE_LIKE = {
    "cable_machine",
    "lat_pulldown",
    "seated_row_machine",
    "leg_press",
    "hack_squat",
    "leg_extension",
    "leg_curl",
    "chest_press_machine",
    "shoulder_press_machine",
    "pec_deck",
    "calf_raise_machine",
    "hip_thrust_machine",
    "hip_abductor_adductor_machine",
    "arm_curl_machine",
}


def default_sets(tier: str, role: str) -> int:
    """Starting sets for a slot before the volume adjustment."""
    return DEFAULT_SETS[tier][role]


def rep_range(role: str, goal: Goal, tier: str, pattern: MovementPattern) -> tuple[int, int]:
    """Rep range for a slot: heavy compounds only for performance and non-beginners."""
    if pattern is MovementPattern.CORE:
        return CORE_RANGE
    if role == MAIN and goal is Goal.PERFORMANCE and tier != "beginner":
        return HEAVY_RANGE
    return REP_RANGES[role]


def rir_bounds(role: str) -> tuple[int, int]:
    """RIR at the start and at the end of the mesocycle."""
    return (3, 1) if role in (MAIN, SECONDARY) else (3, 0)


def weekly_rir(mesocycle_weeks: int) -> tuple[int, ...]:
    """RIR per week, descending from 3 to 1 (last week 0-1 for isolation work)."""
    if mesocycle_weeks <= 4:
        base = (3, 2, 1, 1)
    elif mesocycle_weeks == 5:
        base = (3, 2, 2, 1, 1)
    else:
        base = (3, 3, 2, 2, 1, 1)
    return (
        base[:mesocycle_weeks]
        if mesocycle_weeks <= len(base)
        else base + (1,) * (mesocycle_weeks - len(base))
    )


def mesocycle_and_deload(tier: str, reported_fatigue: int | None) -> tuple[int, int]:
    """Mesocycle length and deload frequency, shortened when fatigue is high."""
    weeks = MESOCYCLE_WEEKS[tier]
    deload = DELOAD_EVERY_WEEKS[tier]
    if reported_fatigue is not None and reported_fatigue >= HIGH_FATIGUE:
        weeks = max(4, weeks - 1)
        deload = max(4, deload - 2)
    return weeks, deload


def rest_seconds(exercise: ExerciseInfo, role: str) -> int:
    """Rest between sets, never under ``MIN_REST_SECONDS``.

    The floor is deliberate and applies to isolation and bodyweight work too:
    resting less looks like fitting more work into the hour, but the next set
    comes out short of reps and the session ends with less effective volume.
    """
    table = BODYWEIGHT_REST_SECONDS if exercise.is_bodyweight else REST_SECONDS
    return max(table[role], MIN_REST_SECONDS)


def tempo_for(_exercise: ExerciseInfo, role: str) -> str:
    """Slower eccentric cue for isolation work, neutral tempo for compounds."""
    return TEMPO_ISOLATION if role == ISOLATION else TEMPO_COMPOUND


def load_increment_kg(exercise: ExerciseInfo, sex: Sex) -> float:
    """Smallest sensible jump once the top of the rep range is reached in every set."""
    female = sex is Sex.FEMALE
    if exercise.is_bodyweight or exercise.equipment <= {"resistance_bands", "body_only"}:
        return 0.0
    if exercise.equipment & BARBELL_LIKE:
        lower = exercise.pattern in LOWER_BODY_PATTERNS
        return (2.5 if female else 5.0) if lower else (1.25 if female else 2.5)
    if "dumbbells" in exercise.equipment:
        return 1.0 if female else 2.0
    if "kettlebell" in exercise.equipment:
        return 2.0 if female else 4.0
    if exercise.equipment & MACHINE_LIKE:
        return 2.5 if female else 5.0
    return 1.25 if female else 2.5


def set_seconds(exercise: ExerciseInfo, role: str, rep_max: int) -> float:
    """Work plus rest for one set."""
    work = rep_max * SECONDS_PER_REP
    if exercise.is_unilateral:
        work *= UNILATERAL_WORK_FACTOR
    return work + rest_seconds(exercise, role)


def estimate_minutes(items: list[tuple[ExerciseInfo, str, int, int]]) -> int:
    """Duration of a day: warm-up + every set's work and rest + transitions.

    ``items`` are ``(exercise, role, sets, rep_max)`` tuples.
    """
    seconds = 0.0
    for exercise, role, sets, rep_max in items:
        seconds += sets * set_seconds(exercise, role, rep_max) + TRANSITION_SECONDS
    return round(WARM_UP_MINUTES + seconds / 60)
