"""Accounts and the equipment each user owns."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.extensions import db
from app.models.base import SoftDeleteMixin, TimestampMixin, UTCDateTime, utcnow

if TYPE_CHECKING:
    from app.models.exercise import Equipment
    from app.models.onboarding import QuestionnaireDraft
    from app.models.plan import Plan, PlanAdjustment
    from app.models.profile import Profile
    from app.models.routine import Routine
    from app.models.tracking import ActivityLog, BodyMeasurement, IntakeLog, WeightLog
    from app.models.workout import WorkoutSession

EMAIL_MAX_LENGTH = 254
DISPLAY_NAME_MAX_LENGTH = 80

user_equipment = Table(
    "user_equipment",
    db.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("equipment_id", ForeignKey("equipment.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", UTCDateTime, default=utcnow, nullable=False),
)


class User(UserMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    """Registered person. Owns every other user-scoped row (cascade on delete)."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("length(email) >= 6", name="email_min_length"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(EMAIL_MAX_LENGTH), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(DISPLAY_NAME_MAX_LENGTH), nullable=False)
    locale: Mapped[str] = mapped_column(String(5), default="es", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Madrid", nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    consent_accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    profiles: Mapped[list[Profile]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="Profile.version"
    )
    equipment: Mapped[list[Equipment]] = relationship(secondary=user_equipment)
    weight_logs: Mapped[list[WeightLog]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="WeightLog.logged_on"
    )
    body_measurements: Mapped[list[BodyMeasurement]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="BodyMeasurement.measured_on"
    )
    intake_logs: Mapped[list[IntakeLog]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="IntakeLog.logged_on"
    )
    activity_logs: Mapped[list[ActivityLog]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="ActivityLog.logged_on"
    )
    plans: Mapped[list[Plan]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="Plan.version"
    )
    plan_adjustments: Mapped[list[PlanAdjustment]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="PlanAdjustment.created_at"
    )
    routines: Mapped[list[Routine]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="Routine.version"
    )
    workout_sessions: Mapped[list[WorkoutSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="WorkoutSession.started_at"
    )
    questionnaire_draft: Mapped[QuestionnaireDraft | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )

    def today(self) -> date:
        """Calendar date in the user's time zone (UTC if the zone is unknown)."""
        try:
            return datetime.now(ZoneInfo(self.timezone)).date()
        except (ZoneInfoNotFoundError, ValueError):
            return datetime.now(UTC).date()

    @validates("email")
    def _normalise_email(self, _key: str, value: str) -> str:
        return value.strip().lower()

    @property
    def current_profile(self) -> Profile | None:
        """The profile version in force (the one not yet superseded)."""
        for profile in reversed(self.profiles):
            if profile.superseded_at is None:
                return profile
        return None

    def __repr__(self) -> str:
        return f"<User {self.id} {self.email}>"
