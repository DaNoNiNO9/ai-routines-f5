"""Explicit consent for health data (RGPD art. 9.2.a), and withdrawing it.

Weight, measurements, sleep, food, training and injuries are health data, and
the type of diet (halal, kosher…) can reveal religious beliefs: special
categories. They are processed only with explicit consent, given separately
from the account terms and recorded with its date and the version of the text.

Withdrawing consent is as easy as giving it, and it means exactly what it says:
every piece of health data is deleted for good, and nothing is shown again until
consent is given anew. The account, its login and the subscription remain, so
the person can come back or delete the account too.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.extensions import db
from app.models import (
    ActivityLog,
    BodyMeasurement,
    FoodEntry,
    IntakeLog,
    Plan,
    PlanAdjustment,
    Profile,
    QuestionnaireDraft,
    Routine,
    User,
    WeightLog,
    WorkoutSession,
)
from app.models.privacy import ERASURE_ACCOUNT, ERASURE_HEALTH, ErasureRecord

logger = logging.getLogger(__name__)

# Sube cuando cambie el texto del consentimiento: se guarda con cada aceptación.
CONSENT_VERSION = "2026-11-12"

# Tablas con datos de salud de una persona (todas cuelgan de users.id).
HEALTH_TABLES = (
    FoodEntry,
    IntakeLog,
    WeightLog,
    BodyMeasurement,
    ActivityLog,
    PlanAdjustment,
    QuestionnaireDraft,
)


def give_consent(user: User) -> None:
    """Record explicit consent now, with the version of the text accepted."""
    user.health_consent_at = datetime.now(UTC)
    user.health_consent_version = CONSENT_VERSION
    db.session.commit()
    logger.info("Health-data consent given by user %s (v%s)", user.id, CONSENT_VERSION)


def record_erasure(user_id: int, kind: str) -> None:
    """Note an erasure (no personal data) so a restored backup can repeat it."""
    db.session.add(ErasureRecord(user_id=user_id, kind=kind))


def withdraw_consent(user: User, *, record: bool = True) -> None:
    """Delete every piece of health data and stop processing it.

    ORM deletes for the rows with children (sessions and their sets, routines
    and their days, plans and their meals, profiles and their injuries) so the
    cascades run; bulk deletes for the flat tables.
    """
    for model in HEALTH_TABLES:
        db.session.execute(delete(model).where(model.user_id == user.id))
    for model in (WorkoutSession, Routine, Plan, Profile):
        for row in db.session.scalars(select(model).where(model.user_id == user.id)):
            db.session.delete(row)
    user.equipment = []  # el material deja ver lesiones y limitaciones
    user.health_consent_at = None
    user.health_consent_version = None
    if record:
        record_erasure(user.id, ERASURE_HEALTH)
    db.session.commit()
    logger.info("Health-data consent withdrawn by user %s: health data deleted", user.id)


@dataclass(frozen=True)
class ReapplyResult:
    """What a re-application after a restore did."""

    accounts: int
    health: int
    purged: int


def purge_erasure_log(keep_days: int) -> int:
    """Forget erasures older than every backup that could still be restored."""
    cutoff = datetime.now(UTC) - timedelta(days=keep_days)
    result = db.session.execute(delete(ErasureRecord).where(ErasureRecord.erased_at < cutoff))
    db.session.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def reapply_erasures(keep_days: int) -> ReapplyResult:
    """After restoring a backup, erase again what was erased since it was taken.

    Whatever happened after the erasure is respected: an account number now
    belonging to an account created later is not touched, and health data is
    kept if consent was given anew after it was withdrawn (that data is new).
    """
    purged = purge_erasure_log(keep_days)
    accounts = health = 0
    records = db.session.scalars(select(ErasureRecord).order_by(ErasureRecord.erased_at)).all()
    for record in records:
        user = db.session.get(User, record.user_id)
        if user is None or user.created_at > record.erased_at:
            continue
        if record.kind == ERASURE_ACCOUNT:
            db.session.delete(user)
            db.session.commit()
            accounts += 1
            logger.info("Restored account %s deleted again", record.user_id)
        elif record.kind == ERASURE_HEALTH:
            consent = user.health_consent_at
            if consent is None or consent > record.erased_at:
                continue  # nada que borrar, o datos dados con un consentimiento nuevo
            withdraw_consent(user, record=False)
            health += 1
            logger.info("Restored health data of user %s deleted again", record.user_id)
    return ReapplyResult(accounts=accounts, health=health, purged=purged)
