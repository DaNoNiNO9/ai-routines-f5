"""The real Stripe gateway, against Stripe-shaped responses and signed webhooks.

No network: the HTTP transport is replaced, and webhooks are signed exactly as
Stripe signs them (HMAC-SHA256 of "<timestamp>.<body>" with the endpoint secret).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.models import BillingEvent, Subscription, User
from app.services.billing import BillingError
from app.services.billing.stripe_gateway import StripeGateway, verify_signature
from tests.integration.test_workout_flow import _with_routine

SECRET = "whsec_test_secret"
CONFIG = {
    "STRIPE_SECRET_KEY": "sk_test_123",
    "STRIPE_WEBHOOK_SECRET": SECRET,
    "STRIPE_PRICE_MONTHLY": "price_monthly",
    "STRIPE_PRICE_YEARLY": "price_yearly",
    "STRIPE_API_VERSION": "2024-06-20",
}


def _sign(payload: bytes, secret: str = SECRET, at: int | None = None) -> str:
    timestamp = at if at is not None else int(time.time())
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256)
    return f"t={timestamp},v1={digest.hexdigest()}"


@pytest.fixture
def stripe_app(app: Flask) -> Flask:
    app.config.update(CONFIG, BILLING_BACKEND="stripe", PAYWALL_ENABLED=True)
    return app


class Recorder:
    """Stands in for HTTPS: records each call and answers like Stripe."""

    def __init__(self, answer: dict[str, Any]) -> None:
        self.answer = answer
        self.calls: list[tuple[str, str, dict[str, str], dict[str, str]]] = []

    def __call__(
        self, method: str, url: str, fields: Mapping[str, str], headers: Mapping[str, str]
    ) -> dict[str, Any]:
        self.calls.append((method, url, dict(fields), dict(headers)))
        return self.answer


def test_signatures_are_checked_like_stripe_does() -> None:
    payload = b'{"id": "evt_1"}'
    verify_signature(payload, _sign(payload), SECRET)
    with pytest.raises(BillingError, match="bad_signature"):
        verify_signature(payload, _sign(payload, "whsec_other"), SECRET)
    with pytest.raises(BillingError, match="bad_signature"):
        verify_signature(payload + b" ", _sign(payload), SECRET)
    with pytest.raises(BillingError, match="bad_signature"):
        verify_signature(payload, None, SECRET)
    with pytest.raises(BillingError, match="stale_signature"):
        verify_signature(payload, _sign(payload, at=int(time.time()) - 3600), SECRET)
    # Varias firmas (rotación del secreto): vale si una coincide.
    good = _sign(payload).split(",")[1]
    verify_signature(payload, f"t={int(time.time())},v1=deadbeef,{good}", SECRET)


def test_checkout_asks_stripe_for_a_subscription_with_trial(
    client: FlaskClient, seeded: SQLAlchemy, stripe_app: Flask
) -> None:
    _with_routine(client)
    user = seeded.session.scalar(select(User))
    assert user is not None
    recorder = Recorder({"id": "cs_test_1", "url": "https://checkout.stripe.com/c/pay/cs_test_1"})
    with stripe_app.test_request_context():
        url = StripeGateway(CONFIG, transport=recorder).checkout_url(
            user, "yearly", "https://alza.fit/ok", "https://alza.fit/precios", 7
        )
    assert url.startswith("https://checkout.stripe.com/")
    method, endpoint, fields, headers = recorder.calls[0]
    assert (method, endpoint) == ("POST", "https://api.stripe.com/v1/checkout/sessions")
    assert headers["Authorization"] == "Bearer sk_test_123"
    assert headers["Stripe-Version"] == "2024-06-20"
    assert fields["mode"] == "subscription"
    assert fields["line_items[0][price]"] == "price_yearly"
    assert fields["subscription_data[trial_period_days]"] == "7"
    assert fields["subscription_data[metadata][user_id]"] == str(user.id)
    assert fields["client_reference_id"] == str(user.id)
    assert fields["customer_email"] == user.email


def test_the_start_route_redirects_to_stripe(
    client: FlaskClient, seeded: SQLAlchemy, stripe_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    _with_routine(client)
    recorder = Recorder({"url": "https://checkout.stripe.com/c/pay/cs_test_2"})
    monkeypatch.setattr("app.services.billing.stripe_gateway._urllib_transport", recorder)
    response = client.post("/suscripcion/empezar", data={"plan": "monthly"})
    assert response.status_code == 303
    assert response.headers["Location"] == "https://checkout.stripe.com/c/pay/cs_test_2"


def test_without_keys_it_says_payments_are_not_set_up(
    client: FlaskClient, seeded: SQLAlchemy, stripe_app: Flask
) -> None:
    _with_routine(client)
    stripe_app.config["STRIPE_SECRET_KEY"] = ""
    page = client.post("/suscripcion/empezar", data={"plan": "monthly"}, follow_redirects=True)
    assert "Los pagos no están configurados todavía." in page.get_data(as_text=True)


def _post_event(client: FlaskClient, event: dict[str, Any]) -> Any:
    payload = json.dumps(event).encode()
    return client.post(
        "/suscripcion/webhook",
        data=payload,
        headers={"Stripe-Signature": _sign(payload), "Content-Type": "application/json"},
    )


def _subscription_event(user_id: int, event_id: str, status: str, **extra: Any) -> dict[str, Any]:
    obj = {
        "id": "sub_123",
        "object": "subscription",
        "customer": "cus_123",
        "status": status,
        "trial_end": None,
        "cancel_at_period_end": False,
        "metadata": {"user_id": str(user_id), "plan": "monthly"},
        "items": {"data": [{"price": {"id": "price_yearly"}}]},
    }
    obj.update(extra)
    return {"id": event_id, "type": "customer.subscription.updated", "data": {"object": obj}}


def test_signed_webhooks_update_the_subscription_once(
    client: FlaskClient, seeded: SQLAlchemy, stripe_app: Flask
) -> None:
    _with_routine(client)
    user = seeded.session.scalar(select(User))
    assert user is not None
    end = int(time.time()) + 30 * 86400
    event = _subscription_event(user.id, "evt_1", "active", current_period_end=end)
    assert _post_event(client, event).get_json() == {"received": True, "applied": True}
    again = _post_event(client, event)  # Stripe reintenta: no cambia nada
    assert again.status_code == 200
    assert again.get_json()["applied"] is False
    row = seeded.session.scalar(select(Subscription))
    assert row is not None
    assert row.status == "active"
    assert row.plan == "yearly"  # el precio manda sobre los metadatos
    assert row.current_period_end is not None
    assert len(seeded.session.scalars(select(BillingEvent)).all()) == 1


def test_newer_api_versions_put_the_period_end_on_the_item(
    client: FlaskClient, seeded: SQLAlchemy, stripe_app: Flask
) -> None:
    _with_routine(client)
    user = seeded.session.scalar(select(User))
    assert user is not None
    end = int(time.time()) + 365 * 86400
    items = {"data": [{"price": {"id": "price_yearly"}, "current_period_end": end}]}
    _post_event(client, _subscription_event(user.id, "evt_2", "active", items=items))
    row = seeded.session.scalar(select(Subscription))
    assert row is not None
    assert row.current_period_end is not None
    assert int(row.current_period_end.timestamp()) == end


def test_unsigned_or_forged_webhooks_are_refused(
    client: FlaskClient, seeded: SQLAlchemy, stripe_app: Flask
) -> None:
    _with_routine(client)
    payload = json.dumps(_subscription_event(1, "evt_3", "active")).encode()
    assert client.post("/suscripcion/webhook", data=payload).status_code == 400
    forged = client.post(
        "/suscripcion/webhook", data=payload, headers={"Stripe-Signature": _sign(payload, "x")}
    )
    assert forged.status_code == 400
    assert seeded.session.scalar(select(Subscription)) is None


def test_deleted_subscription_ends_pro(
    client: FlaskClient, seeded: SQLAlchemy, stripe_app: Flask
) -> None:
    _with_routine(client)
    user = seeded.session.scalar(select(User))
    assert user is not None
    _post_event(client, _subscription_event(user.id, "evt_4", "active"))
    deleted = _subscription_event(user.id, "evt_5", "canceled")
    deleted["type"] = "customer.subscription.deleted"
    _post_event(client, deleted)
    row = seeded.session.scalar(select(Subscription))
    assert row is not None
    assert row.status == "canceled"
    assert "pro-teaser" in client.get("/panel").get_data(as_text=True)


def test_portal_and_cancellation_calls(seeded: SQLAlchemy, stripe_app: Flask) -> None:
    del seeded, stripe_app
    row = Subscription(customer_id="cus_9", subscription_id="sub_9", status="active")
    recorder = Recorder({"url": "https://billing.stripe.com/p/session/x"})
    gateway = StripeGateway(CONFIG, transport=recorder)
    assert gateway.portal_url(row, "https://alza.fit/suscripcion").startswith("https://billing")
    gateway.cancel_now(row)
    assert recorder.calls[0][1].endswith("/billing_portal/sessions")
    assert recorder.calls[0][2]["customer"] == "cus_9"
    assert recorder.calls[1][:2] == ("DELETE", "https://api.stripe.com/v1/subscriptions/sub_9")
