"""Hevy import: upload the CSV, check the exercise pairs, confirm."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required
from werkzeug.wrappers import Response as WerkzeugResponse

from app.extensions import db, limiter
from app.models import Exercise
from app.services import hevy
from app.services.onboarding import exercise_lookup

bp = Blueprint("imports", __name__, url_prefix="/cuenta/importar")


def _reasons() -> dict[str, str]:
    return {
        "too_big": _("El fichero pasa de 8 MB. Exporta desde Hevy solo los entrenos."),
        "not_csv": _("No es un CSV de texto. Sube el fichero tal como lo da Hevy."),
        "not_hevy": _(
            "No parece una exportación de entrenos de Hevy: faltan las columnas de entreno, "
            "ejercicio y repeticiones."
        ),
        "empty": _("El fichero no tiene ningún entreno que podamos leer."),
    }


def _preview(data: bytes, token: str) -> str:
    history = hevy.parse_csv(data, current_user.timezone or "Europe/Madrid")
    names = [name for name, _count in history.exercises.most_common()]
    matches = hevy.suggest_matches(names)
    choices = db.session.scalars(db.select(Exercise).where(Exercise.is_active.is_(True))).all()
    rows = [
        {"name": name, "sets": history.exercises[name], "match": matches[name]} for name in names
    ]
    first = history.workouts[0].started_at
    last = history.workouts[-1].started_at
    return render_template(
        "imports/preview.html",
        token=token,
        rows=rows,
        history=history,
        first=first,
        last=last,
        choices=sorted(choices, key=lambda e: e.display_name),
    )


@bp.route("/hevy", methods=["GET", "POST"])
@login_required
@limiter.limit("20 per hour", methods=["POST"])
def hevy_upload() -> str | WerkzeugResponse:
    """Explain how to export from Hevy, and read the file."""
    if request.method == "POST":
        upload = request.files.get("archivo")
        data = upload.read(hevy.MAX_BYTES + 1) if upload else b""
        if not data:
            flash(_("Elige el fichero CSV que exportaste de Hevy."), "warning")
            return render_template("imports/hevy.html")
        try:
            hevy.parse_csv(data, current_user.timezone or "Europe/Madrid")
        except hevy.HevyImportError as exc:
            flash(_reasons()[exc.reason], "error")
            return render_template("imports/hevy.html")
        token = hevy.keep_pending(current_user.id, data)
        return _preview(data, token)
    return render_template("imports/hevy.html")


@bp.post("/hevy/confirmar")
@login_required
def hevy_confirm() -> str | WerkzeugResponse:
    """Write the sessions with the pairs the person checked."""
    token = request.form.get("token", "")
    data = hevy.read_pending(current_user.id, token)
    if data is None:
        flash(_("La vista previa ha caducado. Vuelve a subir el fichero."), "warning")
        return redirect(url_for("imports.hevy_upload"))
    history = hevy.parse_csv(data, current_user.timezone or "Europe/Madrid")
    lookup = exercise_lookup()
    by_slug = {
        e.slug: e
        for e in db.session.scalars(db.select(Exercise).where(Exercise.is_active.is_(True)))
    }
    pairs: dict[str, Exercise | None] = {}
    for index, name in enumerate(n for n, _c in history.exercises.most_common()):
        chosen = request.form.get(f"par-{index}", "").strip()
        slug = lookup.slug_of(chosen) if chosen else None
        pairs[name] = by_slug.get(slug) if slug else None
    result = hevy.import_history(current_user, history, pairs)
    hevy.purge_pending(current_user.id)
    flash(
        _(
            "Importados %(workouts)s entrenos con %(sets)s series. "
            "Ya estaban: %(dupes)s. Series sin ejercicio emparejado: %(skipped)s.",
            workouts=result.workouts,
            sets=result.sets,
            dupes=result.duplicates,
            skipped=result.skipped_sets,
        ),
        "success",
    )
    return redirect(url_for("workouts.history"))


@bp.post("/hevy/cancelar")
@login_required
def hevy_cancel() -> WerkzeugResponse:
    """Drop the held file without importing anything."""
    hevy.purge_pending(current_user.id)
    flash(_("No hemos importado nada y el fichero se ha borrado."), "success")
    return redirect(url_for("account.index"))
