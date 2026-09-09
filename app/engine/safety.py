"""Hard limits the engine can never cross, and the final gate before a plan is returned.

Two roles:

1. ``evaluate_eligibility`` runs first: minors, pregnancy or breastfeeding and a
   declared eating disorder stop the whole flow; underweight (BMI < 18.5) or a
   body fat at essential levels stop any deficit (only maintenance, gain and
   the training module remain available).
2. ``verify_plan`` runs last, on the finished numbers: calorie floors (never
   below the BMR, never below 1500 kcal for men or 1200 kcal for women), the
   maximum loss of 1 % of body weight per week, no deficit while underweight,
   and basic macro sanity. Any violation means a bug upstream, so the
   orchestrator raises ``SafetyError`` instead of returning the plan.

The limits are also used by ``targets.py`` while computing, so a valid plan is
produced in one pass; the gate is the guarantee, not the mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.engine.enums import Goal, Sex
from app.engine.types import (
    BmrEstimate,
    BodyComposition,
    CalorieTarget,
    Macros,
    Note,
    NutritionInputs,
)

MIN_AGE = 18
ABSOLUTE_CALORIE_FLOOR: dict[Sex, int] = {Sex.MALE: 1500, Sex.FEMALE: 1200}
MAX_WEEKLY_LOSS_FRACTION = 0.01
UNDERWEIGHT_BMI = 18.5
# Essential fat (ACSM): about 3-5 % men, 10-13 % women; below these the goal is incoherent.
ESSENTIAL_BODY_FAT: dict[Sex, float] = {Sex.MALE: 6.0, Sex.FEMALE: 14.0}
MIN_PROTEIN_PER_KG = 0.8
MAX_PROTEIN_PER_KG = 3.5
MIN_FAT_FRACTION = 0.15
DEFICIT_GOALS = {Goal.FAT_LOSS, Goal.RECOMPOSITION}
KCAL_TOLERANCE = 40


class SafetyError(RuntimeError):
    """A finished plan violates a hard limit (programming error upstream)."""

    def __init__(self, violations: tuple[Note, ...]) -> None:
        super().__init__("; ".join(note.code for note in violations))
        self.violations = violations


@dataclass(frozen=True)
class Eligibility:
    """Whether a plan may be produced at all, and whether a deficit is allowed."""

    allowed: bool
    allow_deficit: bool
    reasons: tuple[Note, ...] = ()


def calorie_floor(sex: Sex, bmr_kcal: float) -> float:
    """Lowest intake ever prescribed: the larger of the BMR and the absolute floor."""
    return max(float(bmr_kcal), float(ABSOLUTE_CALORIE_FLOOR[sex]))


def max_weekly_loss_kg(weight_kg: float) -> float:
    """1 % of body weight per week."""
    return weight_kg * MAX_WEEKLY_LOSS_FRACTION


def evaluate_eligibility(inputs: NutritionInputs, body: BodyComposition) -> Eligibility:
    """Hard stops that depend only on the person, not on the numbers."""
    reasons: list[Note] = []
    allowed = True
    allow_deficit = True

    if inputs.age < MIN_AGE:
        allowed = False
        reasons.append(Note("safety.minor", level="error", params={"age": inputs.age}))
    if inputs.is_pregnant_or_breastfeeding:
        allowed = False
        reasons.append(Note("safety.pregnancy", level="error"))
    if inputs.has_eating_disorder_history:
        allowed = False
        reasons.append(Note("safety.eating_disorder", level="error"))

    if body.bmi < UNDERWEIGHT_BMI:
        allow_deficit = False
        reasons.append(Note("safety.underweight", level="error", params={"bmi": body.bmi}))
    if body.body_fat_pct is not None and body.body_fat_pct <= ESSENTIAL_BODY_FAT[inputs.sex]:
        allow_deficit = False
        reasons.append(
            Note("safety.essential_fat", level="error", params={"body_fat": body.body_fat_pct})
        )
    return Eligibility(allowed=allowed, allow_deficit=allow_deficit, reasons=tuple(reasons))


def deficit_blocked(inputs: NutritionInputs, eligibility: Eligibility) -> bool:
    """A deficit goal with a deficit ban means the plan cannot be produced."""
    return inputs.goal in DEFICIT_GOALS and not eligibility.allow_deficit


def verify_plan(
    inputs: NutritionInputs,
    body: BodyComposition,
    bmr: BmrEstimate,
    target: CalorieTarget,
    macros: Macros,
) -> tuple[Note, ...]:
    """Check every hard limit on the finished numbers; empty tuple means the plan is safe."""
    violations: list[Note] = []
    calories = macros.calories
    floor = calorie_floor(inputs.sex, bmr.selected_kcal)
    if calories < floor:
        violations.append(
            Note("safety.below_floor", level="error", params={"calories": calories, "floor": floor})
        )

    max_loss = max_weekly_loss_kg(body.weight_kg)
    if -target.expected_weekly_change_kg > max_loss + 0.01:
        violations.append(
            Note(
                "safety.loss_too_fast",
                level="error",
                params={"weekly": target.expected_weekly_change_kg, "max": max_loss},
            )
        )

    if body.bmi < UNDERWEIGHT_BMI and target.daily_balance_kcal < -KCAL_TOLERANCE:
        violations.append(Note("safety.deficit_while_underweight", level="error"))

    per_kg = macros.protein_g / body.weight_kg
    if not MIN_PROTEIN_PER_KG <= per_kg <= MAX_PROTEIN_PER_KG:
        violations.append(
            Note("safety.protein_out_of_range", level="error", params={"per_kg": round(per_kg, 2)})
        )

    if macros.fat_g * 9 < MIN_FAT_FRACTION * calories:
        violations.append(Note("safety.fat_too_low", level="error", params={"fat_g": macros.fat_g}))

    if macros.carbs_g < 0 or macros.protein_g <= 0 or macros.fat_g <= 0:
        violations.append(Note("safety.negative_macro", level="error"))

    energy = 4 * macros.protein_g + 4 * macros.carbs_g + 9 * macros.fat_g
    if abs(energy - calories) > KCAL_TOLERANCE:
        violations.append(
            Note(
                "safety.macros_mismatch",
                level="error",
                params={"energy": energy, "calories": calories},
            )
        )

    return tuple(violations)
