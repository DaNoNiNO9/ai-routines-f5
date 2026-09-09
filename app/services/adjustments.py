"""The biweekly review: feed the adjustment engine with real logs and apply what it decides.

``preview()`` never writes. ``apply()`` writes exactly one of: a new plan
version (calories changed), a steps change on the current plan, or a review
record with no change (so the next review is scheduled). The person triggers
it from the review page: the app never changes a plan silently.
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.engine import messages, safety
from app.engine.adjustment.rules import STALL_THRESHOLD_KG, decide
from app.engine.adjustment.types import (
    AdjustmentDecision,
    AdjustmentInputs,
    IntakePoint,
    WeightPoint,
)
from app.engine.enums import AdjustmentReason, PlanStatus
from app.engine.macros import carb_cycle, compute_macros, hydration
from app.engine.meals import distribute_meals
from app.engine.nutrition import build_nutrition_plan
from app.engine.routines.cardio import steps_target as default_steps_target
from app.engine.targets import with_calories
from app.engine.types import NutritionPlan
from app.extensions import db
from app.models import IntakeLog, Plan, PlanAdjustment, Profile, User, WeightLog
from app.services import plans

logger = logging.getLogger(__name__)

HISTORY_MARGIN_DAYS = 7
MAX_HISTORY_DAYS = 90
REVIEW_REASONS = frozenset(
    reason
    for reason in AdjustmentReason
    if reason not in {AdjustmentReason.INITIAL, AdjustmentReason.PROFILE_CHANGE}
)


class ReviewError(Exception):
    """The review cannot run or be applied; ``reason`` is a stable code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ReviewPreview:
    """What the engine would do today, plus the data it saw."""

    plan: Plan
    decision: AdjustmentDecision
    messages: list[dict[str, str]]
    weigh_ins: int
    intake_days: int
    inputs: AdjustmentInputs

    @property
    def due(self) -> bool:
        """Whether the review can be applied today."""
        return self.decision.review_due


@dataclass(frozen=True)
class AppliedReview:
    """Result of applying a review."""

    decision: AdjustmentDecision
    adjustment: PlanAdjustment
    plan_before: Plan
    plan_after: Plan

    @property
    def created_new_plan(self) -> bool:
        """Whether a new plan version was stored."""
        return self.plan_after is not self.plan_before


def steps_target_for(plan: Plan, profile: Profile) -> int:
    """Daily steps goal in force (stored with the plan; the engine's default otherwise)."""
    stored = plan.details.get("steps_target")
    if isinstance(stored, int):
        return stored
    return default_steps_target(profile.daily_steps, profile.goal)


def _mode(plan: Plan) -> str:
    target = plan.details.get("target") or {}
    return str(target.get("mode") or "maintenance")


def _expected_weekly_change(plan: Plan) -> float:
    target = plan.details.get("target") or {}
    return float(target.get("expected_weekly_change_kg") or 0.0)


def weeks_in_deficit(user: User, plan: Plan, today: date) -> int:
    """Consecutive weeks the person has been in a deficit up to ``today``."""
    versions = db.session.scalars(
        select(Plan)
        .where(Plan.user_id == user.id, Plan.version <= plan.version)
        .order_by(Plan.version.desc())
    ).all()
    days = 0
    for version in versions:
        if _mode(version) != "deficit":
            break
        end = version.ends_on or today
        days += max(0, (min(end, today) - version.starts_on).days)
    return days // 7


def review_records(plan: Plan) -> list[PlanAdjustment]:
    """Reviews recorded on ``plan`` (the record that created it does not count), oldest first."""
    rows = db.session.scalars(
        select(PlanAdjustment)
        .where(PlanAdjustment.plan_id == plan.id)
        .order_by(PlanAdjustment.created_at, PlanAdjustment.id)
    ).all()
    return [row for row in rows if row.reason in REVIEW_REASONS or row.data.get("review")]


def build_inputs(user: User, plan: Plan, profile: Profile, today: date) -> AdjustmentInputs:
    """Engine inputs from the plan in force and the diary."""
    since = max(
        today - timedelta(days=MAX_HISTORY_DAYS),
        plan.starts_on - timedelta(days=HISTORY_MARGIN_DAYS),
    )
    weights = db.session.scalars(
        select(WeightLog)
        .where(
            WeightLog.user_id == user.id,
            WeightLog.logged_on >= since,
            WeightLog.logged_on <= today,
        )
        .order_by(WeightLog.logged_on)
    ).all()
    intakes = db.session.scalars(
        select(IntakeLog)
        .where(
            IntakeLog.user_id == user.id,
            IntakeLog.logged_on >= since,
            IntakeLog.logged_on <= today,
        )
        .order_by(IntakeLog.logged_on)
    ).all()
    if not weights:
        raise ReviewError("no_weights")
    records = review_records(plan)
    last = records[-1] if records else None
    stalled = sum(1 for record in records if record.data.get("stalled"))
    return AdjustmentInputs(
        sex=profile.sex,
        goal=plan.goal,
        mode=_mode(plan),
        plan_calories=plan.calorie_target,
        plan_started_on=plan.starts_on,
        expected_weekly_change_kg=_expected_weekly_change(plan),
        bmr_kcal=plan.bmr_kcal,
        theoretical_tdee_kcal=plan.tdee_kcal,
        weights=tuple(WeightPoint(day=row.logged_on, weight_kg=row.weight_kg) for row in weights),
        intakes=tuple(
            IntakePoint(
                day=row.logged_on,
                calories=float(row.calories),
                adherence_pct=float(row.adherence_pct) if row.adherence_pct is not None else None,
            )
            for row in intakes
        ),
        today=today,
        steps_target=steps_target_for(plan, profile),
        weeks_in_deficit=weeks_in_deficit(user, plan, today),
        last_adjustment_on=last.created_at.date() if last is not None else None,
        stalled_reviews=stalled,
    )


def preview(user: User, today: date) -> ReviewPreview:
    """Run the engine without writing anything.

    Raises:
        ReviewError: ``no_plan`` without an active plan, ``no_weights`` without weigh-ins.
    """
    plan = plans.active_plan(user)
    profile = plan.profile if plan is not None else None
    if plan is None or profile is None:
        raise ReviewError("no_plan")
    inputs = build_inputs(user, plan, profile, today)
    decision = decide(inputs)
    return ReviewPreview(
        plan=plan,
        decision=decision,
        messages=plans.messages_for(decision.notes),
        weigh_ins=len(inputs.weights),
        intake_days=len(inputs.intakes),
        inputs=inputs,
    )


def _is_stalled(inputs: AdjustmentInputs, decision: AdjustmentDecision) -> bool:
    observed = decision.observed_weekly_change_kg
    return inputs.mode == "deficit" and observed is not None and -observed < STALL_THRESHOLD_KG


def _explanation(decision: AdjustmentDecision) -> str:
    return " ".join(messages.render(note) for note in decision.notes)


def _plan_with_calories(
    profile: Profile, plan: Plan, new_calories: int, today: date, current_weight_kg: float
) -> tuple[Any, NutritionPlan]:
    """Rebuild the nutrition numbers around ``new_calories`` with the current weight."""
    inputs = dataclasses.replace(
        plans.nutrition_inputs(profile, today), weight_kg=current_weight_kg
    )
    nutrition = build_nutrition_plan(inputs)
    if (
        nutrition.is_blocked
        or nutrition.target is None
        or nutrition.expenditure is None
        or nutrition.bmr is None
    ):
        raise ReviewError("blocked")
    macros = compute_macros(inputs, nutrition.body, new_calories, nutrition.target.mode)
    target = with_calories(nutrition.target, macros.calories, nutrition.expenditure)
    meals, meal_notes = distribute_meals(
        macros, inputs.meals_per_day, inputs.training_time, nutrition.body.weight_kg
    )
    cycle = carb_cycle(macros, inputs.training_days_per_week) if inputs.wants_carb_cycling else None
    water = hydration(
        nutrition.body.weight_kg, inputs.session_minutes if inputs.training_days_per_week else 0
    )
    violations = safety.verify_plan(inputs, nutrition.body, nutrition.bmr, target, macros)
    if violations:
        raise safety.SafetyError(violations)
    adjusted = dataclasses.replace(
        nutrition,
        target=target,
        macros=macros,
        meals=meals,
        carb_cycle=cycle,
        hydration=water,
        notes=(*meal_notes, *nutrition.notes),
    )
    del plan  # kept in the signature for symmetry with the caller; the numbers come from the engine
    return inputs, adjusted


def apply(user: User, today: date) -> AppliedReview:
    """Run the review and store its outcome.

    Raises:
        ReviewError: ``not_due`` before the review date, plus the ``preview`` errors and
            ``blocked`` when the rebuilt plan is no longer allowed.
        SafetyError: If the rebuilt numbers violate a hard limit (a bug upstream).
    """
    current = preview(user, today)
    decision = current.decision
    if not decision.review_due:
        raise ReviewError("not_due")
    plan = current.plan
    profile = plan.profile
    data = decision.to_dict()
    data["review"] = True
    data["stalled"] = _is_stalled(current.inputs, decision)
    explanation = _explanation(decision)

    if decision.calorie_delta != 0:
        inputs, adjusted = _plan_with_calories(
            profile, plan, decision.new_calories, today, current.inputs.current_weight_kg
        )
        new_plan = plans.persist_plan(
            user,
            profile,
            inputs,
            adjusted,
            today,
            reason=decision.reason,
            explanation=explanation,
            data=data,
            steps_target=decision.new_steps_target,
            observed_weekly_change_kg=decision.observed_weekly_change_kg,
            observed_tdee_kcal=decision.tdee.observed_kcal if decision.tdee else None,
            steps_delta=decision.steps_delta,
        )
        new_plan.routine = plan.routine
        adjustment = db.session.scalar(
            select(PlanAdjustment)
            .where(PlanAdjustment.plan_id == new_plan.id)
            .order_by(PlanAdjustment.id.desc())
        )
        if adjustment is None:  # pragma: no cover - persist_plan always records one
            raise ReviewError("no_audit")
        logger.info("Review applied for user %s: plan v%s", user.id, new_plan.version)
        return AppliedReview(decision, adjustment, plan, new_plan)

    if decision.steps_delta != 0:
        plan.details = {**plan.details, "steps_target": decision.new_steps_target}
    adjustment = PlanAdjustment(
        user=user,
        plan=plan,
        previous_plan=None,
        reason=decision.reason,
        expected_weekly_change_kg=decision.expected_weekly_change_kg,
        observed_weekly_change_kg=decision.observed_weekly_change_kg,
        observed_tdee_kcal=decision.tdee.observed_kcal if decision.tdee else None,
        calorie_delta=0,
        steps_delta=decision.steps_delta,
        explanation=explanation,
        data=data,
    )
    db.session.add(adjustment)
    db.session.flush()
    logger.info("Review recorded for user %s: %s", user.id, decision.action)
    return AppliedReview(decision, adjustment, plan, plan)


def latest_review(plan: Plan) -> PlanAdjustment | None:
    """The most recent review recorded on ``plan``."""
    records = review_records(plan)
    return records[-1] if records else None


def is_active(plan: Plan) -> bool:
    """Convenience for templates."""
    return plan.status is PlanStatus.ACTIVE


def as_of(value: datetime) -> date:
    """Calendar date of a stored UTC timestamp."""
    return value.date()
