"""Account settings, exports (PDF and CSV) and deletion."""

from __future__ import annotations

import logging

from flask import Blueprint, Response, flash, redirect, render_template, url_for
from flask_babel import gettext as _
from flask_babel import lazy_gettext as _l
from flask_login import current_user, login_required, logout_user
from werkzeug.wrappers import Response as WerkzeugResponse

from app.blueprints.account.forms import (
    COMMON_TIMEZONES,
    DELETE_WORD,
    DeleteAccountForm,
    EmailForm,
    PasswordForm,
    ProfileForm,
)
from app.blueprints.auth.routes import password_messages
from app.engine.nutrition import build_nutrition_plan
from app.extensions import db, limiter
from app.services import auth as auth_service
from app.services import exports, onboarding, plans

logger = logging.getLogger(__name__)

bp = Blueprint("account", __name__, url_prefix="/cuenta")

WRONG_PASSWORD = _l("La contraseña no es correcta.")


def _page(**overrides: object) -> str:
    """The settings page, keeping whichever form failed validation."""
    forms: dict[str, object] = {
        "profile_form": ProfileForm(obj=current_user),
        "email_form": EmailForm(),
        "password_form": PasswordForm(),
        "delete_form": DeleteAccountForm(),
    }
    forms.update(overrides)
    return render_template(
        "account/index.html",
        timezones=COMMON_TIMEZONES,
        delete_word=DELETE_WORD,
        has_profile=onboarding.current_profile(current_user) is not None,
        **forms,
    )


@bp.get("")
@login_required
def index() -> str:
    """Everything about the account in one page."""
    return _page()


@bp.post("/perfil")
@login_required
def save_profile() -> str | WerkzeugResponse:
    """Name, language and time zone."""
    form = ProfileForm()
    if not form.validate_on_submit():
        return _page(profile_form=form)
    current_user.display_name = (form.display_name.data or "").strip()
    current_user.locale = form.locale.data
    current_user.timezone = form.timezone.data
    db.session.commit()
    flash(_("Datos guardados."), "success")
    return redirect(url_for("account.index"))


@bp.post("/correo")
@login_required
@limiter.limit("10 per hour")
def change_email() -> str | WerkzeugResponse:
    """Change the address used to sign in."""
    form = EmailForm()
    if not form.validate_on_submit():
        return _page(email_form=form)
    try:
        auth_service.change_email(
            current_user, form.current_password.data or "", form.email.data or ""
        )
    except auth_service.InvalidCredentialsError:
        form.current_password.errors.append(str(WRONG_PASSWORD))
        return _page(email_form=form)
    except auth_service.EmailTakenError:
        form.email.errors.append(_("Ya existe una cuenta con ese correo."))
        return _page(email_form=form)
    flash(_("Correo actualizado. Úsalo la próxima vez que entres."), "success")
    return redirect(url_for("account.index"))


@bp.post("/contrasena")
@login_required
@limiter.limit("10 per hour")
def change_password() -> str | WerkzeugResponse:
    """Change the password (the current one is required)."""
    form = PasswordForm()
    if not form.validate_on_submit():
        return _page(password_form=form)
    try:
        auth_service.change_password(
            current_user, form.current_password.data or "", form.password.data or ""
        )
    except auth_service.InvalidCredentialsError:
        form.current_password.errors.append(str(WRONG_PASSWORD))
        return _page(password_form=form)
    except auth_service.WeakPasswordError as exc:
        for message in password_messages(exc.problems):
            form.password.errors.append(message)
        return _page(password_form=form)
    flash(_("Contraseña actualizada."), "success")
    return redirect(url_for("account.index"))


@bp.get("/plan.pdf")
@login_required
@limiter.limit("30 per hour")
def plan_pdf() -> Response | WerkzeugResponse:
    """The plan in force as a PDF, ready to print or to take to a professional."""
    profile = onboarding.current_profile(current_user)
    if profile is None:
        flash(_("Todavía no hay plan que exportar."), "warning")
        return redirect(url_for("onboarding.index"))
    today = current_user.today()
    plan = plans.active_plan(current_user)
    reasons: list[str] = []
    if plan is None:
        nutrition = build_nutrition_plan(plans.nutrition_inputs(profile, today))
        reasons = [item["text"] for item in plans.messages_for(nutrition.blocked_reasons)]
    document = exports.plan_pdf(
        current_user,
        plan,
        plans.active_routine(current_user),
        profile,
        today,
        blocked_reasons=reasons,
    )
    logger.info("Plan exported as PDF by user %s", current_user.id)
    return _download(
        document, "application/pdf", exports.export_filename(current_user, today, "pdf")
    )


@bp.get("/datos.zip")
@login_required
@limiter.limit("10 per hour")
def data_archive() -> Response:
    """Every personal record as a ZIP of CSV files (RGPD, artículo 20)."""
    today = current_user.today()
    archive = exports.data_archive(current_user)
    logger.info("Personal data exported by user %s", current_user.id)
    return _download(
        archive, "application/zip", exports.export_filename(current_user, today, "zip")
    )


def _download(payload: bytes, mimetype: str, filename: str) -> Response:
    response = Response(payload, mimetype=mimetype)
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Content-Length"] = str(len(payload))
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.post("/borrar")
@login_required
@limiter.limit("5 per hour")
def delete_account() -> str | WerkzeugResponse:
    """Erase the account and everything in it, for good."""
    form = DeleteAccountForm()
    if not form.validate_on_submit():
        return _page(delete_form=form)
    if not auth_service.verify_password(
        current_user.password_hash, form.current_password.data or ""
    ):
        form.current_password.errors.append(str(WRONG_PASSWORD))
        return _page(delete_form=form)
    user = current_user._get_current_object()
    logout_user()
    auth_service.delete_account(user)
    flash(_("Tu cuenta y todos tus datos se han borrado. Gracias por probar Alza."), "success")
    return redirect(url_for("main.index"))
