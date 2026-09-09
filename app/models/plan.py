"""Nutrition plans (versioned), their meals and the log of every recalculation."""

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
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.engine.enums import (
    AdjustmentReason,
    BmrMethod,
    Confidence,
    Goal,
    MealTiming,
    PlanStatus,
)
from app.extensions import db
from app.models.base import JSONType, SoftDeleteMixin, TimestampMixin, UTCDateTime, enum_column

if TYPE_CHECKING:
    from app.models.profile import Profile
    from app.models.routine import Routine
    from app.models.user import User


class Plan(TimestampMixin, SoftDeleteMixin, db.Model):
    """A nutrition plan produced by the engine for one profile version.

    Scalar columns hold what the dashboard queries; ``details`` keeps the full
    engine output (ranges, explanations, warnings, carb-cycling days) and
    ``inputs_snapshot`` the exact inputs, so any plan can be reproduced later
    even if the profile changed.
    """

    __tablename__ = "plans"
    __table_args__ = (
        UniqueConstraint("user_id", "version"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("calorie_target BETWEEN 500 AND 10000", name="calorie_range"),
        CheckConstraint("protein_g >= 0 AND carbs_g >= 0 AND fat_g >= 0", name="macros_positive"),
        Index("ix_plans_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    routine_id: Mapped[int | None] = mapped_column(ForeignKey("routines.id", ondelete="SET NULL"))
    version: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[PlanStatus] = mapped_column(
        enum_column(PlanStatus), default=PlanStatus.DRAFT, nullable=False
    )
    goal: Mapped[Goal] = mapped_column(enum_column(Goal), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date)

    calorie_target: Mapped[int] = mapped_column(nullable=False)
    protein_g: Mapped[float] = mapped_column(Float, nullable=False)
    carbs_g: Mapped[float] = mapped_column(Float, nullable=False)
    fat_g: Mapped[float] = mapped_column(Float, nullable=False)
    fiber_g: Mapped[float] = mapped_column(Float, nullable=False)
    water_ml: Mapped[int] = mapped_column(nullable=False)
    bmr_kcal: Mapped[float] = mapped_column(Float, nullable=False)
    tdee_kcal: Mapped[float] = mapped_column(Float, nullable=False)
    bmr_method: Mapped[BmrMethod] = mapped_column(enum_column(BmrMethod), nullable=False)
    confidence: Mapped[Confidence] = mapped_column(enum_column(Confidence), nullable=False)
    inputs_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    superseded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    user: Mapped[User] = relationship(back_populates="plans")
    profile: Mapped[Profile] = relationship()
    routine: Mapped[Routine | None] = relationship()
    meals: Mapped[list[Meal]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="Meal.position"
    )

    def __repr__(self) -> str:
        return f"<Plan user={self.user_id} v{self.version} {self.calorie_target} kcal>"


class Meal(TimestampMixin, db.Model):
    """Calorie and macro share of one meal inside a plan."""

    __tablename__ = "meals"
    __table_args__ = (
        UniqueConstraint("plan_id", "position"),
        CheckConstraint("position >= 1", name="position_positive"),
        CheckConstraint("calories >= 0", name="calories_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    timing: Mapped[MealTiming] = mapped_column(
        enum_column(MealTiming), default=MealTiming.REGULAR, nullable=False
    )
    calories: Mapped[int] = mapped_column(nullable=False)
    protein_g: Mapped[float] = mapped_column(Float, nullable=False)
    carbs_g: Mapped[float] = mapped_column(Float, nullable=False)
    fat_g: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(200))

    plan: Mapped[Plan] = relationship(back_populates="meals")

    def __repr__(self) -> str:
        return f"<Meal {self.position} {self.name}>"


class PlanAdjustment(TimestampMixin, db.Model):
    """Audit trail of every recalculation: why, what was observed, what changed."""

    __tablename__ = "plan_adjustments"
    __table_args__ = (Index("ix_plan_adjustments_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), nullable=False)
    previous_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("plans.id", ondelete="SET NULL")
    )
    reason: Mapped[AdjustmentReason] = mapped_column(enum_column(AdjustmentReason), nullable=False)
    expected_weekly_change_kg: Mapped[float | None] = mapped_column(Float)
    observed_weekly_change_kg: Mapped[float | None] = mapped_column(Float)
    observed_tdee_kcal: Mapped[float | None] = mapped_column(Float)
    calorie_delta: Mapped[int | None] = mapped_column()
    steps_delta: Mapped[int | None] = mapped_column()
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)

    user: Mapped[User] = relationship(back_populates="plan_adjustments")
    plan: Mapped[Plan] = relationship(foreign_keys=[plan_id])
    previous_plan: Mapped[Plan | None] = relationship(foreign_keys=[previous_plan_id])

    def __repr__(self) -> str:
        return f"<PlanAdjustment {self.reason} plan={self.plan_id}>"
