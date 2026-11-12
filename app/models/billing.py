"""Subscription state, as told by the payment gateway (Stripe or the simulated one).

The gateway is the source of truth: these rows only mirror what its events
say, so the app can answer «is this person Pro?» without calling it on every
request. Statuses are kept as the gateway's own strings (``trialing``,
``active``, ``past_due``, ``canceled``…): Stripe adds new ones over time and
an unknown status must be stored, not rejected.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, UTCDateTime, utcnow

if TYPE_CHECKING:
    from app.models.user import User

# Statuses that give access to Pro. ``past_due`` keeps access while the
# gateway retries the payment (Stripe's «smart retries»), as Stripe advises.
ACTIVE_STATUSES = frozenset({"trialing", "active", "past_due"})
# Derecho de desistimiento (Directiva 2011/83/UE; art. 102 TRLGDCU): 14 días naturales.
WITHDRAWAL_PERIOD = timedelta(days=14)


class Subscription(TimestampMixin, db.Model):
    """One person's subscription (at most one row per user)."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    customer_id: Mapped[str | None] = mapped_column(String(80), index=True)
    subscription_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    plan: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="none", nullable=False)
    trial_ends_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    current_period_end: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cancel_at_period_end: Mapped[bool] = mapped_column(default=False, nullable=False)
    # Alta de la suscripción en curso: cuenta el plazo de desistimiento de 14 días.
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Hora del último evento aplicado: Stripe no garantiza el orden de los eventos.
    last_event_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    user: Mapped[User] = relationship(back_populates="subscription")

    @property
    def is_active(self) -> bool:
        """The person has Pro right now."""
        return self.status in ACTIVE_STATUSES

    @property
    def is_trial(self) -> bool:
        """In the free trial."""
        return self.status == "trialing"

    def can_withdraw(self, now: datetime) -> bool:
        """Within the 14-day withdrawal period of the current subscription."""
        if not self.is_active or self.started_at is None:
            return False
        return now - self.started_at <= WITHDRAWAL_PERIOD

    def __repr__(self) -> str:
        return f"<Subscription user={self.user_id} {self.plan} {self.status}>"


class BillingEvent(db.Model):
    """Gateway events already applied: a retried webhook must not apply twice."""

    __tablename__ = "billing_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<BillingEvent {self.event_type} {self.event_id}>"
