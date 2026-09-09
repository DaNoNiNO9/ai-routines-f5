"""Show what the adjustment engine sees and apply its decision on request."""

from __future__ import annotations

import logging

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_babel import gettext as _
from flask_babel import lazy_gettext as _l
from flask_login import current_user, login_required
from werkzeug.wrappers import Response as WerkzeugResponse

from app import labels
from app.engine.safety import SafetyError
from app.extensions import db
from app.services import adjustments, dashboard, onboarding
from app.services.adjustments import ReviewError

logger = logging.getLogger(__name__)

bp = Blueprint("review", __name__, url_prefix="/revision")

ACTION_TEXTS = {
    "wait": _l("Esperar"),
    "keep": _l("Mantener el plan"),
    "adherence": _l("Revisar la adherencia antes de tocar nada"),
    "reduce_calories": _l("Bajar calorías"),
    "increase_calories": _l("Subir calorías"),
    "add_steps": _l("Añadir pasos"),
    "refeed": _l("Día de recarga"),
    "diet_break": _l("Descanso de dieta"),
}
ERROR_TEXTS = {
    "no_plan": _l("No hay un plan activo que revisar."),
    "no_weights": _l("Sin pesajes no hay nada que revisar: registra tu peso a diario."),
    "not_due": _l("Todavía no toca la revisión."),
    "blocked": _l(
        "Con tu peso actual el plan ya no es seguro; actualiza el cuestionario para revisarlo."
    ),
}


@bp.get("")
@login_required
def index() -> str | WerkzeugResponse:
    """What the engine would decide today, and the reviews already recorded."""
    profile = onboarding.current_profile(current_user)
    if profile is None:
        return redirect(url_for("onboarding.index"))
    today = current_user.today()
    try:
        current = adjustments.preview(current_user, today)
    except ReviewError as exc:
        return render_template(
            "review/index.html",
            preview=None,
            error=str(ERROR_TEXTS.get(exc.reason, exc.reason)),
            records=[],
            today=today,
            labels=labels,
            action_texts=ACTION_TEXTS,
        )
    return render_template(
        "review/index.html",
        preview=current,
        error=None,
        records=list(reversed(adjustments.review_records(current.plan))),
        next_review=dashboard.next_review_on(current.plan),
        today=today,
        labels=labels,
        action_texts=ACTION_TEXTS,
    )


@bp.post("/aplicar")
@login_required
def apply() -> WerkzeugResponse:
    """Store the decision (new plan version, steps change or a no-change review)."""
    today = current_user.today()
    try:
        result = adjustments.apply(current_user, today)
    except ReviewError as exc:
        db.session.rollback()
        flash(str(ERROR_TEXTS.get(exc.reason, exc.reason)), "warning")
        return redirect(url_for("review.index"))
    except SafetyError:
        db.session.rollback()
        logger.exception("Review produced an unsafe plan for user %s", current_user.id)
        flash(_("No se pudo aplicar la revisión: lo hemos registrado."), "error")
        return redirect(url_for("review.index"))
    db.session.commit()
    if result.created_new_plan:
        flash(
            _(
                "Plan actualizado a la versión %(v)s: %(kcal)s kcal.",
                v=result.plan_after.version,
                kcal=result.plan_after.calorie_target,
            ),
            "success",
        )
        return redirect(url_for("nutrition.plan"))
    flash(
        _(
            "Revisión registrada: %(text)s",
            text=ACTION_TEXTS.get(result.decision.action, result.decision.action),
        ),
        "success",
    )
    return redirect(url_for("review.index"))
