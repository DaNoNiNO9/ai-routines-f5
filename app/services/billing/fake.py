"""A simulated Stripe: the whole subscription flow without an account or a card.

Checkout and the customer portal are local pages (``billing.fake_checkout`` and
``billing.fake_portal``) that say plainly that nothing is charged. What they do
is emit the same Stripe-shaped events the real webhook would deliver, and feed
them to :func:`app.services.billing.apply_event`, so the rest of the app cannot
tell the difference. The checkout link is signed and expires, so it cannot be
forged to give someone else Pro.
"""

from __future__ import annotations

import calendar
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import current_app, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.models import Subscription, User
from app.services.billing.gateway import BillingError

CHECKOUT_MAX_AGE_SECONDS = 3600
SALT = "alza-fake-checkout"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=SALT)


def read_checkout(token: str) -> dict[str, Any]:
    """The checkout a signed token describes; ``BillingError`` if forged or expired."""
    try:
        data: dict[str, Any] = _serializer().loads(token, max_age=CHECKOUT_MAX_AGE_SECONDS)
    except BadSignature as exc:
        raise BillingError("bad_checkout") from exc
    return data


def _event(kind: str, obj: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"evt_fake_{secrets.token_hex(8)}",
        "type": kind,
        "created": int(datetime.now(UTC).timestamp()),
        "data": {"object": obj},
    }


def add_months(start: datetime, months: int) -> datetime:
    """Same day ``months`` later, or the last day of that month if it is shorter."""
    month_index = start.month - 1 + months
    year, month = start.year + month_index // 12, month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return start.replace(year=year, month=month, day=day)


def _period_end(start: datetime, plan: str) -> datetime:
    return add_months(start, 12 if plan == "yearly" else 1)


def subscription_object(
    user_id: int,
    plan: str,
    status: str,
    *,
    subscription_id: str,
    customer: str,
    trial_end: datetime | None,
    period_end: datetime,
    cancel_at_period_end: bool = False,
) -> dict[str, Any]:
    """A subscription shaped like Stripe's (API 2024-06-20)."""
    return {
        "id": subscription_id,
        "object": "subscription",
        "customer": customer,
        "status": status,
        "trial_end": int(trial_end.timestamp()) if trial_end else None,
        "current_period_end": int(period_end.timestamp()),
        "cancel_at_period_end": cancel_at_period_end,
        "metadata": {"user_id": str(user_id), "plan": plan},
        "items": {"data": [{"price": {"id": f"price_fake_{plan}"}}]},
    }


def payment_events(checkout: dict[str, Any], now: datetime | None = None) -> list[dict[str, Any]]:
    """What Stripe sends after a successful checkout: the session, then the subscription."""
    now = now or datetime.now(UTC)
    user_id, plan, trial_days = (
        int(checkout["user_id"]),
        checkout["plan"],
        int(checkout["trial_days"]),
    )
    customer = checkout.get("customer") or f"cus_fake_{user_id}"
    subscription_id = f"sub_fake_{secrets.token_hex(6)}"
    trial_end = now + timedelta(days=trial_days) if trial_days > 0 else None
    period_end = trial_end or _period_end(now, plan)
    return [
        _event(
            "checkout.session.completed",
            {
                "object": "checkout.session",
                "client_reference_id": str(user_id),
                "customer": customer,
                "subscription": subscription_id,
                "metadata": {"plan": plan},
            },
        ),
        _event(
            "customer.subscription.created",
            subscription_object(
                user_id,
                plan,
                "trialing" if trial_end else "active",
                subscription_id=subscription_id,
                customer=customer,
                trial_end=trial_end,
                period_end=period_end,
            ),
        ),
    ]


def portal_events(row: Subscription, action: str, plan: str | None = None) -> list[dict[str, Any]]:
    """Events for what the person does in the simulated portal.

    ``cancel`` (at the end of the period), ``resume``, ``switch`` (plan),
    ``end`` (the period ran out after a cancellation) and ``fail`` (a renewal
    payment bounced).
    """
    if not row.subscription_id or not row.customer_id:
        raise BillingError("no_subscription")
    now = datetime.now(UTC)
    current_plan = plan if action == "switch" and plan else (row.plan or "monthly")
    status = row.status
    cancel = row.cancel_at_period_end
    kind = "customer.subscription.updated"
    if action == "cancel":
        cancel = True
    elif action == "resume":
        cancel = False
    elif action == "fail":
        status = "past_due"
    elif action == "end":
        kind, status = "customer.subscription.deleted", "canceled"
    elif action != "switch":
        raise BillingError("unknown_action")
    period_end = row.current_period_end or _period_end(now, current_plan)
    trial_end = row.trial_ends_at if row.status == "trialing" else None
    obj = subscription_object(
        row.user_id,
        current_plan,
        status,
        subscription_id=row.subscription_id,
        customer=row.customer_id,
        trial_end=trial_end,
        period_end=period_end,
        cancel_at_period_end=cancel,
    )
    return [_event(kind, obj)]


class FakeGateway:
    """Same contract as ``StripeGateway``; the pages do the rest."""

    name = "fake"

    def checkout_url(
        self, user: User, plan: str, success_url: str, cancel_url: str, trial_days: int
    ) -> str:
        """A signed link to the simulated checkout page."""
        if plan not in current_app.config["BILLING_PLANS"]:
            raise BillingError("unknown_plan")
        existing = user.subscription
        token = _serializer().dumps(
            {
                "user_id": user.id,
                "plan": plan,
                "trial_days": trial_days,
                "success_url": success_url,
                "cancel_url": cancel_url,
                "customer": existing.customer_id if existing else None,
            }
        )
        return url_for("billing.fake_checkout", token=token)

    def portal_url(self, subscription: Subscription, return_url: str) -> str:
        """The simulated portal (it always returns to the subscription page)."""
        del return_url
        if not subscription.subscription_id:
            raise BillingError("no_subscription")
        return url_for("billing.fake_portal")

    def cancel_now(self, subscription: Subscription) -> None:
        """Nothing to tell anyone: the row goes away with the account."""

    def set_cancel_at_period_end(self, subscription: Subscription, cancel: bool) -> None:
        """Emit the same event Stripe would and apply it."""
        from app.services.billing import apply_event

        for event in portal_events(subscription, "cancel" if cancel else "resume"):
            apply_event(event)

    def withdraw(self, subscription: Subscription) -> None:
        """End now (nothing was charged, so nothing to refund)."""
        from app.services.billing import apply_event

        for event in portal_events(subscription, "end"):
            apply_event(event)

    def parse_webhook(self, payload: bytes, signature: str | None) -> dict[str, Any]:
        """The simulation applies its events directly: there is no webhook to receive."""
        del payload, signature
        raise BillingError("no_webhooks_in_fake_mode")
