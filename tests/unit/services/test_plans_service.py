"""Profile → engine inputs, catalogue from rows, and persistence of plans and routines."""

from __future__ import annotations

from datetime import date

import pytest
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.engine.enums import (
    AdjustmentReason,
    BodyFatMethod,
    Goal,
    InjuryArea,
    MuscleGroup,
    PlanStatus,
    Severity,
    TrainingLocation,
)
from app.engine.equipment_presets import preset_for
from app.engine.nutrition import build_nutrition_plan
from app.engine.types import CalorieTarget, Note, NutritionPlan
from app.models import Equipment, Injury, Meal, Plan, PlanAdjustment, Routine, RoutineExercise
from app.services import plans
from tests.factories import make_exercise, make_profile, make_user

TODAY = date(2026, 9, 9)


def _equip(database: SQLAlchemy, user, location: str) -> None:
    codes = preset_for(location)
    user.equipment = database.session.scalars(
        select(Equipment).where(Equipment.code.in_(codes))
    ).all()


def test_nutrition_inputs_mirror_the_profile(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    profile = make_profile(database.session, user, body_fat_pct=24.0, body_fat_method="calipers")
    inputs = plans.nutrition_inputs(profile, TODAY)
    assert inputs.age == 34
    assert inputs.sex is profile.sex
    assert inputs.body_fat_method is BodyFatMethod.CALIPERS
    assert inputs.today == TODAY
    assert inputs.meals_per_day == profile.meals_per_day


def test_routine_inputs_carry_injuries_priorities_and_equipment(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    profile = make_profile(
        database.session,
        user,
        priority_muscles=["glutes", "shoulders", "chest"],
        disliked_exercises=["barbell-squat"],
    )
    profile.injuries.append(Injury(area=InjuryArea.KNEE, severity=Severity.MODERATE))
    database.session.flush()
    inputs = plans.routine_inputs(profile, frozenset({"body_only", "dumbbells"}), None)
    assert inputs.priority_muscles == (MuscleGroup.GLUTES, MuscleGroup.SHOULDERS)
    assert inputs.injuries[0].area is InjuryArea.KNEE
    assert inputs.equipment == frozenset({"body_only", "dumbbells"})
    assert "barbell-squat" in inputs.disliked_exercises
    assert inputs.extra_deficit_kcal_per_day == 0.0


def _target(mode: str, notes: tuple[Note, ...]) -> CalorieTarget:
    return CalorieTarget(
        goal=Goal.FAT_LOSS,
        mode=mode,
        fraction=0.2,
        maintenance_kcal=2000.0,
        target_kcal=1700,
        expenditure_at_target_kcal=1950.0,
        daily_balance_kcal=-250.0,
        expected_weekly_change_kg=-0.23,
        notes=notes,
    )


def test_uncovered_deficit_only_when_the_floor_intervened(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    profile = make_profile(database.session, user)
    body = build_nutrition_plan(plans.nutrition_inputs(profile, TODAY)).body
    raised = NutritionPlan(
        status="ok",
        confidence=body.confidence,
        body=body,
        target=_target("deficit", (Note("target.raised_to_floor", level="warning"),)),
    )
    assert plans.uncovered_deficit_kcal(raised) == pytest.approx(150.0)  # 400 wanted - 250 got
    free = NutritionPlan(
        status="ok", confidence=body.confidence, body=body, target=_target("deficit", ())
    )
    assert plans.uncovered_deficit_kcal(free) == 0.0
    surplus = NutritionPlan(
        status="ok", confidence=body.confidence, body=body, target=_target("surplus", ())
    )
    assert plans.uncovered_deficit_kcal(surplus) == 0.0
    assert (
        plans.routine_inputs(profile, frozenset({"body_only"}), raised).extra_deficit_kcal_per_day
        == 150.0
    )


def test_catalogue_is_built_from_the_rows(seeded: SQLAlchemy) -> None:
    catalogue, by_slug = plans.load_catalogue()
    assert len(catalogue) == len(by_slug) >= 150
    press = next(item for item in catalogue if item.slug == "barbell-bench-press-medium-grip")
    assert press.primary is MuscleGroup.CHEST
    assert "barbell" in press.equipment
    assert press.alternatives, "alternatives come through as slugs"
    assert all(alt in by_slug for alt in press.alternatives)


def test_inactive_exercises_are_left_out(seeded: SQLAlchemy) -> None:
    make_exercise(seeded.session, slug="retired-move", is_active=False)
    catalogue, by_slug = plans.load_catalogue()
    assert "retired-move" not in by_slug
    assert all(item.slug != "retired-move" for item in catalogue)


def test_generate_stores_plan_meals_routine_and_audit(seeded: SQLAlchemy) -> None:
    user = make_user(seeded.session)
    _equip(seeded, user, TrainingLocation.FULL_GYM)
    profile = make_profile(seeded.session, user)
    result = plans.generate_for_profile(user, profile, TODAY)
    seeded.session.commit()

    assert not result.is_blocked
    plan = result.plan
    assert plan is not None
    assert plan.version == 1
    assert plan.status is PlanStatus.ACTIVE
    assert plan.starts_on == TODAY
    assert plan.routine is result.routine
    assert plan.calorie_target == result.nutrition.macros.calories
    assert len(plan.meals) == profile.meals_per_day
    # Meals are rebuilt from macro grams, so the sum can differ by a few kcal.
    assert abs(sum(meal.calories for meal in plan.meals) - plan.calorie_target) <= 10
    assert plan.details["messages"]
    assert all("text" in m for m in plan.details["messages"])
    assert plan.inputs_snapshot["sex"] == "female"

    routine = result.routine
    assert routine is not None
    assert routine.version == 1
    assert routine.days_per_week == profile.training_days_per_week
    assert len(routine.days) == 4
    first = routine.days[0]
    assert first.day_index == 1
    assert first.exercises[0].position == 1
    assert first.exercises[0].exercise.slug == result.routine_plan.days[0].exercises[0].slug
    assert sorted(routine.inputs_snapshot["equipment"]) == sorted(preset_for("full_gym"))

    audit = seeded.session.scalars(select(PlanAdjustment)).all()
    assert len(audit) == 1
    assert audit[0].reason is AdjustmentReason.INITIAL
    assert audit[0].plan is plan
    assert "kcal" in audit[0].explanation


def test_second_generation_supersedes_the_previous_versions(seeded: SQLAlchemy) -> None:
    user = make_user(seeded.session)
    _equip(seeded, user, TrainingLocation.FULL_GYM)
    first_profile = make_profile(seeded.session, user)
    first = plans.generate_for_profile(user, first_profile, TODAY)
    seeded.session.commit()
    second_profile = make_profile(seeded.session, user, version=2, goal=Goal.MUSCLE_GAIN)
    second = plans.generate_for_profile(user, second_profile, TODAY)
    seeded.session.commit()

    assert first.plan is not None
    assert second.plan is not None
    assert first.plan.status is PlanStatus.SUPERSEDED
    assert first.plan.superseded_at is not None
    assert first.plan.ends_on == TODAY
    assert second.plan.version == 2
    assert plans.active_plan(user) is second.plan
    assert first.routine is not None
    assert first.routine.status is PlanStatus.SUPERSEDED
    assert plans.active_routine(user) is second.routine
    audit = seeded.session.scalars(select(PlanAdjustment).order_by(PlanAdjustment.id)).all()
    assert audit[-1].reason is AdjustmentReason.PROFILE_CHANGE
    assert audit[-1].previous_plan is first.plan
    assert audit[-1].calorie_delta == second.plan.calorie_target - first.plan.calorie_target


def test_blocked_nutrition_stores_nothing(seeded: SQLAlchemy) -> None:
    user = make_user(seeded.session)
    _equip(seeded, user, TrainingLocation.FULL_GYM)
    profile = make_profile(seeded.session, user, is_pregnant_or_breastfeeding=True)
    result = plans.generate_for_profile(user, profile, TODAY)
    seeded.session.commit()
    assert result.is_blocked
    assert result.plan is None
    assert result.routine is None
    assert result.routine_plan is None
    assert {note.code for note in result.nutrition.blocked_reasons} == {"safety.pregnancy"}
    assert seeded.session.scalars(select(Plan)).all() == []
    assert seeded.session.scalars(select(Routine)).all() == []


def test_bodyweight_only_still_gets_a_routine(seeded: SQLAlchemy) -> None:
    user = make_user(seeded.session)
    _equip(seeded, user, TrainingLocation.HOME_BODYWEIGHT)
    profile = make_profile(seeded.session, user, training_location=TrainingLocation.HOME_BODYWEIGHT)
    result = plans.generate_for_profile(user, profile, TODAY)
    seeded.session.commit()
    assert result.routine is not None
    used = seeded.session.scalars(select(RoutineExercise)).all()
    assert used
    assert all(item.exercise.equipment_codes <= {"body_only"} for item in used)


def test_persist_refuses_blocked_results(seeded: SQLAlchemy) -> None:
    user = make_user(seeded.session)
    profile = make_profile(seeded.session, user, is_pregnant_or_breastfeeding=True)
    inputs = plans.nutrition_inputs(profile, TODAY)
    blocked = build_nutrition_plan(inputs)
    with pytest.raises(ValueError, match="complete nutrition plan"):
        plans.persist_plan(user, profile, inputs, blocked, TODAY)


def test_messages_of_ignores_malformed_entries() -> None:
    assert plans.messages_of({}) == []
    assert plans.messages_of(
        {"messages": ["x", {"level": "info"}, {"level": "info", "text": "ok"}]}
    ) == [{"level": "info", "text": "ok"}]


def test_meal_rows_match_engine_slots(seeded: SQLAlchemy) -> None:
    user = make_user(seeded.session)
    _equip(seeded, user, TrainingLocation.FULL_GYM)
    profile = make_profile(seeded.session, user, meals_per_day=3, training_time="evening")
    result = plans.generate_for_profile(user, profile, TODAY)
    seeded.session.commit()
    rows = seeded.session.scalars(select(Meal).order_by(Meal.position)).all()
    assert [(row.position, row.name, row.calories) for row in rows] == [
        (slot.position, slot.name, slot.calories) for slot in result.nutrition.meals
    ]


def test_persist_routine_refuses_blocked_results(seeded: SQLAlchemy) -> None:
    from app.engine.routines.generator import build_routine

    user = make_user(seeded.session)
    profile = make_profile(seeded.session, user)
    inputs = plans.routine_inputs(profile, frozenset({"cardio_machine"}), None)
    catalogue, by_slug = plans.load_catalogue()
    blocked = build_routine(inputs, catalogue)
    assert blocked.is_blocked
    with pytest.raises(ValueError, match="complete routine"):
        plans.persist_routine(user, profile, inputs, blocked, TODAY, by_slug)
