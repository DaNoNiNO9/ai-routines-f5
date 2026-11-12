"""Pro subscription: who has it, how to start and manage it, and the gateway's events.

Two gateways with the same contract (``gateway.Gateway``):

- ``fake``: simulates Stripe end to end without an account. Checkout and the
  customer portal are local pages that say clearly that nothing is charged,
  and they produce the very same events Stripe would send.
- ``stripe``: the real API over HTTPS and signed webhooks.

Either way the subscription only changes through :func:`apply_event`, with
Stripe-shaped events, so switching to the real account is configuration, not
code (``BILLING_BACKEND=stripe`` and the ``STRIPE_*`` variables).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from flask import current_app
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import BillingEvent, Subscription, User
from app.services.billing.gateway import BillingError, Gateway

logger = logging.getLogger(__name__)

__all__ = [
    "BillingError",
    "Gateway",
    "apply_event",
    "gateway",
    "is_pro",
    "plan_for_price",
    "price_for_plan",
    "subscription_of",
]


def gateway() -> Gateway:
    """The gateway configured for this app (``BILLING_BACKEND``)."""
    backend = current_app.config.get("BILLING_BACKEND", "fake")
    if backend == "stripe":
        from app.services.billing.stripe_gateway import StripeGateway

        return StripeGateway(current_app.config)
    from app.services.billing.fake import FakeGateway

    return FakeGateway()


def subscription_of(user: User) -> Subscription | None:
    """The person's subscription row, if they ever started one."""
    return db.session.scalar(select(Subscription).where(Subscription.user_id == user.id))


def is_pro(user: Any) -> bool:
    """Whether the person has Pro now. With the paywall off, everyone does."""
    if not current_app.config.get("PAYWALL_ENABLED"):
        return True
    if not getattr(user, "is_authenticated", False):
        return False
    subscription = subscription_of(user)
    return subscription is not None and subscription.is_active


def price_for_plan(plan: str) -> str:
    """Stripe price id configured for ``monthly`` or ``yearly``."""
    key = {"monthly": "STRIPE_PRICE_MONTHLY", "yearly": "STRIPE_PRICE_YEARLY"}.get(plan)
    if key is None:
        raise BillingError("unknown_plan")
    return str(current_app.config.get(key) or "")


def plan_for_price(price_id: str | None) -> str | None:
    """Inverse of :func:`price_for_plan` (``None`` for a price we do not sell)."""
    if not price_id:
        return None
    for plan in ("monthly", "yearly"):
        if price_for_plan(plan) == price_id:
            return plan
    return None


def _when(epoch: Any) -> datetime | None:
    return datetime.fromtimestamp(int(epoch), tz=UTC) if epoch else None


def _row_for(
    user_id: Any = None, subscription_id: str | None = None, customer: str | None = None
) -> Subscription | None:
    """Find (or, knowing the user, create) the row an event is about."""
    row = None
    if subscription_id:
        row = db.session.scalar(
            select(Subscription).where(Subscription.subscription_id == subscription_id)
        )
    if row is None and customer:
        row = db.session.scalar(select(Subscription).where(Subscription.customer_id == customer))
    if row is None and user_id:
        try:
            user = db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            user = None
        if user is not None:
            row = subscription_of(user) or Subscription(user=user)
            db.session.add(row)
    return row


def _apply_subscription(obj: dict[str, Any], deleted: bool) -> None:
    metadata = obj.get("metadata") or {}
    row = _row_for(metadata.get("user_id"), obj.get("id"), obj.get("customer"))
    if row is None:
        logger.warning("Billing event for an unknown subscription %s", obj.get("id"))
        return
    items = (obj.get("items") or {}).get("data") or []
    first = items[0] if items else {}
    row.subscription_id = obj.get("id") or row.subscription_id
    row.customer_id = obj.get("customer") or row.customer_id
    row.status = "canceled" if deleted else str(obj.get("status") or row.status)
    row.plan = (
        plan_for_price((first.get("price") or {}).get("id")) or metadata.get("plan") or row.plan
    )
    row.trial_ends_at = _when(obj.get("trial_end"))
    # Desde la versión 2025-03 de la API el fin del periodo va en cada línea.
    row.current_period_end = _when(obj.get("current_period_end") or first.get("current_period_end"))
    row.cancel_at_period_end = bool(obj.get("cancel_at_period_end"))


def _apply_checkout(obj: dict[str, Any]) -> None:
    metadata = obj.get("metadata") or {}
    row = _row_for(obj.get("client_reference_id"), obj.get("subscription"), obj.get("customer"))
    if row is None:
        logger.warning("Checkout completed for an unknown user %s", obj.get("client_reference_id"))
        return
    row.customer_id = obj.get("customer") or row.customer_id
    row.subscription_id = obj.get("subscription") or row.subscription_id
    row.plan = metadata.get("plan") or row.plan
    if row.status == "none":
        row.status = "incomplete"  # el evento de la suscripción trae el estado real


HANDLERS = {
    "checkout.session.completed": lambda obj: _apply_checkout(obj),
    "customer.subscription.created": lambda obj: _apply_subscription(obj, deleted=False),
    "customer.subscription.updated": lambda obj: _apply_subscription(obj, deleted=False),
    "customer.subscription.deleted": lambda obj: _apply_subscription(obj, deleted=True),
}


def apply_event(event: dict[str, Any]) -> bool:
    """Apply one Stripe-shaped event; ``False`` if it was already applied or is ignored.

    Each event id is recorded in the same transaction as its effect, so a webhook
    that Stripe retries (it does, until it gets a 2xx) changes nothing the second time.
    """
    event_id = str(event.get("id") or "")
    event_type = str(event.get("type") or "")
    handler = HANDLERS.get(event_type)
    if not event_id or handler is None:
        return False
    if db.session.scalar(select(BillingEvent).where(BillingEvent.event_id == event_id)):
        return False
    handler((event.get("data") or {}).get("object") or {})
    db.session.add(BillingEvent(event_id=event_id, event_type=event_type))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()  # el mismo evento llegó a la vez por otro proceso
        return False
    logger.info("Billing event %s applied (%s)", event_type, event_id)
    return True
