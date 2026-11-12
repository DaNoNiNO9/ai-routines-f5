"""Stripe over its HTTPS API, without the SDK (one dependency less to keep up to date).

Only four calls are needed: create a Checkout Session, create a Customer Portal
session, cancel a subscription, and verify webhooks. Webhook signatures follow
Stripe's scheme: the ``Stripe-Signature`` header carries ``t=<timestamp>`` and
one or more ``v1=<hex>`` values, each an HMAC-SHA256 of ``"<t>.<raw body>"``
with the endpoint secret; events older than five minutes are refused so a
captured request cannot be replayed.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from app.models import Subscription, User
from app.services.billing.gateway import BillingError

logger = logging.getLogger(__name__)

API_BASE = "https://api.stripe.com/v1"
TIMEOUT_SECONDS = 20
SIGNATURE_TOLERANCE_SECONDS = 300

# Transport: (method, url, form fields, headers) -> parsed JSON. Swappable in tests.
Transport = Callable[[str, str, Mapping[str, str], Mapping[str, str]], dict[str, Any]]


def _urllib_transport(
    method: str, url: str, fields: Mapping[str, str], headers: Mapping[str, str]
) -> dict[str, Any]:
    body = urllib.parse.urlencode(fields).encode() if fields else None
    request = urllib.request.Request(url, data=body, method=method, headers=dict(headers))
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data: dict[str, Any] = json.loads(response.read())
            return data
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        logger.exception("Stripe %s %s -> %s %s", method, url, exc.code, detail)
        raise BillingError("gateway_error") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        logger.exception("Stripe %s %s unreachable", method, url)
        raise BillingError("gateway_unreachable") from exc


def verify_signature(
    payload: bytes, header: str | None, secret: str, now: float | None = None
) -> None:
    """Raise ``BillingError`` unless ``header`` signs ``payload`` with ``secret``."""
    if not header or not secret:
        raise BillingError("bad_signature")
    parts: dict[str, list[str]] = {}
    for item in header.split(","):
        key, _, value = item.strip().partition("=")
        parts.setdefault(key, []).append(value)
    try:
        timestamp = int(parts["t"][0])
    except (KeyError, ValueError, IndexError) as exc:
        raise BillingError("bad_signature") from exc
    signed = f"{timestamp}.".encode() + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, given) for given in parts.get("v1", [])):
        raise BillingError("bad_signature")
    if abs((now if now is not None else time.time()) - timestamp) > SIGNATURE_TOLERANCE_SECONDS:
        raise BillingError("stale_signature")


class StripeGateway:
    """The real thing. Configured by ``STRIPE_*`` (see ``config.py``)."""

    name = "stripe"

    def __init__(self, config: Mapping[str, Any], transport: Transport | None = None) -> None:
        self.secret_key = str(config.get("STRIPE_SECRET_KEY") or "")
        self.webhook_secret = str(config.get("STRIPE_WEBHOOK_SECRET") or "")
        self.api_version = str(config.get("STRIPE_API_VERSION") or "")
        self.prices = {
            "monthly": str(config.get("STRIPE_PRICE_MONTHLY") or ""),
            "yearly": str(config.get("STRIPE_PRICE_YEARLY") or ""),
        }
        self.transport = transport or _urllib_transport

    def _call(
        self, method: str, path: str, fields: Mapping[str, str] | None = None
    ) -> dict[str, Any]:
        if not self.secret_key:
            raise BillingError("not_configured")
        headers = {"Authorization": f"Bearer {self.secret_key}"}
        if self.api_version:
            headers["Stripe-Version"] = self.api_version
        return self.transport(method, f"{API_BASE}{path}", fields or {}, headers)

    def checkout_url(
        self, user: User, plan: str, success_url: str, cancel_url: str, trial_days: int
    ) -> str:
        """Create a Checkout Session for the plan, with the trial, and return its URL."""
        price = self.prices.get(plan)
        if not price:
            raise BillingError("unknown_plan")
        existing = user.subscription
        fields = {
            "mode": "subscription",
            "line_items[0][price]": price,
            "line_items[0][quantity]": "1",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": str(user.id),
            "allow_promotion_codes": "true",
            "locale": "en" if (user.locale or "es").startswith("en") else "es",
            "metadata[plan]": plan,
            "subscription_data[metadata][user_id]": str(user.id),
            "subscription_data[metadata][plan]": plan,
        }
        if existing is not None and existing.customer_id:
            fields["customer"] = existing.customer_id
        else:
            fields["customer_email"] = user.email
        if trial_days > 0:
            fields["subscription_data[trial_period_days]"] = str(trial_days)
        session = self._call("POST", "/checkout/sessions", fields)
        url = session.get("url")
        if not url:
            raise BillingError("gateway_error")
        return str(url)

    def portal_url(self, subscription: Subscription, return_url: str) -> str:
        """Create a Customer Portal session and return its URL."""
        if not subscription.customer_id:
            raise BillingError("no_customer")
        session = self._call(
            "POST",
            "/billing_portal/sessions",
            {"customer": subscription.customer_id, "return_url": return_url},
        )
        return str(session["url"])

    def cancel_now(self, subscription: Subscription) -> None:
        """Cancel immediately at Stripe (no refund logic: the account is going away)."""
        if subscription.subscription_id:
            self._call("DELETE", f"/subscriptions/{subscription.subscription_id}")

    def set_cancel_at_period_end(self, subscription: Subscription, cancel: bool) -> None:
        """Ask Stripe to (not) cancel at the period end, and mirror its answer."""
        from app.services.billing import apply_subscription_object

        if not subscription.subscription_id:
            raise BillingError("no_subscription")
        updated = self._call(
            "POST",
            f"/subscriptions/{subscription.subscription_id}",
            {"cancel_at_period_end": "true" if cancel else "false"},
        )
        apply_subscription_object(updated)

    def withdraw(self, subscription: Subscription) -> None:
        """Refund the latest paid invoice of the subscription, then cancel it now."""
        from app.services.billing import apply_subscription_object

        if not subscription.subscription_id:
            raise BillingError("no_subscription")
        invoices = self._call(
            "GET",
            "/invoices?"
            + urllib.parse.urlencode(
                {"subscription": subscription.subscription_id, "status": "paid", "limit": "1"}
            ),
        )
        for invoice in invoices.get("data") or []:
            paid = int(invoice.get("amount_paid") or 0)
            intent = invoice.get("payment_intent")
            if paid > 0 and intent:
                self._call("POST", "/refunds", {"payment_intent": str(intent)})
        cancelled = self._call("DELETE", f"/subscriptions/{subscription.subscription_id}")
        apply_subscription_object(cancelled)

    def parse_webhook(self, payload: bytes, signature: str | None) -> dict[str, Any]:
        """Verify the signature and return the event."""
        verify_signature(payload, signature, self.webhook_secret)
        try:
            event: dict[str, Any] = json.loads(payload)
        except ValueError as exc:
            raise BillingError("bad_payload") from exc
        return event
