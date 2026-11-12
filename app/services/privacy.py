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
from datetime import UTC, datetime

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


def withdraw_consent(user: User) -> None:
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
    db.session.commit()
    logger.info("Health-data consent withdrawn by user %s: health data deleted", user.id)
