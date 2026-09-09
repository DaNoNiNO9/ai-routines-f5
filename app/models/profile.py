"""Questionnaire answers, versioned: a change creates a new row, never an update."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.engine.enums import (
    ActivityIntensity,
    Aggressiveness,
    BodyFatMethod,
    DietPattern,
    Goal,
    InjuryArea,
    JobActivity,
    Level,
    Severity,
    Sex,
    TrainingExperience,
    TrainingLocation,
)
from app.extensions import db
from app.models.base import JSONType, TimestampMixin, UTCDateTime, enum_column, utcnow

if TYPE_CHECKING:
    from app.models.user import User


class Profile(TimestampMixin, db.Model):
    """One version of a user's questionnaire (blocks A to E plus safety flags).

    Ranges enforced by CHECK constraints are deliberately wide: they reject
    garbage, not unusual people. Clinical decisions belong to the engine and
    ``safety.py``.
    """

    __tablename__ = "profiles"
    __table_args__ = (
        UniqueConstraint("user_id", "version"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("height_cm BETWEEN 100 AND 250", name="height_range"),
        CheckConstraint("weight_kg BETWEEN 25 AND 350", name="weight_range"),
        CheckConstraint("neck_cm IS NULL OR neck_cm BETWEEN 20 AND 80", name="neck_range"),
        CheckConstraint("waist_cm IS NULL OR waist_cm BETWEEN 40 AND 250", name="waist_range"),
        CheckConstraint("hip_cm IS NULL OR hip_cm BETWEEN 50 AND 250", name="hip_range"),
        CheckConstraint(
            "body_fat_pct IS NULL OR body_fat_pct BETWEEN 2 AND 70", name="body_fat_range"
        ),
        CheckConstraint("daily_steps IS NULL OR daily_steps BETWEEN 0 AND 60000", name="steps"),
        CheckConstraint("sleep_hours BETWEEN 0 AND 16", name="sleep_range"),
        CheckConstraint("stress_level BETWEEN 1 AND 5", name="stress_range"),
        CheckConstraint("training_days_per_week BETWEEN 1 AND 7", name="days_range"),
        CheckConstraint("session_minutes BETWEEN 15 AND 240", name="session_range"),
        CheckConstraint("meals_per_day BETWEEN 1 AND 8", name="meals_range"),
        Index("ix_profiles_user_current", "user_id", "superseded_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    superseded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    # Block A: anthropometrics
    sex: Mapped[Sex] = mapped_column(enum_column(Sex), nullable=False)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    height_cm: Mapped[float] = mapped_column(Float, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    neck_cm: Mapped[float | None] = mapped_column(Float)
    waist_cm: Mapped[float | None] = mapped_column(Float)
    hip_cm: Mapped[float | None] = mapped_column(Float)
    body_fat_pct: Mapped[float | None] = mapped_column(Float)
    body_fat_method: Mapped[BodyFatMethod] = mapped_column(
        enum_column(BodyFatMethod), default=BodyFatMethod.NONE, nullable=False
    )

    # Block B: activity and lifestyle
    job_activity: Mapped[JobActivity] = mapped_column(enum_column(JobActivity), nullable=False)
    daily_steps: Mapped[int | None] = mapped_column()
    sleep_hours: Mapped[float] = mapped_column(Float, nullable=False)
    stress_level: Mapped[int] = mapped_column(nullable=False)
    other_activity_type: Mapped[str | None] = mapped_column(String(80))
    other_activity_sessions_per_week: Mapped[int] = mapped_column(default=0, nullable=False)
    other_activity_minutes: Mapped[int] = mapped_column(default=0, nullable=False)
    other_activity_intensity: Mapped[ActivityIntensity | None] = mapped_column(
        enum_column(ActivityIntensity)
    )

    # Block C: training
    training_experience: Mapped[TrainingExperience] = mapped_column(
        enum_column(TrainingExperience), nullable=False
    )
    training_days_per_week: Mapped[int] = mapped_column(nullable=False)
    session_minutes: Mapped[int] = mapped_column(nullable=False)
    training_location: Mapped[TrainingLocation] = mapped_column(
        enum_column(TrainingLocation), nullable=False
    )
    priority_muscles: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    disliked_exercises: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    preferred_exercises: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)

    # Block D: goal
    goal: Mapped[Goal] = mapped_column(enum_column(Goal), nullable=False)
    aggressiveness: Mapped[Aggressiveness] = mapped_column(
        enum_column(Aggressiveness), default=Aggressiveness.MODERATE, nullable=False
    )
    target_date: Mapped[date | None] = mapped_column(Date)
    target_weight_kg: Mapped[float | None] = mapped_column(Float)

    # Block E: nutrition
    meals_per_day: Mapped[int] = mapped_column(default=4, nullable=False)
    diet_pattern: Mapped[DietPattern] = mapped_column(
        enum_column(DietPattern), default=DietPattern.OMNIVORE, nullable=False
    )
    food_aversions: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    allergies: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    budget_level: Mapped[Level] = mapped_column(
        enum_column(Level, name="budget_level"), default=Level.MEDIUM, nullable=False
    )
    cooking_time: Mapped[Level] = mapped_column(
        enum_column(Level, name="cooking_time"), default=Level.MEDIUM, nullable=False
    )
    alcohol_drinks_per_week: Mapped[int] = mapped_column(default=0, nullable=False)
    caffeine_cups_per_day: Mapped[int] = mapped_column(default=0, nullable=False)

    # Safety flags (hard stops in safety.py)
    is_pregnant_or_breastfeeding: Mapped[bool] = mapped_column(default=False, nullable=False)
    has_eating_disorder_history: Mapped[bool] = mapped_column(default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="profiles")
    injuries: Mapped[list[Injury]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", order_by="Injury.area"
    )

    @property
    def is_current(self) -> bool:
        """Whether this version is the one in force."""
        return self.superseded_at is None

    def supersede(self) -> None:
        """Mark this version as replaced by a newer one."""
        self.superseded_at = utcnow()

    def age_on(self, day: date) -> int:
        """Completed years on ``day``."""
        years = day.year - self.birth_date.year
        if (day.month, day.day) < (self.birth_date.month, self.birth_date.day):
            years -= 1
        return years

    def __repr__(self) -> str:
        return f"<Profile user={self.user_id} v{self.version}>"


class Injury(TimestampMixin, db.Model):
    """Injury or limitation declared in a profile version."""

    __tablename__ = "injuries"
    __table_args__ = (UniqueConstraint("profile_id", "area"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    area: Mapped[InjuryArea] = mapped_column(enum_column(InjuryArea), nullable=False)
    severity: Mapped[Severity] = mapped_column(enum_column(Severity), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(200))

    profile: Mapped[Profile] = relationship(back_populates="injuries")

    def __repr__(self) -> str:
        return f"<Injury {self.area} {self.severity}>"
