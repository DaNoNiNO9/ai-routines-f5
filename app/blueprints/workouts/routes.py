"""Live session, per-set logging, substitutions, closing, history and progress charts."""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_babel import lazy_gettext as _l
from flask_login import current_user, login_required
from werkzeug.wrappers import Response as WerkzeugResponse

from app import labels
from app.blueprints.workouts.forms import FATIGUE_LABELS, FinishForm, SetForm, SubstituteForm
from app.engine.enums import SetType, WorkoutStatus
from app.extensions import db
from app.models import Exercise, Profile, RoutineExercise, WorkoutSession
from app.services import onboarding, plans, workouts
from app.services.workouts import WorkoutError

bp = Blueprint("workouts", __name__, url_prefix="/entreno")

ERROR_TEXTS = {
    "closed": _l("Esa sesión ya está cerrada."),
    "bad_index": _l("Número de serie fuera de rango."),
    "sets_logged": _l("Ya has registrado series de ese ejercicio: no se puede sustituir."),
    "not_an_alternative": _l("Ese ejercicio no es una alternativa válida para ti."),
    "not_found": _l("No encontramos esa serie."),
}


def _profile_or_redirect() -> Profile | WerkzeugResponse:
    profile = onboarding.current_profile(current_user)
    if profile is None:
        return redirect(url_for("onboarding.index"))
    return profile


def _session_or_404(session_id: int) -> WorkoutSession:
    session = workouts.get_session(current_user, session_id)
    if session is None:
        abort(404)
    return session


def _equipment() -> frozenset[str]:
    return frozenset(item.code for item in current_user.equipment)


def _item_of(session: WorkoutSession, routine_exercise_id: int | None) -> RoutineExercise:
    day = session.routine_day
    item = db.session.get(RoutineExercise, routine_exercise_id) if routine_exercise_id else None
    if day is None or item is None or item.routine_day_id != day.id:
        abort(404)
    return item


@bp.post("/empezar/<int:day_index>")
@login_required
def start(day_index: int) -> WerkzeugResponse:
    """Open a session for a routine day (or continue the one in progress)."""
    profile = _profile_or_redirect()
    if not isinstance(profile, Profile):
        return profile
    routine = plans.active_routine(current_user)
    if routine is None:
        flash(_("No tienes una rutina activa."), "warning")
        return redirect(url_for("training.routine"))
    day = next((item for item in routine.days if item.day_index == day_index), None)
    if day is None:
        abort(404)
    session = workouts.start_session(current_user, routine, day, current_user.today())
    db.session.commit()
    if session.routine_day_id != day.id:
        flash(_("Ya tienes una sesión en marcha: termínala o abandónala antes."), "warning")
    return redirect(url_for("workouts.session", session_id=session.id))


@bp.get("/<int:session_id>")
@login_required
def session(session_id: int) -> str | WerkzeugResponse:
    """The live page: every prescribed exercise with its sets."""
    profile = _profile_or_redirect()
    if not isinstance(profile, Profile):
        return profile
    current = _session_or_404(session_id)
    if current.status is not WorkoutStatus.IN_PROGRESS:
        return redirect(url_for("workouts.summary", session_id=current.id))
    blocks = workouts.session_blocks(current_user, current, profile, _equipment())
    return render_template(
        "workouts/session.html",
        session=current,
        blocks=blocks,
        rest_seconds=request.args.get("descanso", type=int),
        rest_started=request.args.get("t", type=int),
        just_logged=request.args.get("hecha", type=int),
        finish_form=FinishForm(),
        fatigue_labels=FATIGUE_LABELS,
        labels=labels,
        started_epoch=int(current.started_at.timestamp()),
    )


@bp.post("/<int:session_id>/serie")
@login_required
def log_set(session_id: int) -> WerkzeugResponse:
    """Record one set and come back with the rest timer armed."""
    current = _session_or_404(session_id)
    form = SetForm()
    if not form.validate():
        for errors in form.errors.values():
            for error in errors:
                flash(str(error), "error")
        return redirect(url_for("workouts.session", session_id=current.id))
    item = _item_of(current, form.routine_exercise_id.data)
    try:
        row = workouts.log_set(
            current,
            item,
            int(form.set_index.data or 0),
            int(form.reps.data or 0),
            float(form.weight_kg.data or 0),
            form.rir.data,
            SetType(form.set_type.data),
        )
    except WorkoutError as exc:
        flash(str(ERROR_TEXTS.get(exc.reason, exc.reason)), "error")
        return redirect(url_for("workouts.session", session_id=current.id))
    db.session.commit()
    target = url_for(
        "workouts.session",
        session_id=current.id,
        descanso=item.rest_seconds,
        t=int(row.completed_at.timestamp()),
        hecha=row.id,
    )
    return redirect(f"{target}#ex-{item.id}")


@bp.post("/<int:session_id>/serie/<int:set_id>/borrar")
@login_required
def delete_set(session_id: int, set_id: int) -> WerkzeugResponse:
    """Remove a logged set."""
    current = _session_or_404(session_id)
    try:
        workouts.delete_set(current, set_id)
    except WorkoutError as exc:
        flash(str(ERROR_TEXTS.get(exc.reason, exc.reason)), "error")
    else:
        db.session.commit()
    return redirect(url_for("workouts.session", session_id=current.id))


@bp.post("/<int:session_id>/sustituir")
@login_required
def substitute(session_id: int) -> WerkzeugResponse:
    """Use an alternative exercise for this session only."""
    profile = _profile_or_redirect()
    if not isinstance(profile, Profile):
        return profile
    current = _session_or_404(session_id)
    form = SubstituteForm()
    if not form.validate():
        flash(_("Petición no válida."), "error")
        return redirect(url_for("workouts.session", session_id=current.id))
    item = _item_of(current, form.routine_exercise_id.data)
    exercise = db.session.get(Exercise, form.exercise_id.data) if form.exercise_id.data else None
    try:
        workouts.substitute(current, item, exercise, profile, _equipment())
    except WorkoutError as exc:
        flash(str(ERROR_TEXTS.get(exc.reason, exc.reason)), "error")
    else:
        db.session.commit()
        flash(
            _("Ejercicio sustituido por %(name)s.", name=exercise.display_name)
            if exercise
            else _("Ejercicio original restaurado."),
            "success",
        )
    return redirect(f"{url_for('workouts.session', session_id=current.id)}#ex-{item.id}")


@bp.post("/<int:session_id>/terminar")
@login_required
def finish(session_id: int) -> WerkzeugResponse:
    """Close the session and show the summary."""
    current = _session_or_404(session_id)
    form = FinishForm()
    if not form.validate():
        flash(_("Revisa el formulario de cierre."), "error")
        return redirect(url_for("workouts.session", session_id=current.id))
    try:
        workouts.finish(
            current, form.perceived_fatigue.data, (form.notes.data or "").strip() or None
        )
    except WorkoutError as exc:
        flash(str(ERROR_TEXTS.get(exc.reason, exc.reason)), "error")
        return redirect(url_for("workouts.session", session_id=current.id))
    db.session.commit()
    if current.status is WorkoutStatus.COMPLETED:
        flash(_("Sesión guardada. Buen trabajo."), "success")
    else:
        flash(_("Sesión cerrada sin series: no cuenta como completada."), "warning")
    return redirect(url_for("workouts.summary", session_id=current.id))


@bp.post("/<int:session_id>/abandonar")
@login_required
def abandon(session_id: int) -> WerkzeugResponse:
    """Close the session without counting it."""
    current = _session_or_404(session_id)
    try:
        workouts.abandon(current)
    except WorkoutError as exc:
        flash(str(ERROR_TEXTS.get(exc.reason, exc.reason)), "error")
    else:
        db.session.commit()
        flash(_("Sesión abandonada."), "info")
    return redirect(url_for("dashboard.index"))


@bp.get("/<int:session_id>/resumen")
@login_required
def summary(session_id: int) -> str | WerkzeugResponse:
    """Totals, best sets and personal records of a closed session."""
    current = _session_or_404(session_id)
    if current.status is WorkoutStatus.IN_PROGRESS:
        return redirect(url_for("workouts.session", session_id=current.id))
    return render_template(
        "workouts/summary.html",
        summary=workouts.summarise(current_user, current),
        fatigue_labels=FATIGUE_LABELS,
        labels=labels,
    )


@bp.get("/historial")
@login_required
def history() -> str:
    """Closed sessions, newest first."""
    return render_template("workouts/history.html", items=workouts.history(current_user))


@bp.get("/progreso")
@login_required
def progress() -> str:
    """Estimated one-rep max and top load per session for one exercise."""
    exercises = workouts.trained_exercises(current_user)
    slug = request.args.get("ejercicio")
    chosen = next((item for item in exercises if item.slug == slug), None)
    if chosen is None and exercises:
        chosen = exercises[0]
    points = workouts.exercise_progress(current_user, chosen) if chosen else []
    chart = None
    if len(points) >= 2:
        chart = {
            "labels": [point.day.strftime("%d/%m") for point in points],
            "series": [
                {"label": str(_("Máximo estimado (kg)")), "data": [p.est_1rm for p in points]},
                {"label": str(_("Peso máximo (kg)")), "data": [p.top_weight for p in points]},
            ],
        }
    return render_template(
        "workouts/progress.html",
        exercises=exercises,
        chosen=chosen,
        points=points,
        chart=chart,
    )
