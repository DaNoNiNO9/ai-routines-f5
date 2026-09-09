"""The routine in force: overview, one page per training day with alternatives."""

from __future__ import annotations

from flask import Blueprint, abort, redirect, render_template, url_for
from flask_login import current_user, login_required
from werkzeug.wrappers import Response as WerkzeugResponse

from app import labels
from app.engine.routines.generator import build_routine
from app.services import dashboard, onboarding, plans

bp = Blueprint("training", __name__, url_prefix="/entrenamiento")


def _routine_reasons(profile) -> list[str]:
    catalogue, _by_slug = plans.load_catalogue()
    equipment = frozenset(item.code for item in current_user.equipment)
    routine_plan = build_routine(plans.routine_inputs(profile, equipment, None), catalogue)
    return [item["text"] for item in plans.messages_for(routine_plan.blocked_reasons)]


@bp.get("")
@login_required
def routine() -> str | WerkzeugResponse:
    """Split, days, weekly volume, cardio and the engine's explanations."""
    profile = onboarding.current_profile(current_user)
    if profile is None:
        return redirect(url_for("onboarding.index"))
    active = plans.active_routine(current_user)
    has_plan = plans.active_plan(current_user) is not None
    reasons: list[str] = []
    if active is None and has_plan:
        reasons = _routine_reasons(profile)
    details = active.details if active else {}
    return render_template(
        "training/routine.html",
        profile=profile,
        routine=active,
        d=details,
        messages=plans.messages_of(details) if active else [],
        reasons=reasons,
        has_plan=has_plan,
        next_day=dashboard.next_routine_day(current_user, active),
        labels=labels,
    )


@bp.get("/dia/<int:index>")
@login_required
def day(index: int) -> str | WerkzeugResponse:
    """One training day: every exercise with its prescription, images and alternatives."""
    profile = onboarding.current_profile(current_user)
    if profile is None:
        return redirect(url_for("onboarding.index"))
    active = plans.active_routine(current_user)
    if active is None:
        return redirect(url_for("training.routine"))
    current = next((item for item in active.days if item.day_index == index), None)
    if current is None:
        abort(404)
    equipment = frozenset(item.code for item in current_user.equipment)
    alternatives = {
        item.id: dashboard.usable_alternatives(item, profile, equipment)
        for item in current.exercises
    }
    frames = {item.id: dashboard.image_frames(item.exercise) for item in current.exercises}
    days = active.days
    position = days.index(current)
    return render_template(
        "training/day.html",
        routine=active,
        day=current,
        alternatives=alternatives,
        frames=frames,
        previous_day=days[position - 1] if position > 0 else None,
        following_day=days[position + 1] if position + 1 < len(days) else None,
        weekly_rir=active.details.get("weekly_rir", []),
        labels=labels,
    )
