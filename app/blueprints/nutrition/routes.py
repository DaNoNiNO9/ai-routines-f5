"""The nutrition plan in full: targets, macros, meals, how it was calculated, history."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, redirect, render_template, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required
from werkzeug.wrappers import Response as WerkzeugResponse

from app import labels
from app.engine.nutrition import build_nutrition_plan
from app.services import dashboard, onboarding, plans

bp = Blueprint("nutrition", __name__, url_prefix="/nutricion")


def _macro_chart(details: dict[str, Any]) -> dict[str, Any]:
    macros = details.get("macros") or {}
    return {
        "labels": [str(_("Proteína")), str(_("Carbohidratos")), str(_("Grasa"))],
        "values": [
            4 * (macros.get("protein_g") or 0),
            4 * (macros.get("carbs_g") or 0),
            9 * (macros.get("fat_g") or 0),
        ],
    }


def _tdee_chart(details: dict[str, Any]) -> dict[str, Any]:
    spent = details.get("expenditure") or {}
    return {
        "labels": [
            str(_("Basal (BMR)")),
            str(_("Actividad diaria (NEAT)")),
            str(_("Ejercicio (EAT)")),
            str(_("Digestión (TEF)")),
        ],
        "values": [
            round(spent.get("bmr_kcal") or 0),
            round(spent.get("neat_kcal") or 0),
            round(spent.get("eat_kcal") or 0),
            round(spent.get("tef_at_maintenance_kcal") or 0),
        ],
    }


@bp.get("")
@login_required
def plan() -> str | WerkzeugResponse:
    """Everything about the plan in force (or why there is none)."""
    profile = onboarding.current_profile(current_user)
    if profile is None:
        return redirect(url_for("onboarding.index"))
    today = current_user.today()
    active = plans.active_plan(current_user)
    blocked_reasons: list[str] = []
    if active is None:
        nutrition = build_nutrition_plan(plans.nutrition_inputs(profile, today))
        blocked_reasons = [item["text"] for item in plans.messages_for(nutrition.blocked_reasons)]
    details = active.details if active else {}
    return render_template(
        "nutrition/plan.html",
        profile=profile,
        plan=active,
        d=details,
        messages=plans.messages_of(details) if active else [],
        blocked_reasons=blocked_reasons,
        history=dashboard.plan_history(current_user),
        next_review=dashboard.next_review_on(active) if active else None,
        macro_chart=_macro_chart(details) if active else None,
        tdee_chart=_tdee_chart(details) if active else None,
        labels=labels,
        today=today,
    )
