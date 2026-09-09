"""Plans, meals, adjustments, routines and workout logs."""

from __future__ import annotations

from datetime import date

import pytest
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError

from app.models import (
    Meal,
    Plan,
    PlanAdjustment,
    RoutineDay,
    RoutineExercise,
    SetLog,
    WorkoutSession,
)
from tests.factories import aware, make_exercise, make_plan, make_profile, make_routine, make_user


def test_plan_meals_are_ordered_and_positions_unique(database: SQLAlchemy) -> None:
    session = database.session
    user = make_user(session)
    profile = make_profile(session, user)
    plan = make_plan(session, user, profile)
    plan.meals.append(
        Meal(position=2, name="Comida", calories=700, protein_g=45, carbs_g=80, fat_g=20)
    )
    plan.meals.append(
        Meal(position=1, name="Desayuno", calories=400, protein_g=30, carbs_g=50, fat_g=10)
    )
    session.commit()
    session.expire_all()
    assert [meal.name for meal in plan.meals] == ["Desayuno", "Comida"]

    plan.meals.append(Meal(position=1, name="Otro", calories=100, protein_g=1, carbs_g=1, fat_g=1))
    with pytest.raises(IntegrityError):
        session.flush()


def test_plan_calorie_target_is_bounded(database: SQLAlchemy) -> None:
    session = database.session
    user = make_user(session)
    profile = make_profile(session, user)
    session.add(Plan(user=user, profile=profile, version=1, **_plan_values(calorie_target=100)))
    with pytest.raises(IntegrityError):
        session.flush()


def test_plan_versions_are_unique_per_user(database: SQLAlchemy) -> None:
    session = database.session
    user = make_user(session)
    profile = make_profile(session, user)
    make_plan(session, user, profile, version=1)
    session.add(Plan(user=user, profile=profile, version=1, **_plan_values()))
    with pytest.raises(IntegrityError):
        session.flush()


def test_adjustment_links_new_and_previous_plan(database: SQLAlchemy) -> None:
    session = database.session
    user = make_user(session)
    profile = make_profile(session, user)
    first = make_plan(session, user, profile, version=1)
    second = make_plan(session, user, profile, version=2, calorie_target=1700)
    adjustment = PlanAdjustment(
        user=user,
        plan=second,
        previous_plan=first,
        reason="loss_too_slow",
        calorie_delta=-100,
        expected_weekly_change_kg=-0.5,
        observed_weekly_change_kg=-0.2,
        explanation="Pérdida por debajo de lo esperado: -100 kcal.",
    )
    session.add(adjustment)
    session.commit()
    session.expire_all()
    assert user.plan_adjustments[0].previous_plan is first
    assert user.plan_adjustments[0].plan.calorie_target == 1700


def test_routine_structure_constraints(database: SQLAlchemy) -> None:
    session = database.session
    user = make_user(session)
    profile = make_profile(session, user)
    exercise = make_exercise(session)
    routine = make_routine(session, user, profile)
    day = RoutineDay(day_index=1, name="Día 1", focus=["chest", "back"])
    day.exercises.append(
        RoutineExercise(
            exercise=exercise, position=1, sets=4, rep_min=6, rep_max=10, rest_seconds=150
        )
    )
    routine.days.append(day)
    session.commit()
    assert routine.days[0].exercises[0].rir_start == 3

    day.exercises.append(
        RoutineExercise(
            exercise=exercise, position=2, sets=3, rep_min=12, rep_max=8, rest_seconds=60
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()

    routine.days.append(RoutineDay(day_index=1, name="Duplicado"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_routine_mesocycle_bounds(database: SQLAlchemy) -> None:
    session = database.session
    user = make_user(session)
    profile = make_profile(session, user)
    with pytest.raises(IntegrityError):
        make_routine(session, user, profile, mesocycle_weeks=2)


def test_workout_cannot_finish_before_it_starts(database: SQLAlchemy) -> None:
    session = database.session
    user = make_user(session)
    session.add(
        WorkoutSession(
            user=user, started_at=aware(2026, 9, 9, 18), finished_at=aware(2026, 9, 9, 17)
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_set_logs_unique_per_session_exercise_and_index(database: SQLAlchemy) -> None:
    session = database.session
    user = make_user(session)
    exercise = make_exercise(session)
    workout = WorkoutSession(user=user, started_at=aware(2026, 9, 9))
    workout.sets.append(
        SetLog(exercise=exercise, set_index=1, reps=8, weight_kg=60, completed_at=aware(2026, 9, 9))
    )
    workout.sets.append(
        SetLog(exercise=exercise, set_index=1, reps=8, weight_kg=60, completed_at=aware(2026, 9, 9))
    )
    session.add(workout)
    with pytest.raises(IntegrityError):
        session.flush()


def test_set_log_defaults_and_ordering(database: SQLAlchemy) -> None:
    session = database.session
    user = make_user(session)
    exercise = make_exercise(session)
    workout = WorkoutSession(user=user, started_at=aware(2026, 9, 9))
    for index in (2, 1):
        workout.sets.append(
            SetLog(
                exercise=exercise,
                set_index=index,
                reps=10,
                weight_kg=0,
                completed_at=aware(2026, 9, 9, 10 + index),
            )
        )
    session.add(workout)
    session.commit()
    session.expire_all()
    assert [s.set_index for s in workout.sets] == [1, 2]
    assert workout.sets[0].set_type == "working"
    assert workout.status == "in_progress"
    assert workout.started_at.tzinfo is not None


def test_soft_delete_on_plans_routines_and_sessions(database: SQLAlchemy) -> None:
    session = database.session
    user = make_user(session)
    profile = make_profile(session, user)
    plan = make_plan(session, user, profile)
    routine = make_routine(session, user, profile)
    workout = WorkoutSession(user=user, started_at=aware(2026, 9, 9))
    session.add(workout)
    session.commit()
    for row in (plan, routine, workout):
        row.soft_delete()
    session.commit()
    assert all(row.is_deleted for row in (plan, routine, workout))
    assert plan.starts_on == date(2026, 9, 9)


def _plan_values(**overrides: object) -> dict[str, object]:
    from tests.factories import PLAN_DEFAULTS

    return {**PLAN_DEFAULTS, "starts_on": date(2026, 9, 9), **overrides}
