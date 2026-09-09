"""The daily diary: weight, intake and activity per day, plus the weekly measurements."""

from __future__ import annotations

from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required
from werkzeug.wrappers import Response as WerkzeugResponse

from app import labels
from app.blueprints.tracking.forms import (
    ActivityForm,
    IntakeForm,
    MeasurementForm,
    WeightForm,
)
from app.engine.enums import BodyFatMethod, CardioKind
from app.extensions import db
from app.services import adjustments, onboarding, plans, tracking

# "/registro" ya es el alta de cuenta (auth.register): el diario vive en "/diario".
bp = Blueprint("tracking", __name__, url_prefix="/diario")


def _requested_day() -> date:
    """The day from ``?fecha=`` (today when absent, malformed or in the future)."""
    today = current_user.today()
    raw = request.args.get("fecha")
    if not raw:
        return today
    try:
        chosen = date.fromisoformat(raw)
    except ValueError:
        return today
    return min(chosen, today)


def _steps_target() -> int | None:
    plan = plans.active_plan(current_user)
    profile = onboarding.current_profile(current_user)
    if plan is None or profile is None:
        return None
    return adjustments.steps_target_for(plan, profile)


def _diary_page(day: date, **overrides: object) -> str:
    """Render the diary for ``day``, keeping any form that failed validation."""
    entry = tracking.entry_for(current_user, day)
    forms = {
        "weight_form": WeightForm(day=day, weight_kg=entry.weight_kg),
        "intake_form": IntakeForm(
            day=day,
            calories=entry.calories,
            protein_g=entry.protein_g,
            carbs_g=entry.carbs_g,
            fat_g=entry.fat_g,
            adherence_pct=entry.adherence_pct,
        ),
        "activity_form": ActivityForm(
            day=day,
            steps=entry.steps,
            cardio_kind=entry.cardio_kind.value if entry.cardio_kind else "",
            cardio_minutes=entry.cardio_minutes,
        ),
    }
    forms.update(overrides)
    return render_template(
        "tracking/diary.html",
        day=day,
        today=current_user.today(),
        rows=tracking.diary_rows(current_user, current_user.today()),
        steps_target=_steps_target(),
        labels=labels,
        **forms,
    )


@bp.get("")
@login_required
def diary() -> str:
    """Everything logged for one day, plus the last two weeks."""
    return _diary_page(_requested_day())


@bp.post("/peso")
@login_required
def save_weight() -> str | WerkzeugResponse:
    """Record the weigh-in of a day (saving it again replaces it)."""
    form = WeightForm()
    if not form.validate_on_submit():
        return _diary_page(form.day.data or current_user.today(), weight_form=form)
    day = form.day.data
    tracking.upsert_weight(
        current_user, day, float(form.weight_kg.data or 0), (form.notes.data or "").strip() or None
    )
    db.session.commit()
    flash(_("Peso guardado: %(kg)s kg.", kg=form.weight_kg.data), "success")
    return redirect(url_for("tracking.diary", fecha=day.isoformat()))


@bp.post("/ingesta")
@login_required
def save_intake() -> str | WerkzeugResponse:
    """Record what was eaten on a day."""
    form = IntakeForm()
    if not form.validate_on_submit():
        return _diary_page(form.day.data or current_user.today(), intake_form=form)
    day = form.day.data
    tracking.upsert_intake(
        current_user,
        day,
        int(form.calories.data or 0),
        protein_g=form.protein_g.data,
        carbs_g=form.carbs_g.data,
        fat_g=form.fat_g.data,
        adherence_pct=form.adherence_pct.data,
        notes=(form.notes.data or "").strip() or None,
    )
    db.session.commit()
    flash(_("Ingesta guardada: %(kcal)s kcal.", kcal=form.calories.data), "success")
    return redirect(url_for("tracking.diary", fecha=day.isoformat()))


@bp.post("/actividad")
@login_required
def save_activity() -> str | WerkzeugResponse:
    """Record steps and cardio of a day."""
    form = ActivityForm()
    if not form.validate_on_submit():
        return _diary_page(form.day.data or current_user.today(), activity_form=form)
    day = form.day.data
    tracking.upsert_activity(
        current_user,
        day,
        form.steps.data,
        cardio_kind=CardioKind(form.cardio_kind.data) if form.cardio_kind.data else None,
        cardio_minutes=form.cardio_minutes.data,
        notes=(form.notes.data or "").strip() or None,
    )
    db.session.commit()
    flash(_("Actividad guardada."), "success")
    return redirect(url_for("tracking.diary", fecha=day.isoformat()))


@bp.route("/perimetros", methods=["GET", "POST"])
@login_required
def measurements() -> str | WerkzeugResponse:
    """Weekly tape measures and their history."""
    form = MeasurementForm() if request.method == "POST" else MeasurementForm(day=_requested_day())
    if form.validate_on_submit():
        tracking.upsert_measurement(
            current_user,
            form.day.data,
            neck_cm=form.neck_cm.data,
            chest_cm=form.chest_cm.data,
            waist_cm=form.waist_cm.data,
            hip_cm=form.hip_cm.data,
            arm_cm=form.arm_cm.data,
            thigh_cm=form.thigh_cm.data,
            calf_cm=form.calf_cm.data,
            body_fat_pct=form.body_fat_pct.data,
            body_fat_method=BodyFatMethod(form.body_fat_method.data),
            notes=(form.notes.data or "").strip() or None,
        )
        db.session.commit()
        flash(_("Medidas guardadas."), "success")
        return redirect(url_for("tracking.measurements"))
    return render_template(
        "tracking/measurements.html",
        form=form,
        rows=tracking.recent_measurements(current_user),
        labels=labels,
    )
