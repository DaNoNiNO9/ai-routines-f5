"""Basal metabolic rate: three formulas, one selected, the range always shown.

Sources:
- Katch, F. I. & McArdle, W. D. (1996). *Exercise Physiology*: BMR = 370 + 21.6 x LBM.
- Mifflin, M. D. et al. (1990). *A new predictive equation for resting energy
  expenditure in healthy individuals*. Am J Clin Nutr 51(2):241-247.
- Roza, A. M. & Shizgal, H. M. (1984). *The Harris Benedict equation
  reevaluated*. Am J Clin Nutr 40(1):168-182 (revised Harris-Benedict).
"""

from __future__ import annotations

from app.engine.enums import BmrMethod, Sex
from app.engine.types import BmrEstimate, BodyComposition, Note, NutritionInputs


def katch_mcardle(lean_mass_kg: float) -> float:
    """370 + 21.6 x lean body mass (kg)."""
    return 370 + 21.6 * lean_mass_kg


def mifflin_st_jeor(sex: Sex, weight_kg: float, height_cm: float, age: int) -> float:
    """10 x kg + 6.25 x cm - 5 x age + 5 (men) or - 161 (women)."""
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + 5 if sex is Sex.MALE else base - 161


def harris_benedict(sex: Sex, weight_kg: float, height_cm: float, age: int) -> float:
    """Revised Harris-Benedict (Roza & Shizgal 1984)."""
    if sex is Sex.MALE:
        return 88.362 + 13.397 * weight_kg + 4.799 * height_cm - 5.677 * age
    return 447.593 + 9.247 * weight_kg + 3.098 * height_cm - 4.330 * age


def estimate_bmr(inputs: NutritionInputs, body: BodyComposition) -> BmrEstimate:
    """Compute every applicable formula and select one.

    Katch-McArdle is used whenever a body-fat figure exists (declared or Navy),
    because it accounts for lean mass; otherwise Mifflin-St Jeor, the most
    accurate equation for the general population. Harris-Benedict is kept only
    to show the range.
    """
    estimates: dict[BmrMethod, float] = {
        BmrMethod.MIFFLIN_ST_JEOR: mifflin_st_jeor(
            inputs.sex, inputs.weight_kg, inputs.height_cm, inputs.age
        ),
        BmrMethod.HARRIS_BENEDICT: harris_benedict(
            inputs.sex, inputs.weight_kg, inputs.height_cm, inputs.age
        ),
    }
    notes: list[Note] = []
    if body.lean_mass_kg is not None:
        estimates[BmrMethod.KATCH_MCARDLE] = katch_mcardle(body.lean_mass_kg)
        method = BmrMethod.KATCH_MCARDLE
        notes.append(Note("bmr.katch_mcardle", params={"lean_mass_kg": body.lean_mass_kg}))
    else:
        method = BmrMethod.MIFFLIN_ST_JEOR
        notes.append(Note("bmr.mifflin"))

    rounded = {key: round(value) for key, value in estimates.items()}
    return BmrEstimate(
        selected_kcal=rounded[method],
        method=method,
        estimates=rounded,
        low_kcal=min(rounded.values()),
        high_kcal=max(rounded.values()),
        notes=tuple(notes),
    )
