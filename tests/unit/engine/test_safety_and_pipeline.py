"""Safety limits, the final gate and the whole nutrition pipeline (incl. property tests)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.engine import safety
from app.engine.bmr import estimate_bmr
from app.engine.body_composition import assess_body_composition
from app.engine.enums import (
    ActivityIntensity,
    Aggressiveness,
    BodyFatMethod,
    Confidence,
    Goal,
    JobActivity,
    Sex,
    TrainingExperience,
    TrainingTime,
)
from app.engine.messages import render, render_all
from app.engine.nutrition import build_nutrition_plan, confidence_label
from app.engine.types import CalorieTarget, Macros, Note, NutritionInputs, NutritionPlan, _jsonable
from tests.engine_factories import make_female_inputs, make_inputs


def test_calorie_floor_and_max_loss() -> None:
    assert safety.calorie_floor(Sex.MALE, 1400) == 1500
    assert safety.calorie_floor(Sex.FEMALE, 1000) == 1200
    assert safety.calorie_floor(Sex.FEMALE, 1450) == 1450
    assert safety.max_weekly_loss_kg(80) == pytest.approx(0.8)


def test_eligibility_hard_stops() -> None:
    body = assess_body_composition(make_inputs())
    assert safety.evaluate_eligibility(make_inputs(), body).allowed is True
    minor = safety.evaluate_eligibility(make_inputs(age=17), body)
    assert minor.allowed is False
    assert minor.reasons[0].code == "safety.minor"
    pregnant = safety.evaluate_eligibility(make_inputs(is_pregnant_or_breastfeeding=True), body)
    assert pregnant.reasons[0].code == "safety.pregnancy"
    disorder = safety.evaluate_eligibility(make_inputs(has_eating_disorder_history=True), body)
    assert disorder.reasons[0].code == "safety.eating_disorder"


def test_eligibility_blocks_deficit_when_underweight_or_at_essential_fat() -> None:
    thin = make_inputs(weight_kg=55, height_cm=180, neck_cm=None, waist_cm=None)
    verdict = safety.evaluate_eligibility(thin, assess_body_composition(thin))
    assert verdict.allowed is True
    assert verdict.allow_deficit is False
    assert verdict.reasons[0].code == "safety.underweight"
    assert safety.deficit_blocked(thin, verdict) is True
    assert safety.deficit_blocked(make_inputs(goal=Goal.MAINTENANCE), verdict) is False

    lean = make_inputs(body_fat_pct=5, body_fat_method=BodyFatMethod.DEXA)
    verdict = safety.evaluate_eligibility(lean, assess_body_composition(lean))
    assert verdict.allow_deficit is False
    assert verdict.reasons[0].code == "safety.essential_fat"


def _target(**values: Any) -> CalorieTarget:
    defaults: dict[str, Any] = {
        "goal": Goal.FAT_LOSS,
        "mode": "deficit",
        "fraction": 0.2,
        "maintenance_kcal": 2500,
        "target_kcal": 2000,
        "expenditure_at_target_kcal": 2450,
        "daily_balance_kcal": -450,
        "expected_weekly_change_kg": -0.41,
    }
    return CalorieTarget(**{**defaults, **values})


def _macros(**values: Any) -> Macros:
    defaults: dict[str, Any] = {
        "calories": 2000,
        "protein_g": 170,
        "fat_g": 68,
        "carbs_g": 177,
        "fiber_g": 28,
        "protein_per_kg": 2.0,
        "protein_basis": "bodyweight",
        "fat_fraction": 0.3,
        "carb_floor_g": 120,
        "calories_added_for_carb_floor": 0,
    }
    return Macros(**{**defaults, **values})


def test_verify_plan_accepts_a_consistent_plan_and_flags_each_violation() -> None:
    inputs = make_inputs()
    body = assess_body_composition(inputs)
    bmr = estimate_bmr(inputs, body)
    assert safety.verify_plan(inputs, body, bmr, _target(), _macros()) == ()

    below = safety.verify_plan(
        inputs, body, bmr, _target(target_kcal=1000), _macros(calories=1000, carbs_g=0, fat_g=10)
    )
    codes = {note.code for note in below}
    assert "safety.below_floor" in codes
    assert "safety.fat_too_low" in codes
    assert "safety.macros_mismatch" in codes

    fast = safety.verify_plan(inputs, body, bmr, _target(expected_weekly_change_kg=-1.5), _macros())
    assert {note.code for note in fast} == {"safety.loss_too_fast"}

    little = safety.verify_plan(inputs, body, bmr, _target(), _macros(protein_g=40, carbs_g=307))
    assert {note.code for note in little} == {"safety.protein_out_of_range"}

    negative = safety.verify_plan(inputs, body, bmr, _target(), _macros(carbs_g=-10, protein_g=0))
    assert "safety.negative_macro" in {note.code for note in negative}


def test_verify_plan_rejects_deficit_while_underweight() -> None:
    thin = make_inputs(
        weight_kg=55, height_cm=180, neck_cm=None, waist_cm=None, goal=Goal.MAINTENANCE
    )
    body = assess_body_composition(thin)
    bmr = estimate_bmr(thin, body)
    macros = _macros(calories=1600, protein_g=90, fat_g=55, carbs_g=186)
    target = _target(
        mode="maintenance",
        target_kcal=1600,
        daily_balance_kcal=-300,
        expected_weekly_change_kg=-0.27,
    )
    violations = safety.verify_plan(thin, body, bmr, target, macros)
    assert any(note.code == "safety.deficit_while_underweight" for note in violations)


def test_safety_error_lists_the_violations() -> None:
    error = safety.SafetyError(
        (Note("safety.below_floor", level="error"), Note("safety.fat_too_low"))
    )
    assert str(error) == "safety.below_floor; safety.fat_too_low"
    assert len(error.violations) == 2


def test_full_pipeline_fat_loss_profile() -> None:
    plan = build_nutrition_plan(make_inputs(wants_carb_cycling=True))
    assert plan.status == "ok"
    assert plan.is_blocked is False
    assert plan.confidence is Confidence.MEDIUM
    assert plan.target is not None
    assert plan.macros is not None
    assert plan.expenditure is not None
    assert plan.hydration is not None
    assert plan.target.target_kcal < plan.expenditure.maintenance_kcal
    assert plan.macros.calories == plan.target.target_kcal
    assert sum(slot.protein_g for slot in plan.meals) == plan.macros.protein_g
    assert sum(slot.carbs_g for slot in plan.meals) == plan.macros.carbs_g
    assert sum(slot.fat_g for slot in plan.meals) == plan.macros.fat_g
    assert plan.carb_cycle is not None
    assert plan.hydration.training_day_ml > plan.hydration.base_ml
    assert plan.notes[-1].code == "plan.confidence"
    assert plan.disclaimer is True
    serialised = json.dumps(plan.to_dict())
    assert '"status": "ok"' in serialised
    assert '"katch_mcardle"' in serialised
    codes = [note.code for note in plan.all_notes()]
    assert codes[0] == "body_fat.navy"
    assert "cycle.enabled" in codes


def test_full_pipeline_muscle_gain_female() -> None:
    plan = build_nutrition_plan(
        make_female_inputs(goal=Goal.MUSCLE_GAIN, training_time=TrainingTime.MORNING)
    )
    assert plan.status == "ok"
    assert plan.target is not None
    assert plan.expenditure is not None
    assert plan.target.mode == "surplus"
    assert plan.target.target_kcal > plan.expenditure.maintenance_kcal
    assert plan.meals[0].timing.value == "pre_workout"
    assert plan.carb_cycle is None


def test_full_pipeline_reports_target_date_feasibility() -> None:
    plan = build_nutrition_plan(make_inputs(target_weight_kg=80, target_date=date(2026, 10, 1)))
    assert plan.status == "ok"
    assert any(note.code == "target.date_unrealistic" for note in plan.notes)


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"age": 16}, "safety.minor"),
        ({"is_pregnant_or_breastfeeding": True}, "safety.pregnancy"),
        ({"has_eating_disorder_history": True}, "safety.eating_disorder"),
    ],
)
def test_pipeline_blocks_hard_stops(overrides: dict[str, Any], code: str) -> None:
    plan = build_nutrition_plan(make_inputs(**overrides))
    assert plan.is_blocked
    assert plan.blocked_reasons[0].code == code
    assert plan.target is None
    assert plan.meals == ()
    assert next(note.code for note in plan.all_notes()) == code


def test_pipeline_blocks_deficit_for_underweight_but_allows_maintenance() -> None:
    thin = make_inputs(weight_kg=55, height_cm=180, neck_cm=None, waist_cm=None)
    blocked = build_nutrition_plan(thin)
    assert blocked.is_blocked
    assert [note.code for note in blocked.blocked_reasons] == [
        "safety.underweight",
        "safety.deficit_blocked",
    ]

    keep = build_nutrition_plan(
        make_inputs(weight_kg=55, height_cm=180, neck_cm=None, waist_cm=None, goal=Goal.MAINTENANCE)
    )
    assert keep.status == "ok"
    assert keep.target is not None
    assert keep.target.daily_balance_kcal >= -safety.KCAL_TOLERANCE
    assert any(n.code == "safety.underweight" and n.level == "warning" for n in keep.notes)


def test_pipeline_blocks_fat_loss_at_essential_body_fat() -> None:
    plan = build_nutrition_plan(make_inputs(body_fat_pct=5, body_fat_method=BodyFatMethod.DEXA))
    assert plan.is_blocked
    assert plan.blocked_reasons[0].code == "safety.essential_fat"


EXTREME_PROFILES: list[dict[str, Any]] = [
    {
        "sex": Sex.FEMALE,
        "weight_kg": 40,
        "height_cm": 140,
        "age": 25,
        "neck_cm": 30,
        "waist_cm": 60,
        "hip_cm": 80,
    },
    {
        "weight_kg": 200,
        "height_cm": 210,
        "age": 85,
        "body_fat_pct": 60,
        "body_fat_method": BodyFatMethod.SCALE,
    },
    {"weight_kg": 200, "height_cm": 160, "age": 40, "neck_cm": 50, "waist_cm": 150},
    {"training_days_per_week": 2, "session_minutes": 20},
    {"training_days_per_week": 6, "session_minutes": 120, "daily_steps": 15000},
    {"goal": Goal.PERFORMANCE, "training_experience": TrainingExperience.OVER_5_YEARS},
    {"goal": Goal.RECOMPOSITION, "training_experience": TrainingExperience.NONE},
    {"meals_per_day": 8, "training_time": TrainingTime.MIDDAY},
    {
        "meals_per_day": 1,
        "training_time": TrainingTime.NONE,
        "training_days_per_week": 0,
        "session_minutes": 0,
    },
]


@pytest.mark.parametrize("overrides", EXTREME_PROFILES)
def test_pipeline_extreme_profiles_never_break_the_limits(overrides: dict[str, Any]) -> None:
    inputs = make_inputs(**overrides)
    plan = build_nutrition_plan(inputs)
    assert plan.status == "ok"
    _assert_invariants(inputs, plan)


def _assert_invariants(inputs: NutritionInputs, plan: NutritionPlan) -> None:
    assert plan.target is not None
    assert plan.macros is not None
    assert plan.bmr is not None
    assert plan.macros.calories >= safety.calorie_floor(inputs.sex, plan.bmr.selected_kcal)
    assert -plan.target.expected_weekly_change_kg <= 0.01 * plan.body.weight_kg + 0.01
    energy = 4 * plan.macros.protein_g + 4 * plan.macros.carbs_g + 9 * plan.macros.fat_g
    assert abs(energy - plan.macros.calories) <= safety.KCAL_TOLERANCE
    assert plan.macros.carbs_g >= plan.macros.carb_floor_g - 1
    assert sum(slot.calories for slot in plan.meals) == pytest.approx(energy, abs=5)
    if plan.body.bmi < safety.UNDERWEIGHT_BMI:
        assert plan.target.daily_balance_kcal >= -safety.KCAL_TOLERANCE
    assert 0.8 <= plan.macros.protein_g / inputs.weight_kg <= 3.5
    json.dumps(plan.to_dict())


VALID_INPUTS = st.fixed_dictionaries(
    {
        "sex": st.sampled_from(list(Sex)),
        "age": st.integers(10, 110),
        "height_cm": st.floats(100, 250),
        "weight_kg": st.floats(25, 350),
        "body_fat_pct": st.one_of(st.none(), st.floats(2, 70)),
        "body_fat_method": st.sampled_from(list(BodyFatMethod)),
        "goal": st.sampled_from(list(Goal)),
        "training_days_per_week": st.integers(0, 7),
        "session_minutes": st.integers(0, 240),
        "training_experience": st.sampled_from(list(TrainingExperience)),
        "job_activity": st.sampled_from(list(JobActivity)),
        "sleep_hours": st.floats(0, 16),
        "stress_level": st.integers(1, 5),
        "meals_per_day": st.integers(1, 8),
        "daily_steps": st.one_of(st.none(), st.integers(0, 60000)),
        "aggressiveness": st.sampled_from(list(Aggressiveness)),
        "other_activity_sessions_per_week": st.integers(0, 14),
        "other_activity_minutes": st.integers(0, 300),
        "other_activity_intensity": st.one_of(st.none(), st.sampled_from(list(ActivityIntensity))),
        "training_time": st.sampled_from(list(TrainingTime)),
        "wants_carb_cycling": st.booleans(),
        "neck_cm": st.one_of(st.none(), st.floats(25, 60)),
        "waist_cm": st.one_of(st.none(), st.floats(50, 200)),
        "hip_cm": st.one_of(st.none(), st.floats(60, 200)),
    }
)


@settings(max_examples=200, deadline=None)
@given(values=VALID_INPUTS)
def test_any_valid_inputs_produce_a_safe_plan_or_a_blocked_one(values: dict[str, Any]) -> None:
    inputs = NutritionInputs(today=date(2026, 9, 9), **values)
    plan = build_nutrition_plan(inputs)
    if plan.is_blocked:
        assert plan.blocked_reasons
        return
    _assert_invariants(inputs, plan)


def test_messages_render_known_and_unknown_codes() -> None:
    assert "Navy" in render(Note("body_fat.navy", params={"value": 15.2}))
    assert render(Note("nope.unknown")) == "nope.unknown"
    assert "{'x': 1}" in render(Note("nope.unknown", params={"x": 1}))
    assert render(Note("target.deficit")).startswith("target.deficit")  # missing param -> fallback
    lines = render_all(
        (Note("bmr.mifflin"), Note("safety.minor", level="error", params={"age": 16}))
    )
    assert lines[1].startswith("[error]")
    assert confidence_label(Confidence.HIGH) == "high"


def test_jsonable_handles_dates_enum_keys_and_nested_structures() -> None:
    payload = _jsonable(
        {"when": date(2026, 1, 2), Sex.MALE: [Note("x", params={"day": date(2026, 1, 3)})]}
    )
    assert payload == {
        "when": "2026-01-02",
        "male": [{"code": "x", "level": "info", "params": {"day": "2026-01-03"}}],
    }
