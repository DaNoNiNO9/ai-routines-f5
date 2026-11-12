"""Registration, login, logout and password recovery."""

from __future__ import annotations

import logging

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_babel import gettext as _
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.wrappers import Response as WerkzeugResponse

from app.blueprints.auth.forms import (
    ForgotPasswordForm,
    LoginForm,
    RegisterForm,
    ResetPasswordForm,
)
from app.email import EmailDeliveryError, send_email
from app.extensions import limiter
from app.security import safe_redirect_target
from app.services import auth as auth_service

logger = logging.getLogger(__name__)

bp = Blueprint("auth", __name__)

PASSWORD_PROBLEM_TEXTS = {
    "equals_email": lambda: _("La contraseña no puede ser tu correo."),
    "too_common": lambda: _("Esa contraseña es demasiado común."),
}


def password_messages(problems: list[str]) -> list[str]:
    """Spanish text for the policy codes the service returns."""
    messages: list[str] = []
    for code in problems:
        if code.startswith("min_length:"):
            minimum = code.split(":", 1)[1]
            messages.append(_("La contraseña debe tener al menos %(n)s caracteres.", n=minimum))
        else:
            text = PASSWORD_PROBLEM_TEXTS.get(code)
            messages.append(text() if text else code)
    return messages


@bp.route("/registro", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def register() -> str | WerkzeugResponse:
    """Create an account and start the session."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    form = RegisterForm()
    if form.validate_on_submit():
        try:
            user = auth_service.register_user(
                form.email.data or "", form.password.data or "", form.display_name.data or ""
            )
        except auth_service.WeakPasswordError as exc:
            for message in password_messages(exc.problems):
                form.password.errors.append(message)
        except auth_service.EmailTakenError:
            form.email.errors.append(_("Ya existe una cuenta con ese correo."))
        else:
            login_user(user)
            flash(_("Cuenta creada. Hola, %(name)s.", name=user.display_name), "success")
            return redirect(url_for("dashboard.index"))
    return render_template("auth/register.html", form=form)


@bp.route("/entrar", methods=["GET", "POST"])
@limiter.limit("5 per minute; 30 per hour", methods=["POST"])
def login() -> str | WerkzeugResponse:
    """Start a session."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    form = LoginForm()
    if form.validate_on_submit():
        try:
            user = auth_service.authenticate(form.email.data or "", form.password.data or "")
        except auth_service.InvalidCredentialsError:
            flash(_("Correo o contraseña incorrectos."), "error")
        except auth_service.InactiveAccountError:
            flash(_("Esta cuenta está desactivada."), "error")
        else:
            login_user(user, remember=bool(form.remember.data))
            return redirect(safe_redirect_target(request.args.get("next"), "dashboard.index"))
    return render_template("auth/login.html", form=form)


@bp.post("/salir")
@login_required
def logout() -> WerkzeugResponse:
    """End the session (POST only, so a link cannot log someone out)."""
    logout_user()
    flash(_("Sesión cerrada."), "success")
    return redirect(url_for("main.index"))


@bp.route("/recuperar", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def forgot_password() -> str | WerkzeugResponse:
    """Send a reset link; the response never reveals whether the email exists."""
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        email = form.email.data or ""
        user = auth_service.find_by_email(email)
        if user is not None and user.is_active and user.deleted_at is None:
            token = auth_service.issue_reset_token(user)
            link = url_for("auth.reset_password", token=token, _external=True)
            minutes = int(current_app.config["PASSWORD_RESET_MAX_AGE"]) // 60
            body = _(
                "Hola %(name)s,\n\nPara elegir una contraseña nueva entra en:\n%(link)s\n\n"
                "El enlace caduca en %(minutes)s minutos. Si no lo has pedido, ignora este correo.",
                name=user.display_name,
                link=link,
                minutes=minutes,
            )
            try:
                send_email(user.email, _("Recupera tu contraseña de Alza"), body)
            except EmailDeliveryError:
                flash(_("No se pudo enviar el correo. Inténtalo más tarde."), "error")
                return render_template("auth/forgot.html", form=form)
        else:
            logger.info("Password reset requested for an unknown or inactive email")
        flash(_("Si el correo existe, recibirás un enlace para restablecer la contraseña."), "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot.html", form=form)


@bp.route("/restablecer/<token>", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def reset_password(token: str) -> str | WerkzeugResponse:
    """Choose a new password with a valid token."""
    try:
        user = auth_service.verify_reset_token(token)
    except auth_service.InvalidTokenError:
        flash(_("El enlace no es válido o ha caducado. Pide uno nuevo."), "error")
        return redirect(url_for("auth.forgot_password"))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        try:
            auth_service.reset_password(user, form.password.data or "")
        except auth_service.WeakPasswordError as exc:
            for message in password_messages(exc.problems):
                form.password.errors.append(message)
        else:
            flash(_("Contraseña actualizada. Ya puedes entrar."), "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/reset.html", form=form, token=token)


@bp.get("/_auth/whoami")
def whoami() -> Response:
    """Tiny JSON probe used by tests and the client (never lists other users)."""
    if not current_app.config["ENABLE_DEBUG_ROUTES"]:
        abort(404)
    if current_user.is_authenticated:
        return current_app.response_class(
            response=current_app.json.dumps({"id": current_user.id, "email": current_user.email}),
            mimetype="application/json",
        )
    return current_app.response_class(
        response=current_app.json.dumps({"id": None}), mimetype="application/json"
    )
