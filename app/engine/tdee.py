"""Total daily energy expenditure built by components.

    TDEE = BMR + NEAT + EAT + TEF

- NEAT (non-exercise activity): walking energy from daily steps plus a
  daily-living and occupational extra. Walking costs about 0.5 kcal per kg per km net of rest
  (ACSM metabolic equation for walking, ~0.1 mL O2/kg/m); an average step is
  0.75 m (Tudor-Locke & Bassett 2004). When steps are unknown they are
  estimated from the job using the Tudor-Locke step categories.
- EAT (exercise activity): (MET - 1) x kg x hours, averaged over the week.
  METs from the 2011 Compendium of Physical Activities (Ainsworth et al.):
  resistance training 3.5-6.0 (4.0 used), light sport ~3, moderate ~6, vigorous ~9.
- TEF (thermic effect of food): 10 % of intake (Westerterp 2004), solved
  iteratively on the target intake, not on the TDEE.
- A small lifestyle modifier lowers the activity components with short sleep
  and high stress (sleep restriction reduces spontaneous activity: Spaeth et
  al. 2013; kept deliberately conservative).

The classic multiplier method (1.2-1.9 x BMR) is computed as a contrast; a
divergence above 15 % flags inconsistent inputs.
"""

from __future__ import annotations

from app.engine.enums import ActivityIntensity, Confidence, JobActivity
from app.engine.types import BmrEstimate, BodyComposition, EnergyExpenditure, Note, NutritionInputs

WALKING_NET_KCAL_PER_KG_KM = 0.5
STEP_LENGTH_M = 0.75
TEF_FRACTION = 0.10
DIVERGENCE_WARNING_PCT = 15.0

STEPS_BY_JOB: dict[JobActivity, int] = {
    JobActivity.SEDENTARY: 4000,
    JobActivity.STANDING: 7000,
    JobActivity.LIGHT_PHYSICAL: 9000,
    JobActivity.HEAVY_PHYSICAL: 12000,
}

# Daily-living activity that is not counted as steps (household tasks, posture,
# fidgeting: roughly 150 kcal even for sedentary people, Levine 2004) plus the
# occupational extra of standing or physical jobs, kcal/day.
JOB_EXTRA_KCAL: dict[JobActivity, float] = {
    JobActivity.SEDENTARY: 150.0,
    JobActivity.STANDING: 250.0,
    JobActivity.LIGHT_PHYSICAL: 400.0,
    JobActivity.HEAVY_PHYSICAL: 650.0,
}

GYM_SESSION_MET = 4.0
OTHER_ACTIVITY_MET: dict[ActivityIntensity, float] = {
    ActivityIntensity.LOW: 3.0,
    ActivityIntensity.MODERATE: 6.0,
    ActivityIntensity.HIGH: 9.0,
}

SLEEP_SHORT_HOURS = 6.0
SLEEP_LOW_HOURS = 7.0
SLEEP_SHORT_PENALTY = 0.03
SLEEP_LOW_PENALTY = 0.015
STRESS_HIGH_LEVEL = 4
STRESS_PENALTY = 0.02


def steps_from_job(job: JobActivity) -> int:
    """Typical daily steps for an occupation when the user does not know theirs."""
    return STEPS_BY_JOB[job]


def walking_kcal(steps: int, weight_kg: float) -> float:
    """Net energy of ``steps`` at 0.75 m/step and 0.5 kcal/kg/km."""
    kilometres = steps * STEP_LENGTH_M / 1000
    return kilometres * WALKING_NET_KCAL_PER_KG_KM * weight_kg


def neat_kcal(steps: int, weight_kg: float, job: JobActivity) -> float:
    """Walking energy plus the occupational extra."""
    return walking_kcal(steps, weight_kg) + JOB_EXTRA_KCAL[job]


def activity_kcal(met: float, weight_kg: float, minutes: float) -> float:
    """Net energy of an activity: (MET - 1) x kg x hours."""
    return (met - 1) * weight_kg * minutes / 60


def eat_kcal_per_day(inputs: NutritionInputs, weight_kg: float) -> float:
    """Weekly exercise energy (gym plus other sport) averaged per day."""
    weekly = inputs.training_days_per_week * activity_kcal(
        GYM_SESSION_MET, weight_kg, inputs.session_minutes
    )
    if inputs.other_activity_intensity is not None:
        met = OTHER_ACTIVITY_MET[inputs.other_activity_intensity]
        weekly += inputs.other_activity_sessions_per_week * activity_kcal(
            met, weight_kg, inputs.other_activity_minutes
        )
    return weekly / 7


def lifestyle_modifier(sleep_hours: float, stress_level: int) -> float:
    """Multiplier (0.95-1.0) applied to NEAT and EAT for short sleep and high stress."""
    penalty = 0.0
    if sleep_hours < SLEEP_SHORT_HOURS:
        penalty += SLEEP_SHORT_PENALTY
    elif sleep_hours < SLEEP_LOW_HOURS:
        penalty += SLEEP_LOW_PENALTY
    if stress_level >= STRESS_HIGH_LEVEL:
        penalty += STRESS_PENALTY
    return 1 - penalty


def solve_intake(base_kcal: float, ratio: float, tolerance: float = 0.5) -> float:
    """Intake I such that I = ratio x (base + TEF(I)), with TEF = 10 % of intake.

    Solved by fixed-point iteration (converges in a handful of steps because the
    TEF fraction is small). ``ratio`` is 1 for maintenance, 0.8 for a 20 %
    deficit, 1.1 for a 10 % surplus.
    """
    intake = base_kcal * ratio
    for _ in range(50):
        updated = ratio * (base_kcal + TEF_FRACTION * intake)
        if abs(updated - intake) < tolerance:
            return updated
        intake = updated
    return intake


def expenditure_at_intake(base_kcal: float, intake_kcal: float) -> float:
    """Energy spent when eating ``intake_kcal``: base components plus TEF."""
    return base_kcal + TEF_FRACTION * intake_kcal


def classic_activity_factor(training_days: int, job: JobActivity) -> float:
    """Traditional multipliers: 1.2 sedentary ... 1.9 very active with a physical job."""
    physical_job = job in (JobActivity.LIGHT_PHYSICAL, JobActivity.HEAVY_PHYSICAL)
    if training_days == 0:
        factor = 1.2
    elif training_days <= 3:
        factor = 1.375
    elif training_days <= 5:
        factor = 1.55
    else:
        factor = 1.725
    if physical_job:
        factor = min(1.9, factor + 0.175)
    return factor


def estimate_expenditure(
    inputs: NutritionInputs, body: BodyComposition, bmr: BmrEstimate
) -> EnergyExpenditure:
    """Assemble the TDEE by components and contrast it with the classic method."""
    notes: list[Note] = []
    steps_estimated = inputs.daily_steps is None
    steps = (
        inputs.daily_steps
        if inputs.daily_steps is not None
        else steps_from_job(inputs.job_activity)
    )
    if steps_estimated:
        notes.append(
            Note("tdee.steps_estimated", params={"steps": steps, "job": inputs.job_activity.value})
        )

    neat = neat_kcal(steps, body.weight_kg, inputs.job_activity)
    eat = eat_kcal_per_day(inputs, body.weight_kg)
    modifier = lifestyle_modifier(inputs.sleep_hours, inputs.stress_level)
    if modifier < 1:
        notes.append(
            Note("tdee.lifestyle_modifier", params={"pct": round((1 - modifier) * 100, 1)})
        )

    base = bmr.selected_kcal + (neat + eat) * modifier
    maintenance = solve_intake(base, 1.0)
    tef = maintenance - base

    classic_factor = classic_activity_factor(inputs.training_days_per_week, inputs.job_activity)
    classic = bmr.selected_kcal * classic_factor
    divergence = (maintenance - classic) / classic * 100
    if abs(divergence) > DIVERGENCE_WARNING_PCT:
        notes.append(
            Note(
                "tdee.divergence",
                level="warning",
                params={
                    "components": round(maintenance),
                    "classic": round(classic),
                    "pct": round(divergence, 1),
                },
            )
        )

    return EnergyExpenditure(
        bmr_kcal=bmr.selected_kcal,
        neat_kcal=round(neat),
        eat_kcal=round(eat),
        lifestyle_modifier=modifier,
        base_kcal=round(base),
        maintenance_kcal=round(maintenance),
        tef_at_maintenance_kcal=round(tef),
        steps_used=steps,
        steps_estimated=steps_estimated,
        classic_factor=classic_factor,
        classic_kcal=round(classic),
        divergence_pct=round(divergence, 1),
        notes=tuple(notes),
    )


def expenditure_confidence(expenditure: EnergyExpenditure, body: BodyComposition) -> Confidence:
    """Overall confidence: body-fat confidence, capped by estimated steps and divergence."""
    order = [Confidence.LOW, Confidence.MEDIUM, Confidence.HIGH]
    level = order.index(body.confidence)
    if expenditure.steps_estimated:
        level = min(level, order.index(Confidence.MEDIUM))
    if abs(expenditure.divergence_pct) > DIVERGENCE_WARNING_PCT:
        level = order.index(Confidence.LOW)
    return order[level]
