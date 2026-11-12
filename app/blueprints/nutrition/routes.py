"""The nutrition plan in full: targets, macros, meals, how it was calculated, history."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_babel import ngettext
from flask_login import current_user, login_required
from werkzeug.wrappers import Response as WerkzeugResponse

from app import labels
from app.blueprints.billing.routes import pro_required
from app.engine.nutrition import build_nutrition_plan
from app.extensions import db
from app.services import adjustments, dashboard, onboarding, plans
from app.services import menu as menu_service

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
        describe=adjustments.describe,
        next_review=dashboard.next_review_on(active) if active else None,
        macro_chart=_macro_chart(details) if active else None,
        tdee_chart=_tdee_chart(details) if active else None,
        labels=labels,
        today=today,
    )


def _variant() -> int:
    try:
        return max(0, min(999, int(request.values.get("variante", 0))))
    except ValueError:
        return 0


def _week() -> tuple[Any, Any, list[menu_service.ServedDay], int] | WerkzeugResponse:
    profile = onboarding.current_profile(current_user)
    plan = plans.active_plan(current_user)
    if profile is None or plan is None or not plan.meals:
        return redirect(url_for("nutrition.plan"))
    variant = _variant()
    days = menu_service.week_for(current_user, plan, profile, current_user.today(), variant)
    return profile, plan, days, variant


@bp.get("/menu")
@login_required
@pro_required
def menu() -> str | WerkzeugResponse:
    """Seven days of real meals that add up to the plan."""
    built = _week()
    if not isinstance(built, tuple):
        return built
    profile, plan, days, variant = built
    return render_template(
        "nutrition/menu.html",
        profile=profile,
        plan=plan,
        days=days,
        variant=variant,
        summary=menu_service.summary,
        today=current_user.today(),
        labels=labels,
    )


@bp.post("/menu/apuntar")
@login_required
@pro_required
def log_meal() -> WerkzeugResponse:
    """Put today's planned meal in the diary, food by food."""
    built = _week()
    if not isinstance(built, tuple):
        return built
    _profile, _plan, days, variant = built
    try:
        position = int(request.form.get("comida", ""))
    except ValueError:
        abort(400)
    plate = next((item for item in days[0].plates if item.target.position == position), None)
    if plate is None:
        abort(400)
    added = menu_service.log_plate(current_user, days[0].day, plate)
    db.session.commit()
    flash(
        ngettext(
            "Apuntado en el diario: %(meal)s, %(num)s alimento.",
            "Apuntado en el diario: %(meal)s, %(num)s alimentos.",
            added,
            meal=plate.target.name,
        ),
        "success",
    )
    return redirect(url_for("nutrition.menu", variante=variant))


@bp.get("/menu/compra")
@login_required
@pro_required
def shopping() -> str | WerkzeugResponse:
    """What to buy for the week's menu, by aisle."""
    built = _week()
    if not isinstance(built, tuple):
        return built
    _profile, _plan, days, variant = built
    return render_template(
        "nutrition/shopping.html", aisles=menu_service.shopping(days), variant=variant
    )
