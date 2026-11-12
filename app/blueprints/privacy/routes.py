"""Privacy policy, and giving or withdrawing consent for health data."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required
from werkzeug.wrappers import Response as WerkzeugResponse

from app.services import auth as auth_service
from app.services import privacy

bp = Blueprint("privacy", __name__)

# Lo que se puede abrir sin consentimiento: nada que muestre o guarde datos de salud.
OPEN_WITHOUT_CONSENT = frozenset(
    {
        "static",
        "privacy.policy",
        "privacy.consent",
        "auth.logout",
        "account.index",
        "account.save_profile",
        "account.change_email",
        "account.change_password",
        "account.data_archive",
        "account.delete_account",
        "billing.prices",
        "billing.subscription",
        "billing.cancel",
        "billing.resume",
        "billing.withdraw",
        "billing.manage",
        "billing.webhook",
        "main.index",
        "main.about",
        "main.offline",
        "main.manifest",
        "main.service_worker",
        "main.favicon",
        "main.health",
        "main.toggle_theme",
    }
)


@bp.before_app_request
def _require_health_consent() -> WerkzeugResponse | None:
    """Without explicit consent, no screen that shows or stores health data."""
    if not current_user.is_authenticated or current_user.has_health_consent:
        return None
    endpoint = request.endpoint or ""
    if endpoint in OPEN_WITHOUT_CONSENT or endpoint.startswith(("debug.", "billing.fake")):
        return None
    return redirect(url_for("privacy.consent"))


@bp.get("/privacidad")
def policy() -> str:
    """The privacy policy (draft for legal review)."""
    return render_template("privacy/policy.html", consent_version=privacy.CONSENT_VERSION)


@bp.route("/consentimiento", methods=["GET", "POST"])
@login_required
def consent() -> str | WerkzeugResponse:
    """Give explicit consent for health data (accounts created before it was asked)."""
    if current_user.has_health_consent:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        if request.form.get("health_consent") != "y":
            flash(_("Marca la casilla para dar tu consentimiento."), "warning")
            return render_template("privacy/consent.html")
        privacy.give_consent(current_user)
        flash(_("Gracias. Ya puedes seguir con tu plan."), "success")
        return redirect(url_for("dashboard.index"))
    return render_template("privacy/consent.html")


@bp.route("/cuenta/consentimiento/retirar", methods=["GET", "POST"])
@login_required
def withdraw() -> str | WerkzeugResponse:
    """Withdraw consent: every piece of health data is deleted for good."""
    if not current_user.has_health_consent:
        return redirect(url_for("privacy.consent"))
    if request.method == "POST":
        password = request.form.get("current_password", "")
        if not auth_service.verify_password(current_user.password_hash, password):
            flash(_("La contraseña no es correcta."), "error")
            return render_template("privacy/withdraw.html")
        privacy.withdraw_consent(current_user)
        flash(
            _("Has retirado tu consentimiento: hemos borrado todos tus datos de salud."),
            "success",
        )
        response = redirect(url_for("account.index"))
        # Las pantallas guardadas en el móvil para usarlas sin red también llevan datos de salud.
        response.headers["Clear-Site-Data"] = '"cache", "storage"'
        return response
    return render_template("privacy/withdraw.html")
