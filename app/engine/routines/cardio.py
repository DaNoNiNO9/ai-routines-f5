"""Steps target and LISS/HIIT sessions.

Rule (§3.7): the deficit is covered by the diet first (the nutrition engine
does that, up to its floors); whatever it could not cover arrives here as
``extra_deficit_kcal_per_day`` and is covered with steps first, then LISS,
then at most one HIIT session. Cardio is never prescribed as punishment: the
prescription is the same whether or not the user stuck to the diet.

Energy per session: (MET - 1) x kg x hours with LISS at 5 METs (brisk walk,
easy cycling) and HIIT at 9 METs (Ainsworth et al. 2011).
"""

from __future__ import annotations

import math

from app.engine.enums import Goal, InjuryArea, Severity
from app.engine.routines.types import CardioPrescription, RoutineInputs
from app.engine.tdee import STEP_LENGTH_M, WALKING_NET_KCAL_PER_KG_KM
from app.engine.types import Note

LISS_MET = 5.0
HIIT_MET = 9.0
LISS_MINUTES = 30
HIIT_MINUTES = 20
MAX_LISS_SESSIONS = 3
MAX_HIIT_SESSIONS = 1
DEFAULT_STEPS = 6000
FAT_LOSS_STEP_BUMP = 2000
FAT_LOSS_MIN_STEPS = 8000
MAX_STEPS_TARGET = 12000
HEALTH_MIN_STEPS = 7000
HEALTH_LISS_SESSIONS = 2
HIIT_UNSAFE_AREAS = {InjuryArea.KNEE, InjuryArea.ANKLE, InjuryArea.HIP, InjuryArea.LOWER_BACK}


def steps_target(current: int | None, goal: Goal) -> int:
    """Daily steps to aim for: a modest bump when losing fat, a health floor otherwise."""
    base = current if current is not None else DEFAULT_STEPS
    if goal is Goal.FAT_LOSS:
        return min(MAX_STEPS_TARGET, max(FAT_LOSS_MIN_STEPS, base + FAT_LOSS_STEP_BUMP))
    return max(HEALTH_MIN_STEPS, base)


def session_kcal(met: float, weight_kg: float, minutes: int) -> float:
    """Net energy of one cardio session."""
    return (met - 1) * weight_kg * minutes / 60


def steps_kcal_per_day(extra_steps: int, weight_kg: float) -> float:
    """Net energy of walking ``extra_steps`` more per day."""
    return extra_steps * STEP_LENGTH_M / 1000 * WALKING_NET_KCAL_PER_KG_KM * weight_kg


def hiit_allowed(inputs: RoutineInputs) -> bool:
    """HIIT only for people with some training history and no lower-body injury above mild."""
    if inputs.training_experience.value in ("none", "under_6_months"):
        return False
    return not any(
        injury.area in HIIT_UNSAFE_AREAS and injury.severity is not Severity.MILD
        for injury in inputs.injuries
    )


def cardio_prescription(inputs: RoutineInputs) -> CardioPrescription:
    """Steps plus LISS/HIIT sessions sized to the deficit the diet could not cover."""
    notes: list[Note] = [Note("cardio.not_punishment")]
    current = inputs.daily_steps if inputs.daily_steps is not None else DEFAULT_STEPS
    target = steps_target(inputs.daily_steps, inputs.goal)
    weekly_needed = inputs.extra_deficit_kcal_per_day * 7
    covered = 7 * steps_kcal_per_day(max(0, target - current), inputs.weight_kg)

    liss_kcal = session_kcal(LISS_MET, inputs.weight_kg, LISS_MINUTES)
    hiit_kcal = session_kcal(HIIT_MET, inputs.weight_kg, HIIT_MINUTES)
    liss = 0
    hiit = 0
    remaining = max(0.0, weekly_needed - covered)
    if remaining > 0:
        liss = min(MAX_LISS_SESSIONS, math.ceil(remaining / liss_kcal))
        remaining = max(0.0, remaining - liss * liss_kcal)
    if remaining > 0 and hiit_allowed(inputs):
        hiit = MAX_HIIT_SESSIONS
        remaining = max(0.0, remaining - hiit * hiit_kcal)
    if remaining > 0:
        notes.append(
            Note("cardio.deficit_not_covered", level="warning", params={"kcal": round(remaining)})
        )

    if weekly_needed == 0 and liss == 0:
        liss = HEALTH_LISS_SESSIONS
        notes.append(Note("cardio.health_sessions", params={"sessions": liss}))

    weekly_estimate = covered + liss * liss_kcal + hiit * hiit_kcal
    notes.append(
        Note(
            "cardio.summary",
            params={"steps": target, "liss": liss, "hiit": hiit, "kcal": round(weekly_estimate)},
        )
    )
    return CardioPrescription(
        daily_steps_target=target,
        liss_sessions=liss,
        liss_minutes=LISS_MINUTES,
        hiit_sessions=hiit,
        hiit_minutes=HIIT_MINUTES,
        weekly_kcal_estimate=round(weekly_estimate),
        notes=tuple(notes),
    )
