"""The routine in force: overview, one page per training day with alternatives."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_babel import lazy_gettext as _l
from flask_login import current_user, login_required
from sqlalchemy import select
from werkzeug.wrappers import Response as WerkzeugResponse

from app import labels
from app.engine.enums import WorkoutStatus
from app.engine.routines.generator import build_routine
from app.extensions import db
from app.models import Exercise, RoutineExercise, WorkoutSession
from app.security import safe_redirect_target
from app.services import dashboard, exercise_media, onboarding, plans, swaps, workouts
from app.services.workouts import WorkoutError

bp = Blueprint("training", __name__, url_prefix="/entrenamiento")

SWAP_ERRORS = {
    "sets_logged": _l("Ya has apuntado series de ese ejercicio hoy: cámbialo en tu rutina."),
    "not_an_alternative": _l("Ese ejercicio no encaja con tu material o tus molestias."),
    "closed": _l("La sesión ya no está abierta."),
}


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
        set_aside=plans.exercises_by_slug(profile.disliked_exercises),
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
    dashboard.preload_alternatives(current.exercises)
    alternatives = {
        item.id: dashboard.usable_alternatives(item, profile, equipment)
        for item in current.exercises
    }
    frames = {item.id: dashboard.image_frames(item.exercise) for item in current.exercises}
    has_video = {
        item.id: exercise_media.video_for(item.exercise) is not None for item in current.exercises
    }
    days = active.days
    position = days.index(current)
    return render_template(
        "training/day.html",
        routine=active,
        day=current,
        alternatives=alternatives,
        frames=frames,
        has_video=has_video,
        previous_day=days[position - 1] if position > 0 else None,
        following_day=days[position + 1] if position + 1 < len(days) else None,
        weekly_rir=active.details.get("weekly_rir", []),
        labels=labels,
    )


@bp.get("/ejercicio/<slug>")
@login_required
def exercise(slug: str) -> str:
    """The exercise sheet: how it is done (video or animation, steps) and your record.

    With ``?parcial=1`` only the sheet is rendered, so the session and the day
    page can open it on top without leaving; without JavaScript it is a page.
    """
    item = db.session.scalar(
        select(Exercise).where(Exercise.slug == slug, Exercise.is_active.is_(True))
    )
    if item is None:
        abort(404)
    context = exercise_media.sheet(current_user, item, onboarding.current_profile(current_user))
    template = (
        "training/_exercise_sheet.html"
        if request.args.get("parcial")
        else ("training/exercise.html")
    )
    return render_template(template, labels=labels, **context)


@bp.post("/permitir")
@login_required
def allow_again() -> WerkzeugResponse:
    """Devuelve a la rutina un ejercicio apartado por error."""
    profile = onboarding.current_profile(current_user)
    if profile is None:
        return redirect(url_for("onboarding.index"))
    slug = request.form.get("slug", "")
    if plans.allow_exercise_again(profile, slug):
        db.session.commit()
        flash(_("Vuelve a estar disponible para las próximas rutinas."), "success")
    return redirect(url_for("training.routine"))


def _own_item(item_id: int) -> tuple[RoutineExercise, Any] | None:
    """A slot of this person's active routine (an id from another account does not exist here)."""
    routine = plans.active_routine(current_user)
    profile = onboarding.current_profile(current_user)
    if routine is None or profile is None:
        return None
    for day in routine.days:
        for row in day.exercises:
            if row.id == item_id:
                return row, profile
    return None


def _open_session(session_id: int | None) -> WorkoutSession | None:
    if not session_id:
        return None
    session = db.session.get(WorkoutSession, session_id)
    if session is None or session.user_id != current_user.id:
        return None
    return session if session.status is WorkoutStatus.IN_PROGRESS else None


@bp.get("/cambiar/<int:item_id>")
@login_required
def choose(item_id: int) -> str:
    """Exercises that can take this slot, by muscle group (page, or dialog with ?parcial=1)."""
    found = _own_item(item_id)
    if found is None:
        abort(404)
    item, profile = found
    equipment = frozenset(row.code for row in current_user.equipment)
    session = _open_session(request.args.get("sesion", type=int))
    can_today = session is not None and not any(
        row.routine_exercise_id == item.id for row in session.sets
    )
    context = {
        "choice": swaps.choices(item, profile, equipment, request.args.get("musculo")),
        "session": session if can_today else None,
        "back": safe_redirect_target(request.args.get("volver"), "training.routine"),
        "labels": labels,
        "image_frames": dashboard.image_frames,
    }
    parcial = request.args.get("parcial")
    template = "training/_swap_body.html" if parcial else "training/swap.html"
    return render_template(template, **context)


@bp.post("/cambiar/<int:item_id>")
@login_required
def apply_swap(item_id: int) -> WerkzeugResponse:
    """Use the chosen exercise only today (in the session) or from now on (in the routine)."""
    found = _own_item(item_id)
    if found is None:
        abort(404)
    item, profile = found
    back = safe_redirect_target(request.form.get("volver"), "training.routine")
    exercise = db.session.get(Exercise, request.form.get("exercise_id", type=int) or 0)
    if exercise is None or not exercise.is_active:
        flash(_("Elige uno de los ejercicios de la lista."), "error")
        return redirect(back)
    equipment = frozenset(row.code for row in current_user.equipment)
    if request.form.get("destino") == "sesion":
        session = _open_session(request.form.get("sesion_id", type=int))
        if session is None or session.routine_day_id != item.routine_day_id:
            flash(_("La sesión ya no está abierta."), "warning")
            return redirect(back)
        try:
            workouts.substitute(session, item, exercise, profile, equipment)
        except WorkoutError as exc:
            flash(str(SWAP_ERRORS.get(exc.reason, _("No se ha podido cambiar."))), "error")
            return redirect(back)
        db.session.commit()
        flash(_("Hoy harás %(name)s.", name=exercise.display_name), "success")
        return redirect(f"{url_for('workouts.session', session_id=session.id)}#ex-{item.id}")
    old = item.exercise.display_name
    try:
        swaps.apply_to_routine(
            item, exercise, profile, equipment, set_aside_old=request.form.get("apartar") == "1"
        )
    except swaps.SwapError:
        flash(_("Ese ejercicio no encaja con tu material o tus molestias."), "error")
        return redirect(back)
    db.session.commit()
    flash(
        _("%(new)s sustituye a %(old)s en tu rutina.", new=exercise.display_name, old=old),
        "success",
    )
    return redirect(back)
