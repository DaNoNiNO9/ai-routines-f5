"""The daily diary: weight, intake and activity per day, plus the weekly measurements."""

from __future__ import annotations

from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_babel import lazy_gettext as _l
from flask_babel import ngettext
from flask_login import current_user, login_required
from werkzeug.wrappers import Response as WerkzeugResponse

from app import formatting, labels
from app.blueprints.billing.routes import pro_required
from app.blueprints.tracking.forms import (
    ActivityForm,
    IntakeForm,
    MeasurementForm,
    WeightForm,
)
from app.engine.enums import BodyFatMethod, CardioKind
from app.extensions import db
from app.services import adjustments, billing, dashboard, onboarding, plans, tracking
from app.services import food as food_service

# "/registro" ya es el alta de cuenta (auth.register): el diario vive en "/diario".
bp = Blueprint("tracking", __name__, url_prefix="/diario")


def _requested_day(raw: str | None = None) -> date:
    """The day from ``?fecha=`` (today when absent, malformed or in the future)."""
    today = current_user.today()
    raw = raw if raw is not None else request.args.get("fecha")
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
    pro = billing.is_pro(current_user)
    foods = food_service.entries(current_user, day) if pro else []
    plan = plans.active_plan(current_user)
    return render_template(
        "tracking/diary.html",
        day=day,
        foods=foods,
        food_totals=food_service.totals(foods),
        targets=dashboard.target_for_day(
            dashboard.today_targets(plan), dashboard.trains_on(current_user, day)
        )
        if plan
        else None,
        yesterday_foods=pro
        and not foods
        and bool(food_service.entries(current_user, day - timedelta(days=1))),
        today=current_user.today(),
        rows=tracking.diary_rows(current_user, current_user.today()),
        steps_target=_steps_target(),
        labels=labels,
        **forms,
    )


def _rejected(form: object, **overrides: object) -> str:
    """Re-render the diary explaining why it was not saved.

    The day travels in a hidden field, so ``hidden_tag()`` would swallow its
    errors and the page would come back unchanged with no explanation.
    """
    for message in form.day.errors:
        flash(str(message), "error")
    return _diary_page(form.day.data or current_user.today(), **overrides)


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
        return _rejected(form, weight_form=form)
    day = form.day.data
    tracking.upsert_weight(
        current_user, day, float(form.weight_kg.data or 0), (form.notes.data or "").strip() or None
    )
    db.session.commit()
    flash(_("Peso guardado: %(kg)s.", kg=formatting.kg(form.weight_kg.data)), "success")
    return redirect(url_for("tracking.diary", fecha=day.isoformat()))


@bp.post("/ingesta")
@login_required
def save_intake() -> str | WerkzeugResponse:
    """Record what was eaten on a day."""
    form = IntakeForm()
    if not form.validate_on_submit():
        return _rejected(form, intake_form=form)
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
    if food_service.entries(current_user, day):
        # Con alimentos apuntados, el total sale de ellos: aquí solo cuenta el %.
        food_service.refresh_intake(current_user, day)
        db.session.commit()
        flash(_("Guardado."), "success")
        return redirect(url_for("tracking.diary", fecha=day.isoformat()))
    db.session.commit()
    flash(_("Ingesta guardada: %(kcal)s kcal.", kcal=form.calories.data), "success")
    return redirect(url_for("tracking.diary", fecha=day.isoformat()))


@bp.post("/actividad")
@login_required
def save_activity() -> str | WerkzeugResponse:
    """Record steps and cardio of a day."""
    form = ActivityForm()
    if not form.validate_on_submit():
        return _rejected(form, activity_form=form)
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


# --- Alimentos (Alza Pro) -------------------------------------------------------

FOOD_ERRORS = {
    "off_unreachable": _l(
        "Open Food Facts no responde ahora mismo. La tabla básica sigue funcionando."
    ),
    "bad_barcode": _l("Ese código de barras no parece válido: son de 8 a 13 cifras."),
    "barcode_not_found": _l("No encontramos ese código en Open Food Facts. Búscalo por su nombre."),
    "barcode_incomplete": _l(
        "Ese producto no tiene todos sus valores en Open Food Facts. Búscalo por su nombre."
    ),
    "bad_grams": _l("Indica los gramos: entre 1 y 5000."),
    "unknown_food": _l("No encontramos ese alimento."),
}


def _food_from(source: str, code: str) -> food_service.Food:
    """Re-read a food from its source: values never come from the browser."""
    if source == "basic":
        found = food_service.basic_food(code)
        if found is None:
            raise food_service.FoodError("unknown_food")
        return found
    if source == "off":
        return food_service.by_barcode(code)
    raise food_service.FoodError("unknown_food")


@bp.get("/alimentos")
@login_required
@pro_required
def foods() -> str:
    """Search foods, scan a barcode, or pick one of your usual ones."""
    day = _requested_day()
    query = (request.args.get("q") or "").strip()[:80]
    barcode = (request.args.get("codigo") or "").strip()[:20]
    results: list[food_service.Food] = []
    off_down = False
    error = None
    if barcode:
        try:
            results = [food_service.by_barcode(barcode)]
        except food_service.FoodError as exc:
            error = str(FOOD_ERRORS.get(exc.reason, FOOD_ERRORS["unknown_food"]))
    elif query:
        results, off_down = food_service.search(query)
    return render_template(
        "tracking/foods.html",
        day=day,
        today=current_user.today(),
        query=query,
        barcode=barcode,
        results=results,
        off_down=off_down,
        error=error,
        usual=food_service.usual(current_user) if not (query or barcode) else [],
    )


@bp.post("/alimentos")
@login_required
@pro_required
def add_food() -> WerkzeugResponse:
    """Log a food on a day, in grams."""
    day = _requested_day(request.form.get("fecha"))
    try:
        grams = float((request.form.get("grams") or "").replace(",", "."))
    except ValueError:
        grams = 0
    try:
        chosen = _food_from(request.form.get("source", ""), request.form.get("code", ""))
        entry = food_service.add(current_user, day, chosen, grams)
    except food_service.FoodError as exc:
        db.session.rollback()
        flash(str(FOOD_ERRORS.get(exc.reason, FOOD_ERRORS["unknown_food"])), "error")
        return redirect(url_for("tracking.foods", fecha=day.isoformat()))
    db.session.commit()
    flash(
        _(
            "Apuntado: %(name)s, %(grams)s g (%(kcal)s kcal).",
            name=entry.name,
            grams=formatting.num(entry.grams),
            kcal=formatting.num(entry.kcal, 0),
        ),
        "success",
    )
    return redirect(url_for("tracking.diary", fecha=day.isoformat()) + "#comida")


@bp.post("/alimentos/<int:entry_id>/borrar")
@login_required
def delete_food(entry_id: int) -> WerkzeugResponse:
    """Remove a logged food."""
    day = food_service.remove(current_user, entry_id)
    if day is None:
        return redirect(url_for("tracking.diary"))
    db.session.commit()
    return redirect(url_for("tracking.diary", fecha=day.isoformat()) + "#comida")


@bp.post("/alimentos/copiar")
@login_required
@pro_required
def copy_yesterday() -> WerkzeugResponse:
    """Log again what was eaten the day before."""
    day = _requested_day(request.form.get("fecha"))
    copied = food_service.copy_day(current_user, day - timedelta(days=1), day)
    db.session.commit()
    flash(
        ngettext(
            "%(num)s alimento copiado de ayer.", "%(num)s alimentos copiados de ayer.", copied
        ),
        "success",
    )
    return redirect(url_for("tracking.diary", fecha=day.isoformat()) + "#comida")
