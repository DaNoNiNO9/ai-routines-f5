"""Nutrition engine orchestrator.

    inputs -> body composition -> eligibility (hard stops) -> BMR -> TDEE by
    components -> calorie target (with safety limits) -> macros (carb floor may
    raise calories) -> meals -> carb cycling -> hydration -> final safety gate

Pure function: no Flask, no database. ``build_nutrition_plan`` either returns
a complete :class:`NutritionPlan`, a blocked plan with the reasons, or raises
:class:`SafetyError` when the finished numbers violate a hard limit (which
would be a bug in the pipeline, not a user error).
"""

from __future__ import annotations

from app.engine import safety
from app.engine.bmr import estimate_bmr
from app.engine.body_composition import assess_body_composition
from app.engine.enums import Confidence
from app.engine.macros import carb_cycle, compute_macros, hydration
from app.engine.meals import distribute_meals
from app.engine.targets import calorie_target, target_date_feasibility, with_calories
from app.engine.tdee import estimate_expenditure, expenditure_confidence
from app.engine.types import Note, NutritionInputs, NutritionPlan


def build_nutrition_plan(inputs: NutritionInputs) -> NutritionPlan:
    """Run the whole nutrition pipeline for ``inputs``."""
    body = assess_body_composition(inputs)
    eligibility = safety.evaluate_eligibility(inputs, body)

    if not eligibility.allowed:
        return NutritionPlan(
            status="blocked",
            confidence=body.confidence,
            body=body,
            blocked_reasons=eligibility.reasons,
        )
    if safety.deficit_blocked(inputs, eligibility):
        reasons = (*eligibility.reasons, Note("safety.deficit_blocked", level="error"))
        return NutritionPlan(
            status="blocked", confidence=body.confidence, body=body, blocked_reasons=reasons
        )

    bmr = estimate_bmr(inputs, body)
    expenditure = estimate_expenditure(inputs, body, bmr)
    target = calorie_target(inputs, body, bmr, expenditure)
    macros = compute_macros(inputs, body, target.target_kcal, target.mode)
    if macros.calories != target.target_kcal:
        target = with_calories(target, macros.calories, expenditure)

    meals, meal_notes = distribute_meals(
        macros, inputs.meals_per_day, inputs.training_time, body.weight_kg
    )
    cycle = carb_cycle(macros, inputs.training_days_per_week) if inputs.wants_carb_cycling else None
    water = hydration(
        body.weight_kg, inputs.session_minutes if inputs.training_days_per_week else 0
    )

    notes: list[Note] = list(meal_notes)
    for reason in eligibility.reasons:
        notes.append(Note(reason.code, level="warning", params=reason.params))
    date_note = target_date_feasibility(inputs, target)
    if date_note is not None:
        notes.append(date_note)
    confidence = expenditure_confidence(expenditure, body)
    notes.append(Note("plan.confidence", params={"confidence": confidence.value}))

    violations = safety.verify_plan(inputs, body, bmr, target, macros)
    if violations:
        raise safety.SafetyError(violations)

    return NutritionPlan(
        status="ok",
        confidence=confidence,
        body=body,
        bmr=bmr,
        expenditure=expenditure,
        target=target,
        macros=macros,
        hydration=water,
        meals=meals,
        carb_cycle=cycle,
        notes=tuple(notes),
    )


def confidence_label(confidence: Confidence) -> str:
    """Stable string for templates and JSON (kept here so the UI does not import enums)."""
    return confidence.value
