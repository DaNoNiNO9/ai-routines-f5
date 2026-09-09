"""Read models for the signed-in pages: today's numbers, next session, weight trend, history.

Everything here only reads; the dashboard never changes state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select

from app.engine.adjustment.smoothing import moving_average
from app.engine.adjustment.types import WeightPoint
from app.engine.enums import WorkoutStatus
from app.engine.routines import catalog
from app.engine.routines.types import InjuryInput
from app.extensions import db
from app.models import (
    Exercise,
    Plan,
    PlanAdjustment,
    Profile,
    Routine,
    RoutineDay,
    RoutineExercise,
    User,
    WeightLog,
    WorkoutSession,
)
from app.services.plans import exercise_info

# Same default as ``AdjustmentInputs.review_interval_days`` (checked by a test).
REVIEW_INTERVAL_DAYS = 14
WEIGHT_HISTORY_DAYS = 90


@dataclass(frozen=True)
class WeightSeries:
    """Raw weigh-ins and their 7-day moving average, oldest first."""

    points: list[tuple[date, float]]
    smoothed: list[tuple[date, float]]

    @property
    def latest(self) -> tuple[date, float] | None:
        """Most recent weigh-in."""
        return self.points[-1] if self.points else None

    @property
    def change_kg(self) -> float | None:
        """Change of the smoothed weight over the series (needs two smoothed points)."""
        if len(self.smoothed) < 2:
            return None
        return round(self.smoothed[-1][1] - self.smoothed[0][1], 2)

    def to_chart(self) -> dict[str, Any]:
        """Chart.js payload: labels plus the raw and smoothed datasets aligned by day."""
        averages = dict(self.smoothed)
        return {
            "labels": [day.strftime("%d/%m") for day, _kg in self.points],
            "weight": [kg for _day, kg in self.points],
            "average": [averages.get(day) for day, _kg in self.points],
        }


def weight_series(user: User, today: date, days: int = WEIGHT_HISTORY_DAYS) -> WeightSeries:
    """Weigh-ins of the last ``days`` days with the moving average the engine uses."""
    since = today - timedelta(days=days - 1)
    rows = db.session.scalars(
        select(WeightLog)
        .where(WeightLog.user_id == user.id, WeightLog.logged_on >= since)
        .order_by(WeightLog.logged_on)
    ).all()
    points = [(row.logged_on, row.weight_kg) for row in rows]
    smoothed = moving_average([WeightPoint(day=day, weight_kg=kg) for day, kg in points])
    return WeightSeries(points=points, smoothed=smoothed)


def next_routine_day(user: User, routine: Routine | None) -> RoutineDay | None:
    """The day after the last completed session of this routine (day 1 when none)."""
    if routine is None or not routine.days:
        return None
    last = db.session.scalar(
        select(WorkoutSession)
        .join(RoutineDay, WorkoutSession.routine_day_id == RoutineDay.id)
        .where(
            WorkoutSession.user_id == user.id,
            RoutineDay.routine_id == routine.id,
            WorkoutSession.status == WorkoutStatus.COMPLETED,
        )
        .order_by(WorkoutSession.started_at.desc(), WorkoutSession.id.desc())
    )
    if last is None or last.routine_day_id is None:
        return routine.days[0]
    ids = [day.id for day in routine.days]
    position = ids.index(last.routine_day_id) if last.routine_day_id in ids else -1
    return routine.days[(position + 1) % len(routine.days)]


def next_review_on(plan: Plan) -> date:
    """When the biweekly review of ``plan`` is due (after its last adjustment, else its start)."""
    last = db.session.scalar(
        select(PlanAdjustment)
        .where(PlanAdjustment.plan_id == plan.id)
        .order_by(PlanAdjustment.created_at.desc(), PlanAdjustment.id.desc())
    )
    anchor = last.created_at.date() if last is not None else plan.starts_on
    anchor = max(anchor, plan.starts_on)
    return anchor + timedelta(days=REVIEW_INTERVAL_DAYS)


def plan_history(user: User) -> list[tuple[Plan, PlanAdjustment | None]]:
    """Every plan version (newest first) with the adjustment that created it."""
    plans_ = db.session.scalars(
        select(Plan).where(Plan.user_id == user.id).order_by(Plan.version.desc())
    ).all()
    adjustments = db.session.scalars(
        select(PlanAdjustment).where(PlanAdjustment.user_id == user.id).order_by(PlanAdjustment.id)
    ).all()
    by_plan = {item.plan_id: item for item in adjustments}
    return [(plan, by_plan.get(plan.id)) for plan in plans_]


def today_targets(plan: Plan) -> dict[str, Any]:
    """Calories and macros for today: base plan plus, with carb cycling, both kinds of day."""
    base = {
        "calories": plan.calorie_target,
        "protein_g": round(plan.protein_g),
        "carbs_g": round(plan.carbs_g),
        "fat_g": round(plan.fat_g),
    }
    cycle = plan.details.get("carb_cycle")
    if not isinstance(cycle, dict):
        return {"base": base, "cycle": None}
    return {
        "base": base,
        "cycle": {
            "high": cycle.get("high_day", {}),
            "low": cycle.get("low_day", {}),
            "training_days": cycle.get("training_days"),
        },
    }


def usable_alternatives(
    item: RoutineExercise, profile: Profile, equipment: frozenset[str]
) -> list[Exercise]:
    """Catalogue alternatives of a prescribed exercise the person can actually do."""
    injuries = tuple(InjuryInput(injury.area, injury.severity) for injury in profile.injuries)
    ceiling = catalog.allowed_level(profile.training_experience)
    disliked = set(profile.disliked_exercises)
    result: list[Exercise] = []
    for link in item.exercise.alternatives:
        row = link.alternative
        if not row.is_active or row.slug in disliked:
            continue
        info = exercise_info(row, {})
        if (
            catalog.equipment_available(info, equipment)
            and not catalog.is_contraindicated(info, injuries)
            and catalog.level_ok(info, ceiling)
        ):
            result.append(row)
    return result


def image_frames(exercise: Exercise) -> list[str]:
    """Static paths of the start and end illustrations (empty when there is no image)."""
    if not exercise.image_path:
        return []
    first = exercise.image_path
    second = first.replace("/0.jpg", "/1.jpg")
    return [first, second] if second != first else [first]
