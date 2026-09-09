"""Body composition: body-fat percentage, BMI, lean mass and confidence.

Sources:
- Hodgdon, J. A. & Beckett, M. B. (1984). *Prediction of percent body fat for
  U.S. Navy men/women from body circumferences and height*. Naval Health
  Research Center reports 84-11 and 84-29 (the "Navy method").
- WHO (2000). *Obesity: preventing and managing the global epidemic*: BMI.
"""

from __future__ import annotations

import math

from app.engine.enums import BodyFatMethod, Confidence, Sex
from app.engine.types import BodyComposition, Note, NutritionInputs

NAVY_MIN_BF = 2.0
NAVY_MAX_BF = 70.0

# How much to trust a body-fat figure by the method that produced it.
METHOD_CONFIDENCE: dict[BodyFatMethod, Confidence] = {
    BodyFatMethod.DEXA: Confidence.HIGH,
    BodyFatMethod.CALIPERS: Confidence.MEDIUM,
    BodyFatMethod.NAVY: Confidence.MEDIUM,
    BodyFatMethod.SCALE: Confidence.MEDIUM,
    BodyFatMethod.VISUAL: Confidence.LOW,
    BodyFatMethod.NONE: Confidence.LOW,
}


def bmi(weight_kg: float, height_cm: float) -> float:
    """Body mass index: kg / m^2."""
    metres = height_cm / 100
    return weight_kg / (metres * metres)


def lean_body_mass(weight_kg: float, body_fat_pct: float) -> float:
    """Lean body mass: weight x (1 - body fat fraction)."""
    return weight_kg * (1 - body_fat_pct / 100)


def navy_body_fat(
    sex: Sex,
    height_cm: float,
    neck_cm: float,
    waist_cm: float,
    hip_cm: float | None = None,
) -> float | None:
    """Body-fat percentage from circumferences (US Navy method, centimetres).

    Men:   495 / (1.0324 - 0.19077 * log10(waist - neck) + 0.15456 * log10(height)) - 450
    Women: 495 / (1.29579 - 0.35004 * log10(waist + hip - neck) + 0.22100 * log10(height)) - 450

    Returns ``None`` when the measurements are geometrically impossible
    (waist not larger than neck) or the result falls outside 2-70 %.
    """
    if sex is Sex.MALE:
        girth = waist_cm - neck_cm
        if girth <= 0:
            return None
        denominator = 1.0324 - 0.19077 * math.log10(girth) + 0.15456 * math.log10(height_cm)
    else:
        if hip_cm is None:
            return None
        girth = waist_cm + hip_cm - neck_cm
        if girth <= 0:
            return None
        denominator = 1.29579 - 0.35004 * math.log10(girth) + 0.22100 * math.log10(height_cm)
    if denominator <= 0:  # pragma: no cover - unreachable within the validated input ranges
        return None
    value = 495 / denominator - 450
    if not NAVY_MIN_BF <= value <= NAVY_MAX_BF:
        return None
    return round(value, 1)


def assess_body_composition(inputs: NutritionInputs) -> BodyComposition:
    """Pick the best available body-fat figure and derive lean mass and confidence.

    Priority: a declared percentage (with its method) > Navy estimate from
    circumferences > nothing (low confidence, the BMR falls back to Mifflin-St Jeor).
    """
    notes: list[Note] = []
    body_fat: float | None = None
    source = BodyFatMethod.NONE

    if inputs.body_fat_pct is not None:
        body_fat = float(inputs.body_fat_pct)
        source = inputs.body_fat_method
        notes.append(Note("body_fat.declared", params={"method": source.value, "value": body_fat}))
    elif inputs.neck_cm is not None and inputs.waist_cm is not None:
        estimate = navy_body_fat(
            inputs.sex, inputs.height_cm, inputs.neck_cm, inputs.waist_cm, inputs.hip_cm
        )
        if estimate is None:
            notes.append(Note("body_fat.navy_invalid", level="warning"))
        else:
            body_fat = estimate
            source = BodyFatMethod.NAVY
            notes.append(Note("body_fat.navy", params={"value": estimate}))
    else:
        notes.append(Note("body_fat.unknown", level="warning"))

    lean = lean_body_mass(inputs.weight_kg, body_fat) if body_fat is not None else None
    return BodyComposition(
        weight_kg=inputs.weight_kg,
        height_cm=inputs.height_cm,
        bmi=round(bmi(inputs.weight_kg, inputs.height_cm), 1),
        body_fat_pct=body_fat,
        body_fat_source=source,
        lean_mass_kg=round(lean, 1) if lean is not None else None,
        confidence=METHOD_CONFIDENCE[source],
        notes=tuple(notes),
    )
