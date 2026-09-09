"""Signed-in area. Phase 7 ships the shell; Phase 9 fills it with the plan."""

from __future__ import annotations

from flask import Blueprint, render_template
from flask_login import current_user, login_required

bp = Blueprint("dashboard", __name__)


@bp.get("/panel")
@login_required
def index() -> str:
    """Home of a signed-in user."""
    return render_template("dashboard/index.html", user=current_user)
