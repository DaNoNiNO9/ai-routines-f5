"""The biweekly review: real logs in, engine decision out, and what gets written."""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.engine import safety
from app.engine.enums import AdjustmentReason, PlanStatus
from app.engine.equipment_presets import preset_for
from app.models import Equipment, Plan, PlanAdjustment, Profile, User
from app.services import adjustments, plans, tracking
from app.services.adjustments import ReviewError
from tests.factories import make_profile, make_user

TODAY = date(2026, 9, 9)
PLAN_DAYS = 15


def _with_plan(
    seeded: SQLAlchemy,
    days_ago: int = PLAN_DAYS,
    email: str = "ana@example.com",
    **profile_kwargs: object,
) -> tuple[User, Profile, Plan]:
    """A user with a plan that started ``days_ago`` days before ``TODAY``."""
    user = make_user(seeded.session, email=email)
    user.equipment = seeded.session.scalars(
        select(Equipment).where(Equipment.code.in_(preset_for("full_gym")))
    ).all()
    profile = make_profile(seeded.session, user, **profile_kwargs)
    result = plans.generate_for_profile(user, profile, TODAY - timedelta(days=days_ago))
    seeded.session.commit()
    assert result.plan is not None
    return user, profile, result.plan


def _log_weights(
    seeded: SQLAlchemy, user: User, plan: Plan, start_kg: float, total_change_kg: float
) -> None:
    """One weigh-in per day from the plan start to today, changing linearly."""
    days = (TODAY - plan.starts_on).days
    for offset in range(days + 1):
        weight = start_kg + total_change_kg * offset / days
        tracking.upsert_weight(user, plan.starts_on + timedelta(days=offset), round(weight, 2))
    seeded.session.commit()


def _log_intakes(seeded: SQLAlchemy, user: User, plan: Plan, calories: int, adherence: int) -> None:
    days = (TODAY - plan.starts_on).days
    for offset in range(days + 1):
        tracking.upsert_intake(
            user, plan.starts_on + timedelta(days=offset), calories, adherence_pct=adherence
        )
    seeded.session.commit()


def test_steps_target_comes_from_the_plan_or_the_engine_default(seeded: SQLAlchemy) -> None:
    _user, profile, plan = _with_plan(seeded)
    assert plan.details["steps_target"] == adjustments.steps_target_for(plan, profile)
    assert plan.details["steps_target"] >= 8000  # fat loss adds steps over the baseline

    plan.details = {key: value for key, value in plan.details.items() if key != "steps_target"}
    seeded.session.commit()
    assert adjustments.steps_target_for(plan, profile) >= 8000


def test_weeks_in_deficit_counts_the_days_of_every_deficit_version(seeded: SQLAlchemy) -> None:
    user, _profile, plan = _with_plan(seeded)
    assert adjustments.weeks_in_deficit(user, plan, TODAY) == PLAN_DAYS // 7


def test_preview_needs_a_plan_and_weigh_ins(seeded: SQLAlchemy) -> None:
    user = make_user(seeded.session)
    seeded.session.commit()
    with pytest.raises(ReviewError) as caught:
        adjustments.preview(user, TODAY)
    assert caught.value.reason == "no_plan"

    user2, _profile, _plan = _with_plan(seeded, email="otra@example.com")
    with pytest.raises(ReviewError) as caught:
        adjustments.preview(user2, TODAY)
    assert caught.value.reason == "no_weights"


def test_review_before_the_due_date_waits(seeded: SQLAlchemy) -> None:
    user, _profile, plan = _with_plan(seeded, days_ago=6)
    _log_weights(seeded, user, plan, 64.0, -0.2)
    current = adjustments.preview(user, TODAY)
    assert current.due is False
    assert current.decision.action == "wait"
    assert current.decision.calorie_delta == 0
    assert any("próxima revisión" in item["text"].lower() for item in current.messages)

    with pytest.raises(ReviewError) as caught:
        adjustments.apply(user, TODAY)
    assert caught.value.reason == "not_due"
    assert seeded.session.scalars(select(Plan)).all() == [plan]


def test_slow_loss_cuts_calories_into_a_new_plan_version(seeded: SQLAlchemy) -> None:
    user, _profile, plan = _with_plan(seeded)
    _log_weights(seeded, user, plan, 64.0, -0.15)  # about 0.07 kg/week, well under target
    before_calories = plan.calorie_target

    current = adjustments.preview(user, TODAY)
    assert current.due is True
    assert current.decision.action == "reduce_calories"
    assert current.weigh_ins == PLAN_DAYS + 1
    assert seeded.session.scalars(select(Plan)).all() == [plan]  # preview writes nothing

    result = adjustments.apply(user, TODAY)
    seeded.session.commit()

    assert result.created_new_plan is True
    new_plan = result.plan_after
    assert new_plan.version == 2
    assert new_plan.status is PlanStatus.ACTIVE
    assert new_plan.calorie_target < before_calories
    assert before_calories - new_plan.calorie_target <= before_calories * 0.05
    assert new_plan.starts_on == TODAY
    assert new_plan.routine is plan.routine
    assert new_plan.details["steps_target"] == plan.details["steps_target"]
    assert plan.status is PlanStatus.SUPERSEDED
    assert plan.ends_on == TODAY

    audit = result.adjustment
    assert audit.reason is AdjustmentReason.LOSS_TOO_SLOW
    assert audit.previous_plan is plan
    assert audit.observed_weekly_change_kg is not None
    assert audit.observed_weekly_change_kg > -0.15
    assert audit.data["review"] is True
    assert "kcal" in audit.explanation


def test_the_cut_never_goes_below_the_calorie_floor(seeded: SQLAlchemy) -> None:
    user, profile, plan = _with_plan(seeded)
    floor = safety.calorie_floor(profile.sex, plan.bmr_kcal)
    plan.calorie_target = int(math.ceil(floor / 5) * 5)
    seeded.session.commit()
    _log_weights(seeded, user, plan, 64.0, -0.15)

    current = adjustments.preview(user, TODAY)
    assert current.decision.action == "add_steps"
    assert current.decision.calorie_delta == 0
    assert current.decision.steps_delta > 0

    result = adjustments.apply(user, TODAY)
    seeded.session.commit()
    assert result.created_new_plan is False
    assert result.plan_after is plan
    assert plan.calorie_target >= floor
    assert plan.details["steps_target"] == current.decision.new_steps_target
    assert result.adjustment.steps_delta == current.decision.steps_delta
    assert result.adjustment.calorie_delta == 0
    assert len(seeded.session.scalars(select(Plan)).all()) == 1


def test_losing_faster_than_the_safety_cap_raises_calories(seeded: SQLAlchemy) -> None:
    user, _profile, plan = _with_plan(seeded)
    _log_weights(seeded, user, plan, 64.0, -1.5)  # 0.7 kg/week on a 64 kg person
    before = plan.calorie_target

    current = adjustments.preview(user, TODAY)
    assert current.decision.action == "increase_calories"
    result = adjustments.apply(user, TODAY)
    seeded.session.commit()
    assert result.plan_after.calorie_target > before
    assert result.adjustment.reason is AdjustmentReason.LOSS_TOO_FAST


def test_on_target_keeps_the_plan_and_records_the_review(seeded: SQLAlchemy) -> None:
    user, _profile, plan = _with_plan(seeded)
    expected_weekly = plan.details["target"]["expected_weekly_change_kg"]
    _log_weights(seeded, user, plan, 64.0, expected_weekly * PLAN_DAYS / 7)

    current = adjustments.preview(user, TODAY)
    assert current.decision.action == "keep"

    result = adjustments.apply(user, TODAY)
    seeded.session.commit()
    assert result.created_new_plan is False
    assert result.adjustment.calorie_delta == 0
    assert result.adjustment.steps_delta == 0
    assert len(seeded.session.scalars(select(Plan)).all()) == 1

    records = adjustments.review_records(plan)
    assert len(records) == 1
    assert records[0] is result.adjustment
    # The record that created the plan is not a review.
    everything = seeded.session.scalars(select(PlanAdjustment)).all()
    assert len(everything) == 2
    assert everything[0].reason is AdjustmentReason.INITIAL


def test_poor_adherence_is_reported_before_touching_calories(seeded: SQLAlchemy) -> None:
    user, _profile, plan = _with_plan(seeded)
    _log_weights(seeded, user, plan, 64.0, -0.15)
    _log_intakes(seeded, user, plan, plan.calorie_target + 400, adherence=60)

    current = adjustments.preview(user, TODAY)
    assert current.decision.action == "adherence"
    assert current.decision.adherence_pct == pytest.approx(60.0)
    assert current.intake_days == PLAN_DAYS + 1
    assert any("adherencia" in item["text"].lower() for item in current.messages)

    result = adjustments.apply(user, TODAY)
    seeded.session.commit()
    assert result.created_new_plan is False
    assert plan.calorie_target == result.plan_after.calorie_target


def test_the_observed_expenditure_reaches_the_decision(seeded: SQLAlchemy) -> None:
    user, _profile, plan = _with_plan(seeded)
    _log_weights(seeded, user, plan, 64.0, -0.15)
    _log_intakes(seeded, user, plan, plan.calorie_target, adherence=95)

    decision = adjustments.preview(user, TODAY).decision
    assert decision.tdee is not None
    assert decision.tdee.observed_kcal is not None
    assert decision.tdee.observed_kcal < plan.tdee_kcal  # eating the plan and barely losing
    result = adjustments.apply(user, TODAY)
    seeded.session.commit()
    assert result.adjustment.observed_tdee_kcal == pytest.approx(decision.tdee.observed_kcal)


def test_the_next_review_moves_after_applying_one(seeded: SQLAlchemy) -> None:
    from app.services import dashboard

    user, _profile, plan = _with_plan(seeded)
    _log_weights(seeded, user, plan, 64.0, -0.15)
    assert dashboard.next_review_on(plan) == plan.starts_on + timedelta(days=14)

    result = adjustments.apply(user, TODAY)
    seeded.session.commit()
    assert dashboard.next_review_on(result.plan_after) == TODAY + timedelta(days=14)
