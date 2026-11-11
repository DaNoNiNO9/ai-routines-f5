"""Multi-step questionnaire: one page per block, a review page and the result."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_babel import lazy_gettext as _l
from flask_babel import ngettext
from flask_login import current_user, login_required
from werkzeug.wrappers import Response as WerkzeugResponse

from app import formatting, labels
from app.blueprints.onboarding.forms import INJURY_FIELDS, STEP_FORMS
from app.engine.enums import TrainingLocation
from app.engine.equipment_presets import preset_for
from app.engine.nutrition import build_nutrition_plan
from app.engine.routines.generator import build_routine
from app.services import onboarding, plans
from app.services.onboarding import (
    DATE_FIELDS,
    LAST_STEP,
    STEP_BY_NUMBER,
    STEPS,
    OnboardingError,
    Step,
)

logger = logging.getLogger(__name__)

bp = Blueprint("onboarding", __name__, url_prefix="/cuestionario")

REVIEW_STEP = Step(LAST_STEP + 1, "review", _l("Revisión"), ())
ALL_STEPS = (*STEPS, REVIEW_STEP)

ERROR_TEXTS = {
    "incomplete": _l("Faltan respuestas: revisa los pasos marcados."),
    "invalid": _l("Alguna respuesta no es válida. Revisa los pasos y vuelve a intentarlo."),
    "engine": _l(
        "No se pudo generar el plan con estos datos. Lo hemos registrado; "
        "revisa las respuestas o inténtalo más tarde."
    ),
}


def _form_defaults(number: int, data: dict[str, Any]) -> dict[str, Any]:
    """Draft values shaped for ``Form(data=...)`` (dates as dates, injuries as selects)."""
    defaults: dict[str, Any] = {}
    for key, value in data.items():
        if key in DATE_FIELDS and isinstance(value, str):
            defaults[key] = date.fromisoformat(value)
        else:
            defaults[key] = value
    if number == 4:
        location = data.get("training_location")
        if "equipment" not in data or data.get("equipment_for_location") != location:
            defaults["equipment"] = sorted(preset_for(location)) if location else ["body_only"]
        for area, name in INJURY_FIELDS.items():
            defaults[name] = (data.get("injuries") or {}).get(area.value, "none")
        defaults["has_injuries"] = bool(data.get("injuries"))
    return defaults


def _step_context(number: int, form: Any, data: dict[str, Any] | None = None) -> dict[str, Any]:
    context: dict[str, Any] = {}
    if number == 4:
        groups = onboarding.equipment_groups()
        form.equipment.choices = [(code, name) for _label, items in groups for code, name in items]
        location = (data or {}).get("training_location")
        context["equipment_groups"] = groups
        context["injury_fields"] = list(INJURY_FIELDS.items())
        context["location"] = TrainingLocation(location) if location else None
        context["equipment_hints"] = labels.EQUIPMENT_HINT
    return context


@bp.get("")
@login_required
def index() -> WerkzeugResponse:
    """Continue where the person left off (or start)."""
    draft = onboarding.start_draft(current_user)
    missing = onboarding.first_incomplete_step(draft.data)
    if missing is None:
        return redirect(url_for("onboarding.review"))
    return redirect(url_for("onboarding.step", number=min(missing, draft.step + 1)))


@bp.route("/paso/<int:number>", methods=["GET", "POST"])
@login_required
def step(number: int) -> str | WerkzeugResponse:
    """Show and save one block of answers."""
    current = STEP_BY_NUMBER.get(number)
    if current is None:
        abort(404)
    draft = onboarding.start_draft(current_user)
    if number > draft.step + 1:
        flash(_("Completa primero los pasos anteriores."), "warning")
        return redirect(url_for("onboarding.step", number=draft.step + 1))
    form_class = STEP_FORMS[number]
    form = (
        form_class()
        if request.method == "POST"
        else form_class(data=_form_defaults(number, draft.data))
    )
    context = _step_context(number, form, draft.data)
    if form.validate_on_submit():
        values = form.to_data()
        ready = True
        if number == 4:
            values["equipment_for_location"] = draft.data.get("training_location")
        if ready:
            onboarding.save_step(draft, number, values)
            if number == LAST_STEP:
                return redirect(url_for("onboarding.review"))
            return redirect(url_for("onboarding.step", number=number + 1))
    return render_template(
        f"onboarding/step_{current.key}.html",
        form=form,
        step=current,
        steps=ALL_STEPS,
        draft=draft,
        labels=labels,
        **context,
    )


def _summary(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Human-readable rows per block for the review page."""
    lookup = onboarding.exercise_lookup()
    equipment_names = dict(onboarding.equipment_names())
    yes_no = lambda value: _("Sí") if value else _("No")  # noqa: E731 - tiny local helper
    injuries = data.get("injuries") or {}
    rows_body = [
        (_("Sexo"), labels.label(labels.SEX, data.get("sex"))),
        (_("Fecha de nacimiento"), formatting.fdate(data.get("birth_date"), "long")),
        (_("Altura"), f"{formatting.num(data.get('height_cm'))} cm"),
        (_("Peso"), formatting.kg(data.get("weight_kg"))),
        (
            _("Perímetros"),
            ", ".join(
                f"{label}: {formatting.num(data[key])} cm"
                for key, label in (
                    ("neck_cm", _("cuello")),
                    ("waist_cm", _("cintura")),
                    ("hip_cm", _("cadera")),
                )
                if data.get(key)
            )
            or _("no indicados"),
        ),
        (
            _("Grasa corporal"),
            (
                f"{formatting.num(data['body_fat_pct'])} % · "
                f"{labels.label(labels.BODY_FAT_METHOD, data.get('body_fat_method'))}"
                if data.get("body_fat_pct")
                else _("no indicada")
            ),
        ),
    ]
    other = data.get("other_activity_sessions_per_week") or 0
    rows_activity = [
        (_("Trabajo"), labels.label(labels.JOB_ACTIVITY, data.get("job_activity"))),
        (
            _("Pasos diarios"),
            formatting.num(data["daily_steps"], 0)
            if data.get("daily_steps")
            else _("no indicados"),
        ),
        (_("Sueño"), f"{formatting.num(data.get('sleep_hours'))} h"),
        (_("Estrés"), labels.label(labels.STRESS_LEVEL, data.get("stress_level"))),
        (
            _("Otra actividad"),
            (
                f"{data.get('other_activity_type') or _('actividad')}: {other} {formatting.TIMES} "
                f"{data.get('other_activity_minutes')} min, "
                f"{labels.label(labels.ACTIVITY_INTENSITY, data.get('other_activity_intensity'))}"
                if other
                else _("ninguna")
            ),
        ),
    ]
    rows_training = [
        (
            _("Experiencia"),
            labels.label(labels.TRAINING_EXPERIENCE, data.get("training_experience")),
        ),
        (
            _("Frecuencia"),
            ngettext(
                "%(num)s día a la semana, %(minutes)s min",
                "%(num)s días a la semana, %(minutes)s min",
                int(data.get("training_days_per_week") or 0),
                minutes=data.get("session_minutes"),
            ),
        ),
        (_("Lugar"), labels.label(labels.TRAINING_LOCATION, data.get("training_location"))),
        (_("Hora"), labels.label(labels.TRAINING_TIME, data.get("training_time"))),
    ]
    rows_equipment = [
        (
            _("Material"),
            ", ".join(equipment_names.get(code, code) for code in data.get("equipment", [])),
        ),
        (
            _("Prioridad"),
            ", ".join(
                labels.label(labels.MUSCLE_GROUP, m) for m in data.get("priority_muscles", [])
            )
            or _("ninguna"),
        ),
        (
            _("Molestias o lesiones"),
            ", ".join(
                f"{labels.label(labels.INJURY_AREA, area)} ({labels.label(labels.SEVERITY, sev)})"
                for area, sev in injuries.items()
            )
            or _("ninguna"),
        ),
    ]
    # Los ejercicios marcados se eligen desde la rutina: aquí solo se enseñan si hay.
    for etiqueta, clave in (
        (_("Ejercicios que evitar"), "disliked_exercises"),
        (_("Ejercicios preferidos"), "preferred_exercises"),
    ):
        marcados = ", ".join(lookup.name_of(s) or s for s in data.get(clave, []))
        if marcados:
            rows_equipment.append((etiqueta, marcados))
    rows_goal = [
        (_("Objetivo"), labels.label(labels.GOAL, data.get("goal"))),
        (_("Ritmo"), labels.label(labels.AGGRESSIVENESS, data.get("aggressiveness"))),
        (
            _("Peso objetivo"),
            formatting.kg(data["target_weight_kg"])
            if data.get("target_weight_kg")
            else _("no indicado"),
        ),
        (
            _("Fecha objetivo"),
            formatting.fdate(data["target_date"], "long")
            if data.get("target_date")
            else _("sin fecha"),
        ),
    ]
    rows_nutrition = [
        (_("Comidas al día"), data.get("meals_per_day")),
        (_("Alimentación"), labels.label(labels.DIET_PATTERN, data.get("diet_pattern"))),
        (_("Más hidratos los días de entreno"), yes_no(data.get("wants_carb_cycling"))),
        (
            _("Alcohol"),
            ngettext(
                "%(num)s bebida a la semana",
                "%(num)s bebidas a la semana",
                int(data.get("alcohol_drinks_per_week") or 0),
            ),
        ),
    ]
    rows_health = [
        (_("Embarazo o lactancia"), yes_no(data.get("is_pregnant_or_breastfeeding"))),
        (
            _("Antecedentes de trastorno alimentario"),
            yes_no(data.get("has_eating_disorder_history")),
        ),
    ]
    rows = (
        rows_body,
        rows_activity,
        rows_training,
        rows_equipment,
        rows_goal,
        rows_nutrition,
        rows_health,
    )
    return [{"step": step, "rows": block} for step, block in zip(STEPS, rows, strict=True)]


@bp.route("/revisar", methods=["GET", "POST"])
@login_required
def review() -> str | WerkzeugResponse:
    """Check every answer, then generate the plan."""
    draft = onboarding.start_draft(current_user)
    missing = onboarding.first_incomplete_step(draft.data)
    if missing is not None:
        flash(_("Faltan respuestas en el paso %(n)s.", n=missing), "warning")
        return redirect(url_for("onboarding.step", number=missing))
    if request.method == "POST":
        try:
            result = onboarding.complete(current_user, draft, current_user.today())
        except OnboardingError as exc:
            flash(str(ERROR_TEXTS.get(exc.reason, ERROR_TEXTS["engine"])), "error")
            return redirect(url_for("onboarding.review"))
        if result.is_blocked:
            flash(_("Hemos guardado tus respuestas, pero no podemos darte un plan."), "warning")
        elif result.routine is None:
            flash(
                _("Plan de nutrición listo. No pudimos montar una rutina con ese material."),
                "warning",
            )
        else:
            flash(_("Plan y rutina generados."), "success")
        return redirect(url_for("onboarding.result"))
    return render_template(
        "onboarding/review.html",
        sections=_summary(draft.data),
        step=REVIEW_STEP,
        steps=ALL_STEPS,
        draft=draft,
    )


@bp.get("/resultado")
@login_required
def result() -> str | WerkzeugResponse:
    """The plan and routine in force, or the reasons there is none."""
    profile = onboarding.current_profile(current_user)
    if profile is None:
        return redirect(url_for("onboarding.index"))
    today = current_user.today()
    plan = plans.active_plan(current_user)
    routine = plans.active_routine(current_user)
    blocked_reasons: list[str] = []
    routine_reasons: list[str] = []
    if plan is None:
        nutrition = build_nutrition_plan(plans.nutrition_inputs(profile, today))
        blocked_reasons = [item["text"] for item in plans.messages_for(nutrition.blocked_reasons)]
    elif routine is None:
        catalogue, _by_slug = plans.load_catalogue()
        equipment = frozenset(item.code for item in current_user.equipment)
        routine_plan = build_routine(plans.routine_inputs(profile, equipment, None), catalogue)
        routine_reasons = [
            item["text"] for item in plans.messages_for(routine_plan.blocked_reasons)
        ]
    return render_template(
        "onboarding/result.html",
        profile=profile,
        plan=plan,
        routine=routine,
        blocked_reasons=blocked_reasons,
        routine_reasons=routine_reasons,
        labels=labels,
        plan_messages=plans.messages_of(plan.details) if plan else [],
        routine_messages=plans.messages_of(routine.details) if routine else [],
    )
