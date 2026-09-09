"""Calorie target by goal, with the safety limits applied as part of the maths.

Rules (see ``docs/`` and the engine README for the reasoning):
- Fat loss: deficit of 10-25 % of expenditure, larger the more body fat there
  is (Helms, Aragon & Fitschen 2014 recommend slower rates as leanness
  increases), shifted by the requested aggressiveness within the range.
- Muscle gain: surplus of 5-15 %; beginners get the smallest surplus (they
  build muscle with little extra energy), the range grows with experience.
- Recomposition: 0-8 % deficit with high protein; only offered to beginners,
  people returning after a break, or high body fat (Barakat et al. 2020).
- Maintenance: 0 %. Performance: small 5 % surplus to fuel training.
- Expected weekly change assumes 7700 kcal per kg of body fat (Wishnofsky 1958;
  a rough guide, which is why the adjustment engine re-estimates it later).
"""

from __future__ import annotations

import math
from datetime import date

from app.engine import safety
from app.engine.enums import Aggressiveness, Goal, Sex, TrainingExperience
from app.engine.tdee import expenditure_at_intake, solve_intake
from app.engine.types import (
    BmrEstimate,
    BodyComposition,
    CalorieTarget,
    EnergyExpenditure,
    Note,
    NutritionInputs,
)

KCAL_PER_KG_FAT = 7700
DEFICIT_MIN = 0.10
DEFICIT_MAX = 0.25
DEFICIT_DEFAULT_UNKNOWN_BF = 0.15
SURPLUS_MIN = 0.05
SURPLUS_MAX = 0.15
RECOMPOSITION_DEFICIT = 0.05
PERFORMANCE_SURPLUS = 0.05
AGGRESSIVENESS_SHIFT: dict[Aggressiveness, float] = {
    Aggressiveness.CONSERVATIVE: -0.05,
    Aggressiveness.MODERATE: 0.0,
    Aggressiveness.AGGRESSIVE: 0.05,
}
SURPLUS_AGGRESSIVENESS_SHIFT: dict[Aggressiveness, float] = {
    Aggressiveness.CONSERVATIVE: -0.025,
    Aggressiveness.MODERATE: 0.0,
    Aggressiveness.AGGRESSIVE: 0.025,
}
# Body fat where the deficit range starts (lean) and ends (high), per sex.
LEAN_BODY_FAT: dict[Sex, float] = {Sex.MALE: 12.0, Sex.FEMALE: 20.0}
HIGH_BODY_FAT: dict[Sex, float] = {Sex.MALE: 30.0, Sex.FEMALE: 38.0}
# Body fat above which recomposition works well even for experienced people.
RECOMPOSITION_BODY_FAT: dict[Sex, float] = {Sex.MALE: 25.0, Sex.FEMALE: 33.0}
SURPLUS_BY_EXPERIENCE: dict[TrainingExperience, float] = {
    TrainingExperience.NONE: 0.05,
    TrainingExperience.UNDER_6_MONTHS: 0.05,
    TrainingExperience.MONTHS_6_TO_24: 0.075,
    TrainingExperience.YEARS_2_TO_5: 0.10,
    TrainingExperience.OVER_5_YEARS: 0.10,
}
RECOMPOSITION_EXPERIENCE = {
    TrainingExperience.NONE,
    TrainingExperience.UNDER_6_MONTHS,
    TrainingExperience.MONTHS_6_TO_24,
}
DEFICIT_GOALS = {Goal.FAT_LOSS, Goal.RECOMPOSITION}


def deficit_fraction(sex: Sex, body_fat_pct: float | None, aggressiveness: Aggressiveness) -> float:
    """Deficit as a fraction of expenditure, scaled by body fat and shifted by aggressiveness."""
    if body_fat_pct is None:
        base = DEFICIT_DEFAULT_UNKNOWN_BF
    else:
        lean, high = LEAN_BODY_FAT[sex], HIGH_BODY_FAT[sex]
        position = (body_fat_pct - lean) / (high - lean)
        position = min(1.0, max(0.0, position))
        base = DEFICIT_MIN + position * (DEFICIT_MAX - DEFICIT_MIN)
    shifted = base + AGGRESSIVENESS_SHIFT[aggressiveness]
    return round(min(DEFICIT_MAX, max(DEFICIT_MIN, shifted)), 3)


def surplus_fraction(experience: TrainingExperience, aggressiveness: Aggressiveness) -> float:
    """Surplus as a fraction of expenditure by experience, shifted by aggressiveness."""
    shifted = SURPLUS_BY_EXPERIENCE[experience] + SURPLUS_AGGRESSIVENESS_SHIFT[aggressiveness]
    return round(min(SURPLUS_MAX, max(SURPLUS_MIN, shifted)), 3)


def recomposition_eligible(
    sex: Sex, experience: TrainingExperience, body_fat_pct: float | None
) -> bool:
    """Recomposition suits beginners, returners and people with high body fat."""
    if experience in RECOMPOSITION_EXPERIENCE:
        return True
    return body_fat_pct is not None and body_fat_pct >= RECOMPOSITION_BODY_FAT[sex]


def weekly_change_kg(daily_balance_kcal: float) -> float:
    """Expected weekly weight change from a daily energy balance (7700 kcal/kg)."""
    return daily_balance_kcal * 7 / KCAL_PER_KG_FAT


def calorie_target(
    inputs: NutritionInputs,
    body: BodyComposition,
    bmr: BmrEstimate,
    expenditure: EnergyExpenditure,
) -> CalorieTarget:
    """Daily calorie goal for the user's goal, already clamped by the safety limits."""
    notes: list[Note] = []
    goal = inputs.goal
    if goal is Goal.FAT_LOSS:
        mode, fraction = (
            "deficit",
            deficit_fraction(inputs.sex, body.body_fat_pct, inputs.aggressiveness),
        )
        ratio = 1 - fraction
    elif goal is Goal.RECOMPOSITION:
        if recomposition_eligible(inputs.sex, inputs.training_experience, body.body_fat_pct):
            mode, fraction, ratio = "deficit", RECOMPOSITION_DEFICIT, 1 - RECOMPOSITION_DEFICIT
        else:
            mode, fraction, ratio = "maintenance", 0.0, 1.0
            notes.append(Note("target.recomposition_not_ideal", level="warning"))
    elif goal is Goal.MUSCLE_GAIN:
        mode, fraction = (
            "surplus",
            surplus_fraction(inputs.training_experience, inputs.aggressiveness),
        )
        ratio = 1 + fraction
    elif goal is Goal.PERFORMANCE:
        mode, fraction, ratio = "surplus", PERFORMANCE_SURPLUS, 1 + PERFORMANCE_SURPLUS
    else:
        mode, fraction, ratio = "maintenance", 0.0, 1.0

    intake = solve_intake(expenditure.base_kcal, ratio)
    notes.append(Note(f"target.{mode}", params={"pct": round(fraction * 100, 1)}))

    floor = safety.calorie_floor(inputs.sex, bmr.selected_kcal)
    if intake < floor:
        notes.append(
            Note("target.raised_to_floor", level="warning", params={"floor": round(floor)})
        )
        intake = floor

    if mode == "deficit":
        max_loss = safety.max_weekly_loss_kg(body.weight_kg)
        max_daily_deficit = max_loss * KCAL_PER_KG_FAT / 7
        spent = expenditure_at_intake(expenditure.base_kcal, intake)
        if spent - intake > max_daily_deficit:
            intake = _intake_for_daily_deficit(expenditure.base_kcal, max_daily_deficit)
            notes.append(
                Note(
                    "target.capped_by_max_loss",
                    level="warning",
                    params={"max_weekly_kg": round(max_loss, 2)},
                )
            )

    target_kcal = _round_to(intake, 5)
    if target_kcal < floor:
        target_kcal = int(math.ceil(floor / 5) * 5)
    spent = expenditure_at_intake(expenditure.base_kcal, target_kcal)
    balance = target_kcal - spent
    return CalorieTarget(
        goal=goal,
        mode=mode,
        fraction=fraction,
        maintenance_kcal=expenditure.maintenance_kcal,
        target_kcal=target_kcal,
        expenditure_at_target_kcal=round(spent),
        daily_balance_kcal=round(balance),
        expected_weekly_change_kg=round(weekly_change_kg(balance), 2),
        notes=tuple(notes),
    )


def with_calories(
    target: CalorieTarget, calories: int, expenditure: EnergyExpenditure
) -> CalorieTarget:
    """Copy of ``target`` with a different intake (the macro stage may raise it)."""
    spent = expenditure_at_intake(expenditure.base_kcal, calories)
    balance = calories - spent
    return CalorieTarget(
        goal=target.goal,
        mode=target.mode,
        fraction=target.fraction,
        maintenance_kcal=target.maintenance_kcal,
        target_kcal=calories,
        expenditure_at_target_kcal=round(spent),
        daily_balance_kcal=round(balance),
        expected_weekly_change_kg=round(weekly_change_kg(balance), 2),
        notes=target.notes,
    )


def target_date_feasibility(inputs: NutritionInputs, target: CalorieTarget) -> Note | None:
    """Compare the requested date with the planned rate; warn when unrealistic."""
    if inputs.target_weight_kg is None or inputs.target_date is None:
        return None
    weeks = (inputs.target_date - inputs.today).days / 7
    change_needed = inputs.target_weight_kg - inputs.weight_kg
    if weeks <= 0:
        return Note("target.date_in_past", level="warning")
    if abs(change_needed) < 0.5 or target.expected_weekly_change_kg == 0:
        return None
    if (change_needed < 0) != (target.expected_weekly_change_kg < 0):
        return Note("target.date_direction_mismatch", level="warning")
    weeks_needed = abs(change_needed) / abs(target.expected_weekly_change_kg)
    realistic_date = date.fromordinal(inputs.today.toordinal() + round(weeks_needed * 7))
    params = {
        "weeks_available": round(weeks, 1),
        "weeks_needed": round(weeks_needed, 1),
        "realistic_date": realistic_date.isoformat(),
    }
    if weeks_needed > weeks * 1.1:
        return Note("target.date_unrealistic", level="warning", params=params)
    return Note("target.date_realistic", params=params)


def _intake_for_daily_deficit(base_kcal: float, daily_deficit: float) -> float:
    """Intake I such that (base + 0.1 I) - I = daily_deficit."""
    return (base_kcal - daily_deficit) / 0.9


def _round_to(value: float, step: int) -> int:
    return int(round(value / step) * step)
