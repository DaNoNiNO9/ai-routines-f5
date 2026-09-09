"""Signed-in area. Phase 9 fills it with charts; for now it points to the plan."""

from __future__ import annotations

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app import labels
from app.services import onboarding, plans

bp = Blueprint("dashboard", __name__)


@bp.get("/panel")
@login_required
def index() -> str:
    """Home of a signed-in user."""
    profile = onboarding.current_profile(current_user)
    return render_template(
        "dashboard/index.html",
        user=current_user,
        profile=profile,
        plan=plans.active_plan(current_user) if profile else None,
        routine=plans.active_routine(current_user) if profile else None,
        draft=onboarding.get_draft(current_user),
        labels=labels,
    )
