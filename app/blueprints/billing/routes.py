"""Prices, the Pro subscription and the gateway's webhook (plus the simulated gateway's pages)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_babel import gettext as _
from flask_babel import lazy_gettext as _l
from flask_login import current_user, login_required
from werkzeug.wrappers import Response as WerkzeugResponse

from app.extensions import csrf
from app.services import billing
from app.services.billing import fake

logger = logging.getLogger(__name__)

bp = Blueprint("billing", __name__)

ERROR_TEXTS = {
    "unknown_plan": _l("Ese plan no existe."),
    "not_configured": _l("Los pagos no están configurados todavía."),
    "gateway_error": _l("La pasarela de pago ha dado un error. Inténtalo de nuevo en un rato."),
    "gateway_unreachable": _l("No hemos podido contactar con la pasarela de pago."),
    "no_customer": _l("Todavía no tienes una suscripción que gestionar."),
    "no_subscription": _l("Todavía no tienes una suscripción que gestionar."),
    "bad_checkout": _l("Ese enlace de pago no es válido o ha caducado."),
}


@bp.app_context_processor
def _inject_pro() -> dict[str, Any]:
    return {
        "is_pro": billing.is_pro(current_user),
        "paywall": current_app.config["PAYWALL_ENABLED"],
    }


def pro_required(view: Callable[..., Any]) -> Callable[..., Any]:
    """Send people without Pro to the prices page, saying why."""

    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not billing.is_pro(current_user):
            flash(_("Esto es parte de Alza Pro. Pruébalo gratis 7 días."), "info")
            return redirect(url_for("billing.prices"))
        return view(*args, **kwargs)

    return wrapper


def _fake_only() -> None:
    if current_app.config.get("BILLING_BACKEND") != "fake":
        abort(404)


def _plans() -> list[dict[str, Any]]:
    """The two plans with their amounts in euros (templates format them with |money)."""
    plans = current_app.config["BILLING_PLANS"]
    monthly = plans["monthly"]["amount_cents"] / 100
    yearly = plans["yearly"]["amount_cents"] / 100
    return [
        {
            "key": "monthly",
            "amount": monthly,
            "per": _("al mes"),
            "saving": None,
            "per_month": None,
        },
        {
            "key": "yearly",
            "amount": yearly,
            "per": _("al año"),
            "saving": round(100 - yearly / (monthly * 12) * 100),
            "per_month": round(yearly / 12, 2),
        },
    ]


@bp.get("/precios")
def prices() -> str:
    """Free versus Pro, and the two plans."""
    subscription = billing.subscription_of(current_user) if current_user.is_authenticated else None
    return render_template(
        "billing/prices.html",
        plans=_plans(),
        trial_days=current_app.config["BILLING_TRIAL_DAYS"],
        subscription=subscription,
    )


@bp.get("/suscripcion")
@login_required
def subscription() -> str:
    """Your plan, its state, and the way to change it."""
    return render_template(
        "billing/subscription.html",
        subscription=billing.subscription_of(current_user),
        plans={plan["key"]: plan for plan in _plans()},
        backend=current_app.config["BILLING_BACKEND"],
    )


def _trial_days() -> int:
    """No second trial: only whoever never subscribed gets it."""
    existing = billing.subscription_of(current_user)
    if existing is not None and existing.subscription_id:
        return 0
    return int(current_app.config["BILLING_TRIAL_DAYS"])


@bp.post("/suscripcion/empezar")
@login_required
def start() -> WerkzeugResponse:
    """Off to the gateway's checkout for the chosen plan."""
    existing = billing.subscription_of(current_user)
    if existing is not None and existing.is_active:
        flash(_("Ya tienes Alza Pro."), "info")
        return redirect(url_for("billing.subscription"))
    plan = request.form.get("plan", "")
    try:
        url = billing.gateway().checkout_url(
            current_user,
            plan,
            success_url=url_for("billing.done", _external=True),
            cancel_url=url_for("billing.prices", _external=True),
            trial_days=_trial_days(),
        )
    except billing.BillingError as exc:
        flash(str(ERROR_TEXTS.get(exc.reason, ERROR_TEXTS["gateway_error"])), "error")
        return redirect(url_for("billing.prices"))
    return redirect(url, code=303)


@bp.get("/suscripcion/hecho")
@login_required
def done() -> str:
    """Back from checkout. With Stripe the webhook may arrive a second later."""
    return render_template("billing/done.html", subscription=billing.subscription_of(current_user))


@bp.post("/suscripcion/gestionar")
@login_required
def manage() -> WerkzeugResponse:
    """Off to the gateway's customer portal (card, plan, cancellation)."""
    existing = billing.subscription_of(current_user)
    if existing is None:
        flash(str(ERROR_TEXTS["no_subscription"]), "info")
        return redirect(url_for("billing.prices"))
    try:
        url = billing.gateway().portal_url(
            existing, return_url=url_for("billing.subscription", _external=True)
        )
    except billing.BillingError as exc:
        flash(str(ERROR_TEXTS.get(exc.reason, ERROR_TEXTS["gateway_error"])), "error")
        return redirect(url_for("billing.subscription"))
    return redirect(url, code=303)


@bp.post("/suscripcion/webhook")
@csrf.exempt
def webhook() -> tuple[WerkzeugResponse, int]:
    """Stripe's events. Verified by signature; an already seen event is accepted again."""
    try:
        event = billing.gateway().parse_webhook(
            request.get_data(), request.headers.get("Stripe-Signature")
        )
    except billing.BillingError as exc:
        logger.warning("Webhook refused: %s", exc.reason)
        return jsonify(error=exc.reason), 400
    applied = billing.apply_event(event)
    return jsonify(received=True, applied=applied), 200


# --- Pasarela simulada (BILLING_BACKEND=fake) ---------------------------------


@bp.route("/suscripcion/simulada/pago/<token>", methods=["GET", "POST"])
@login_required
def fake_checkout(token: str) -> str | WerkzeugResponse:
    """A checkout page that charges nothing and says so."""
    _fake_only()
    try:
        checkout = fake.read_checkout(token)
    except billing.BillingError:
        flash(str(ERROR_TEXTS["bad_checkout"]), "error")
        return redirect(url_for("billing.prices"))
    if int(checkout["user_id"]) != current_user.id:
        abort(403)
    if request.method == "POST":
        outcome = request.form.get("outcome")
        if outcome == "pay":
            for event in fake.payment_events(checkout):
                billing.apply_event(event)
            return redirect(checkout["success_url"])
        if outcome == "decline":
            flash(_("La tarjeta ha sido rechazada (simulación). No se ha cobrado nada."), "error")
        return redirect(checkout["cancel_url"])
    plan = next(item for item in _plans() if item["key"] == checkout["plan"])
    return render_template("billing/fake_checkout.html", checkout=checkout, plan=plan)


@bp.route("/suscripcion/simulada/portal", methods=["GET", "POST"])
@login_required
def fake_portal() -> str | WerkzeugResponse:
    """A customer portal to try cancellations, plan changes and failed payments."""
    _fake_only()
    existing = billing.subscription_of(current_user)
    if existing is None or not existing.subscription_id:
        flash(str(ERROR_TEXTS["no_subscription"]), "info")
        return redirect(url_for("billing.prices"))
    if request.method == "POST":
        try:
            events = fake.portal_events(
                existing, request.form.get("action", ""), request.form.get("plan")
            )
        except billing.BillingError:
            abort(400)
        for event in events:
            billing.apply_event(event)
        flash(_("Cambio guardado (simulación)."), "success")
        return redirect(url_for("billing.subscription"))
    return render_template(
        "billing/fake_portal.html", subscription=existing, plans={p["key"]: p for p in _plans()}
    )
