"""Training routines (versioned), their days and the prescription per exercise."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.engine.enums import PlanStatus, SplitType
from app.extensions import db
from app.models.base import JSONType, SoftDeleteMixin, TimestampMixin, UTCDateTime, enum_column

if TYPE_CHECKING:
    from app.models.exercise import Exercise
    from app.models.profile import Profile
    from app.models.user import User


class Routine(TimestampMixin, SoftDeleteMixin, db.Model):
    """A mesocycle generated for one profile version."""

    __tablename__ = "routines"
    __table_args__ = (
        UniqueConstraint("user_id", "version"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("days_per_week BETWEEN 1 AND 7", name="days_range"),
        CheckConstraint("mesocycle_weeks BETWEEN 3 AND 8", name="mesocycle_range"),
        CheckConstraint("deload_every_weeks BETWEEN 3 AND 12", name="deload_range"),
        Index("ix_routines_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    split_type: Mapped[SplitType] = mapped_column(enum_column(SplitType), nullable=False)
    days_per_week: Mapped[int] = mapped_column(nullable=False)
    mesocycle_weeks: Mapped[int] = mapped_column(default=4, nullable=False)
    deload_every_weeks: Mapped[int] = mapped_column(default=4, nullable=False)
    status: Mapped[PlanStatus] = mapped_column(
        enum_column(PlanStatus), default=PlanStatus.DRAFT, nullable=False
    )
    starts_on: Mapped[date | None] = mapped_column(Date)
    inputs_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    superseded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    user: Mapped[User] = relationship(back_populates="routines")
    profile: Mapped[Profile] = relationship()
    days: Mapped[list[RoutineDay]] = relationship(
        back_populates="routine", cascade="all, delete-orphan", order_by="RoutineDay.day_index"
    )

    def __repr__(self) -> str:
        return f"<Routine user={self.user_id} v{self.version} {self.split_type}>"


class RoutineDay(TimestampMixin, db.Model):
    """One training day of a routine (e.g. 'Día 2: Tirón')."""

    __tablename__ = "routine_days"
    __table_args__ = (
        UniqueConstraint("routine_id", "day_index"),
        CheckConstraint("day_index BETWEEN 1 AND 7", name="day_index_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    routine_id: Mapped[int] = mapped_column(
        ForeignKey("routines.id", ondelete="CASCADE"), nullable=False
    )
    day_index: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    focus: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    estimated_minutes: Mapped[int | None] = mapped_column()
    notes: Mapped[str | None] = mapped_column(String(300))

    routine: Mapped[Routine] = relationship(back_populates="days")
    exercises: Mapped[list[RoutineExercise]] = relationship(
        back_populates="day", cascade="all, delete-orphan", order_by="RoutineExercise.position"
    )

    def __repr__(self) -> str:
        return f"<RoutineDay {self.day_index} {self.name}>"


class RoutineExercise(TimestampMixin, db.Model):
    """Prescription of one exercise inside a routine day."""

    __tablename__ = "routine_exercises"
    __table_args__ = (
        UniqueConstraint("routine_day_id", "position"),
        CheckConstraint("position >= 1", name="position_positive"),
        CheckConstraint("sets BETWEEN 1 AND 12", name="sets_range"),
        CheckConstraint("rep_min >= 1 AND rep_max >= rep_min", name="rep_range"),
        CheckConstraint("rir_start BETWEEN 0 AND 6 AND rir_end BETWEEN 0 AND 6", name="rir_range"),
        CheckConstraint("rest_seconds BETWEEN 15 AND 600", name="rest_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    routine_day_id: Mapped[int] = mapped_column(
        ForeignKey("routine_days.id", ondelete="CASCADE"), nullable=False
    )
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[int] = mapped_column(nullable=False)
    sets: Mapped[int] = mapped_column(nullable=False)
    rep_min: Mapped[int] = mapped_column(nullable=False)
    rep_max: Mapped[int] = mapped_column(nullable=False)
    rir_start: Mapped[int] = mapped_column(default=3, nullable=False)
    rir_end: Mapped[int] = mapped_column(default=1, nullable=False)
    rest_seconds: Mapped[int] = mapped_column(nullable=False)
    tempo: Mapped[str | None] = mapped_column(String(12))
    load_increment_kg: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(String(200))

    day: Mapped[RoutineDay] = relationship(back_populates="exercises")
    exercise: Mapped[Exercise] = relationship()

    def __repr__(self) -> str:
        reps = f"{self.sets}x{self.rep_min}-{self.rep_max}"
        return f"<RoutineExercise {self.position} ex={self.exercise_id} {reps}>"
