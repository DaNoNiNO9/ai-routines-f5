"""Signed-in home: today's numbers, next session, weight trend and next review."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, render_template
from flask_babel import gettext as _
from flask_login import current_user, login_required

from app import labels
from app.services import billing, dashboard, onboarding, plans, workouts

bp = Blueprint("dashboard", __name__)

MIN_POINTS_FOR_CHART = 2


@bp.get("/panel")
@login_required
def index() -> str:
    """Home of a signed-in user (a call to action until the questionnaire is done)."""
    profile = onboarding.current_profile(current_user)
    today = current_user.today()
    context: dict[str, Any] = {
        "user": current_user,
        "profile": profile,
        "draft": onboarding.get_draft(current_user),
        "labels": labels,
        "today": today,
        "plan": None,
        "routine": None,
        "weight_chart": None,
    }
    if profile is not None:
        plan = plans.active_plan(current_user)
        routine = plans.active_routine(current_user)
        weights = dashboard.weight_series(current_user, today)
        chart = None
        if len(weights.points) >= MIN_POINTS_FOR_CHART:
            chart = {
                **weights.to_chart(),
                "weight_label": _("Peso"),
                "average_label": _("Media de 7 días"),
            }
        context.update(
            plan=plan,
            routine=routine,
            targets=dashboard.today_targets(plan) if plan else None,
            training_today=dashboard.trains_on(current_user, today),
            next_day=dashboard.next_routine_day(current_user, routine),
            weights=weights,
            weight_chart=chart,
            arrival=dashboard.arrival_card(profile, plan, weights, today)
            if billing.is_pro(current_user)
            else None,
            streak=workouts.weekly_streak(current_user, today, len(routine.days))
            if routine
            else None,
            next_review=dashboard.next_review_on(plan) if plan else None,
        )
    return render_template("dashboard/index.html", **context)
