"""Logged training sessions and the sets performed in them."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.engine.enums import SetType, WorkoutStatus
from app.extensions import db
from app.models.base import JSONType, SoftDeleteMixin, TimestampMixin, UTCDateTime, enum_column

if TYPE_CHECKING:
    from app.models.exercise import Exercise
    from app.models.routine import RoutineDay, RoutineExercise
    from app.models.user import User


class WorkoutSession(TimestampMixin, SoftDeleteMixin, db.Model):
    """A gym session, planned (linked to a routine day) or ad hoc."""

    __tablename__ = "workout_sessions"
    __table_args__ = (
        CheckConstraint(
            "perceived_fatigue IS NULL OR perceived_fatigue BETWEEN 1 AND 5", name="fatigue_range"
        ),
        CheckConstraint("finished_at IS NULL OR finished_at >= started_at", name="finish_after"),
        Index("ix_workout_sessions_user_started", "user_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    routine_day_id: Mapped[int | None] = mapped_column(
        ForeignKey("routine_days.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status: Mapped[WorkoutStatus] = mapped_column(
        enum_column(WorkoutStatus), default=WorkoutStatus.IN_PROGRESS, nullable=False
    )
    mesocycle_week: Mapped[int | None] = mapped_column()
    perceived_fatigue: Mapped[int | None] = mapped_column()
    # Respuesta de un toque al empezar: good | ok | bad | skip | normal (pidió entrenar normal).
    sleep_quality: Mapped[str | None] = mapped_column(String(10))
    notes: Mapped[str | None] = mapped_column(Text)
    # {routine_exercise_id (as str): exercise_id} chosen for this session only.
    substitutions: Mapped[dict[str, int] | None] = mapped_column(JSONType)

    user: Mapped[User] = relationship(back_populates="workout_sessions")
    routine_day: Mapped[RoutineDay | None] = relationship()
    sets: Mapped[list[SetLog]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="(SetLog.exercise_id, SetLog.set_index)",
    )

    def __repr__(self) -> str:
        return f"<WorkoutSession {self.id} {self.status}>"


class SetLog(TimestampMixin, db.Model):
    """One set: reps, load and reps in reserve."""

    __tablename__ = "set_logs"
    __table_args__ = (
        UniqueConstraint("workout_session_id", "exercise_id", "set_index"),
        CheckConstraint("set_index >= 1", name="set_index_positive"),
        CheckConstraint("reps BETWEEN 0 AND 200", name="reps_range"),
        CheckConstraint("weight_kg BETWEEN 0 AND 1000", name="weight_range"),
        CheckConstraint("rir IS NULL OR rir BETWEEN 0 AND 10", name="rir_range"),
        Index("ix_set_logs_exercise_completed", "exercise_id", "completed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workout_session_id: Mapped[int] = mapped_column(
        ForeignKey("workout_sessions.id", ondelete="CASCADE"), nullable=False
    )
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id", ondelete="RESTRICT"), nullable=False
    )
    routine_exercise_id: Mapped[int | None] = mapped_column(
        ForeignKey("routine_exercises.id", ondelete="SET NULL")
    )
    set_index: Mapped[int] = mapped_column(nullable=False)
    set_type: Mapped[SetType] = mapped_column(
        enum_column(SetType), default=SetType.WORKING, nullable=False
    )
    reps: Mapped[int] = mapped_column(nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    rir: Mapped[int | None] = mapped_column()
    completed_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(200))

    session: Mapped[WorkoutSession] = relationship(back_populates="sets")
    exercise: Mapped[Exercise] = relationship()
    routine_exercise: Mapped[RoutineExercise | None] = relationship()

    def __repr__(self) -> str:
        return f"<SetLog ex={self.exercise_id} #{self.set_index} {self.reps}x{self.weight_kg}>"
