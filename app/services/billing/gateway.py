"""The contract every payment gateway fulfils."""

from __future__ import annotations

from typing import Any, Protocol

from app.models import Subscription, User


class BillingError(Exception):
    """A gateway operation failed; ``reason`` is a stable code for the UI."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class Gateway(Protocol):
    """What the app needs from a payment gateway."""

    name: str

    def checkout_url(
        self, user: User, plan: str, success_url: str, cancel_url: str, trial_days: int
    ) -> str:
        """Where to send the person to pay (and start the trial)."""
        ...

    def portal_url(self, subscription: Subscription, return_url: str) -> str:
        """Where the person changes card, plan or cancels."""
        ...

    def cancel_now(self, subscription: Subscription) -> None:
        """End the subscription immediately (used when the account is deleted)."""
        ...

    def parse_webhook(self, payload: bytes, signature: str | None) -> dict[str, Any]:
        """A verified event from the gateway's webhook, or ``BillingError``."""
        ...
