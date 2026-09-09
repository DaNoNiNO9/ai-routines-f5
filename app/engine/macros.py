"""Macronutrients, fibre, water and carb cycling.

Sources:
- Morton, R. W. et al. (2018). *A systematic review, meta-analysis and
  meta-regression of the effect of protein supplementation on resistance
  training-induced gains*. Br J Sports Med 52:376-384: ~1.6 g/kg, upper
  confidence limit 2.2 g/kg.
- Helms, E. R., Aragon, A. A. & Fitschen, P. J. (2014). *Evidence-based
  recommendations for natural bodybuilding contest preparation*. JISSN 11:20:
  2.3-3.1 g/kg of fat-free mass in a deficit, fat 15-30 % of calories.
- Institute of Medicine (2005). *Dietary Reference Intakes*: fibre 14 g per
  1000 kcal.
- EFSA (2010) and common sports-nutrition practice: 30-40 mL water per kg
  plus extra around training.

Carbohydrates take what remains. When they fall below a functional floor the
engine first lowers fat towards its minimum and then, in a deficit, reduces the
deficit itself (raises calories): carbohydrates never go to zero.
"""

from __future__ import annotations

import math

from app.engine.enums import Confidence, Goal, Sex, TrainingExperience
from app.engine.types import (
    BodyComposition,
    CarbCycle,
    DayMacros,
    Hydration,
    Macros,
    Note,
    NutritionInputs,
)

PROTEIN_PER_KG_BY_GOAL: dict[Goal, float] = {
    Goal.FAT_LOSS: 2.0,
    Goal.RECOMPOSITION: 2.2,
    Goal.MUSCLE_GAIN: 1.8,
    Goal.MAINTENANCE: 1.6,
    Goal.PERFORMANCE: 1.8,
}
PROTEIN_MIN_PER_KG = 1.6
PROTEIN_MAX_PER_KG = 2.2
PROTEIN_ADVANCED_BONUS = 0.2
PROTEIN_AGGRESSIVE_DEFICIT_BONUS = 0.2
PROTEIN_PER_KG_LEAN_DEFICIT = 2.6
PROTEIN_PER_KG_LEAN_OTHER = 2.3
PROTEIN_FLOOR_PER_KG = 0.8
LEAN_BASIS_BODY_FAT: dict[Sex, float] = {Sex.MALE: 25.0, Sex.FEMALE: 32.0}
ADVANCED = {TrainingExperience.YEARS_2_TO_5, TrainingExperience.OVER_5_YEARS}

FAT_MIN_PER_KG = 0.6
FAT_TARGET_PER_KG = 0.8
FAT_MIN_FRACTION = 0.20
FAT_MAX_FRACTION = 0.35

CARB_FLOOR_MIN_G = 100.0
FIBER_PER_1000_KCAL = 14.0
WATER_ML_PER_KG = 35
WATER_PER_SESSION_ML = 500
WATER_EXTRA_PER_30_MIN_ML = 250
CARB_CYCLE_HIGH_FACTOR = 1.25
MAX_FLOOR_ITERATIONS = 6


def protein_target(
    inputs: NutritionInputs, body: BodyComposition, mode: str
) -> tuple[float, float, str]:
    """Daily protein in grams, plus the g/kg used and the basis (``bodyweight`` or ``lean``).

    Lean-mass basis is used when body fat is known with at least medium confidence
    and is high, because bodyweight-based targets overshoot in that case.
    """
    lean_basis = (
        body.lean_mass_kg is not None
        and body.body_fat_pct is not None
        and body.confidence is not Confidence.LOW
        and body.body_fat_pct >= LEAN_BASIS_BODY_FAT[inputs.sex]
    )
    if lean_basis and body.lean_mass_kg is not None:
        per_kg_lean = (
            PROTEIN_PER_KG_LEAN_DEFICIT if mode == "deficit" else PROTEIN_PER_KG_LEAN_OTHER
        )
        grams = max(body.lean_mass_kg * per_kg_lean, PROTEIN_FLOOR_PER_KG * body.weight_kg)
        return grams, round(grams / body.weight_kg, 2), "lean"

    per_kg = PROTEIN_PER_KG_BY_GOAL[inputs.goal]
    if inputs.training_experience in ADVANCED:
        per_kg += PROTEIN_ADVANCED_BONUS
    if mode == "deficit" and inputs.aggressiveness.value == "aggressive":
        per_kg += PROTEIN_AGGRESSIVE_DEFICIT_BONUS
    per_kg = min(PROTEIN_MAX_PER_KG, max(PROTEIN_MIN_PER_KG, per_kg))
    return body.weight_kg * per_kg, round(per_kg, 2), "bodyweight"


def fat_target_g(calories: float, weight_kg: float) -> float:
    """0.8 g/kg, kept between 20 % and 35 % of calories."""
    grams = FAT_TARGET_PER_KG * weight_kg
    low = FAT_MIN_FRACTION * calories / 9
    high = FAT_MAX_FRACTION * calories / 9
    return min(high, max(low, grams))


def fat_minimum_g(calories: float, weight_kg: float) -> float:
    """Never below 0.6 g/kg nor below 20 % of calories (hormonal health)."""
    return max(FAT_MIN_PER_KG * weight_kg, FAT_MIN_FRACTION * calories / 9)


def carb_floor_g(weight_kg: float, training_days: int) -> float:
    """Functional carbohydrate floor: 1-2 g/kg by training frequency, never under 100 g."""
    if training_days >= 5:
        per_kg = 2.0
    elif training_days >= 3:
        per_kg = 1.5
    else:
        per_kg = 1.0
    return max(CARB_FLOOR_MIN_G, per_kg * weight_kg)


def compute_macros(
    inputs: NutritionInputs, body: BodyComposition, target_kcal: int, mode: str
) -> Macros:
    """Split the calories into protein, fat and carbohydrates, enforcing the carb floor."""
    notes: list[Note] = []
    protein, per_kg, basis = protein_target(inputs, body, mode)
    if basis == "lean":
        notes.append(Note("macros.protein_lean_basis", params={"per_kg": per_kg}))

    calories = float(target_kcal)
    fat = fat_target_g(calories, body.weight_kg)
    floor = carb_floor_g(body.weight_kg, inputs.training_days_per_week)
    carbs = _carbs_for(calories, protein, fat)

    if carbs < floor:
        fat = min(fat, fat_minimum_g(calories, body.weight_kg))
        carbs = _carbs_for(calories, protein, fat)
        notes.append(Note("macros.fat_lowered_for_carbs", params={"floor": round(floor)}))

    added = 0.0
    for _ in range(MAX_FLOOR_ITERATIONS):
        if carbs >= floor:
            break
        needed = 4 * protein + 9 * fat + 4 * floor
        added += needed - calories
        calories = needed
        fat = max(fat, fat_minimum_g(calories, body.weight_kg))
        carbs = _carbs_for(calories, protein, fat)
    protein_g = math.ceil(protein - 1e-9)
    fat_g = round(fat)
    floor_g = round(floor)
    calories_int = int(math.ceil(calories / 5) * 5) if added > 0 else int(round(calories / 5) * 5)
    carbs_g = max(0, round(_carbs_for(calories_int, protein_g, fat_g)))
    # Rounding protein up, fat to the nearest gram and calories to 5 kcal can
    # leave the carbs a gram or two under the floor: 5 kcal steps restore it.
    while carbs_g < floor_g:
        calories_int += 5
        added += 5
        carbs_g = max(0, round(_carbs_for(calories_int, protein_g, fat_g)))
    if added > 0:
        code = (
            "macros.deficit_reduced_for_carbs"
            if mode == "deficit"
            else "macros.calories_raised_for_carbs"
        )
        notes.append(Note(code, level="warning", params={"kcal": round(added), "floor": floor_g}))
    return Macros(
        calories=calories_int,
        protein_g=protein_g,
        fat_g=fat_g,
        carbs_g=carbs_g,
        fiber_g=round(FIBER_PER_1000_KCAL * calories_int / 1000),
        protein_per_kg=per_kg,
        protein_basis=basis,
        fat_fraction=round(9 * fat_g / calories_int, 3),
        carb_floor_g=floor_g,
        calories_added_for_carb_floor=round(added),
        notes=tuple(notes),
    )


def hydration(weight_kg: float, session_minutes: int) -> Hydration:
    """35 mL/kg baseline; 500 mL per session plus 250 mL per extra half hour beyond 60 min."""
    base = round(WATER_ML_PER_KG * weight_kg)
    per_session = 0
    if session_minutes > 0:
        extra_blocks = max(0, (session_minutes - 60 + 29) // 30)
        per_session = WATER_PER_SESSION_ML + WATER_EXTRA_PER_30_MIN_ML * extra_blocks
    return Hydration(base_ml=base, per_session_ml=per_session, training_day_ml=base + per_session)


def carb_cycle(macros: Macros, training_days: int) -> CarbCycle | None:
    """High-carb training days and low-carb rest days averaging the base carbs over the week.

    Protein and fat stay constant; calories differ between day types. The low
    day never goes under the carb floor (the high-day bump shrinks instead).
    Returns ``None`` when every day (or no day) is a training day.
    """
    rest_days = 7 - training_days
    if training_days <= 0 or rest_days <= 0:
        return None
    notes: list[Note] = []
    base = macros.carbs_g
    high = round(base * CARB_CYCLE_HIGH_FACTOR)
    low = round((7 * base - training_days * high) / rest_days)
    if low < macros.carb_floor_g:
        low = macros.carb_floor_g
        high = round((7 * base - rest_days * low) / training_days)
        notes.append(Note("cycle.low_day_at_floor", params={"floor": macros.carb_floor_g}))
    average = (training_days * high + rest_days * low) / 7
    notes.append(Note("cycle.enabled", params={"high": high, "low": low}))
    return CarbCycle(
        training_days=training_days,
        rest_days=rest_days,
        high_day=_day("training", macros, high),
        low_day=_day("rest", macros, low),
        weekly_average_carbs_g=round(average, 1),
        notes=tuple(notes),
    )


def _day(label: str, macros: Macros, carbs: int) -> DayMacros:
    calories = 4 * macros.protein_g + 4 * carbs + 9 * macros.fat_g
    return DayMacros(
        label=label,
        calories=calories,
        protein_g=macros.protein_g,
        carbs_g=carbs,
        fat_g=macros.fat_g,
    )


def _carbs_for(calories: float, protein_g: float, fat_g: float) -> float:
    return (calories - 4 * protein_g - 9 * fat_g) / 4
