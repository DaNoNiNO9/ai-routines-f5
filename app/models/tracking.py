"""Daily and weekly logs: weight, body measurements, intake and activity.

One row per user and day for each log type (unique constraints). Editing a
day replaces its values; there is no history of edits by design.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.engine.enums import BodyFatMethod, CardioKind
from app.extensions import db
from app.models.base import TimestampMixin, enum_column

if TYPE_CHECKING:
    from app.models.user import User


class WeightLog(TimestampMixin, db.Model):
    """Morning body weight. The adjustment engine works on its 7-day moving average."""

    __tablename__ = "weight_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "logged_on"),
        CheckConstraint("weight_kg BETWEEN 25 AND 350", name="weight_range"),
        Index("ix_weight_logs_user_logged_on", "user_id", "logged_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    logged_on: Mapped[date] = mapped_column(Date, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(200))

    user: Mapped[User] = relationship(back_populates="weight_logs")

    def __repr__(self) -> str:
        return f"<WeightLog {self.logged_on} {self.weight_kg} kg>"


class BodyMeasurement(TimestampMixin, db.Model):
    """Weekly circumferences (cm) and optional body-fat estimate."""

    __tablename__ = "body_measurements"
    __table_args__ = (
        UniqueConstraint("user_id", "measured_on"),
        CheckConstraint("neck_cm IS NULL OR neck_cm BETWEEN 20 AND 80", name="neck_range"),
        CheckConstraint("waist_cm IS NULL OR waist_cm BETWEEN 40 AND 250", name="waist_range"),
        CheckConstraint("hip_cm IS NULL OR hip_cm BETWEEN 50 AND 250", name="hip_range"),
        CheckConstraint(
            "body_fat_pct IS NULL OR body_fat_pct BETWEEN 2 AND 70", name="body_fat_range"
        ),
        Index("ix_body_measurements_user_measured_on", "user_id", "measured_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    measured_on: Mapped[date] = mapped_column(Date, nullable=False)
    neck_cm: Mapped[float | None] = mapped_column(Float)
    chest_cm: Mapped[float | None] = mapped_column(Float)
    waist_cm: Mapped[float | None] = mapped_column(Float)
    hip_cm: Mapped[float | None] = mapped_column(Float)
    arm_cm: Mapped[float | None] = mapped_column(Float)
    thigh_cm: Mapped[float | None] = mapped_column(Float)
    calf_cm: Mapped[float | None] = mapped_column(Float)
    body_fat_pct: Mapped[float | None] = mapped_column(Float)
    body_fat_method: Mapped[BodyFatMethod] = mapped_column(
        enum_column(BodyFatMethod), default=BodyFatMethod.NONE, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(String(200))

    user: Mapped[User] = relationship(back_populates="body_measurements")

    def __repr__(self) -> str:
        return f"<BodyMeasurement {self.measured_on}>"


class IntakeLog(TimestampMixin, db.Model):
    """What was actually eaten in a day, entered by hand (decision D-07)."""

    __tablename__ = "intake_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "logged_on"),
        CheckConstraint("calories BETWEEN 0 AND 20000", name="calories_range"),
        CheckConstraint("protein_g IS NULL OR protein_g BETWEEN 0 AND 1000", name="protein"),
        CheckConstraint("carbs_g IS NULL OR carbs_g BETWEEN 0 AND 2000", name="carbs"),
        CheckConstraint("fat_g IS NULL OR fat_g BETWEEN 0 AND 1000", name="fat"),
        CheckConstraint(
            "adherence_pct IS NULL OR adherence_pct BETWEEN 0 AND 100", name="adherence"
        ),
        Index("ix_intake_logs_user_logged_on", "user_id", "logged_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    logged_on: Mapped[date] = mapped_column(Date, nullable=False)
    calories: Mapped[int] = mapped_column(nullable=False)
    protein_g: Mapped[float | None] = mapped_column(Float)
    carbs_g: Mapped[float | None] = mapped_column(Float)
    fat_g: Mapped[float | None] = mapped_column(Float)
    adherence_pct: Mapped[int | None] = mapped_column()
    notes: Mapped[str | None] = mapped_column(String(200))

    user: Mapped[User] = relationship(back_populates="intake_logs")

    def __repr__(self) -> str:
        return f"<IntakeLog {self.logged_on} {self.calories} kcal>"


class ActivityLog(TimestampMixin, db.Model):
    """Steps and cardio done in a day (NEAT and EAT inputs for the adjustment engine)."""

    __tablename__ = "activity_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "logged_on"),
        CheckConstraint("steps IS NULL OR steps BETWEEN 0 AND 100000", name="steps_range"),
        CheckConstraint(
            "cardio_minutes IS NULL OR cardio_minutes BETWEEN 0 AND 600", name="cardio_range"
        ),
        Index("ix_activity_logs_user_logged_on", "user_id", "logged_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    logged_on: Mapped[date] = mapped_column(Date, nullable=False)
    steps: Mapped[int | None] = mapped_column()
    cardio_kind: Mapped[CardioKind | None] = mapped_column(enum_column(CardioKind))
    cardio_minutes: Mapped[int | None] = mapped_column()
    notes: Mapped[str | None] = mapped_column(String(200))

    user: Mapped[User] = relationship(back_populates="activity_logs")

    def __repr__(self) -> str:
        return f"<ActivityLog {self.logged_on}>"


class FoodEntry(TimestampMixin, db.Model):
    """One food eaten on a day, in grams, with its values already worked out.

    The values per 100 g are copied at the moment of logging, so the day does
    not change if Open Food Facts edits the product later. While a day has
    entries, its ``IntakeLog`` totals are their sum (``services.food``).
    """

    __tablename__ = "food_entries"
    __table_args__ = (
        CheckConstraint("grams > 0 AND grams <= 5000", name="grams_range"),
        CheckConstraint("kcal_100g >= 0 AND kcal_100g <= 950", name="kcal_range"),
        Index("ix_food_entries_user_logged_on", "user_id", "logged_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    logged_on: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # basic | off
    code: Mapped[str | None] = mapped_column(String(40))  # código de barras o clave de la tabla
    grams: Mapped[float] = mapped_column(Float, nullable=False)
    kcal_100g: Mapped[float] = mapped_column(Float, nullable=False)
    protein_100g: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    carbs_100g: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    fat_100g: Mapped[float] = mapped_column(Float, nullable=False, default=0)

    user: Mapped[User] = relationship(back_populates="food_entries")

    def _part(self, per_100g: float) -> float:
        return per_100g * self.grams / 100

    @property
    def kcal(self) -> float:
        """Calories of this portion."""
        return self._part(self.kcal_100g)

    @property
    def protein_g(self) -> float:
        """Protein of this portion."""
        return self._part(self.protein_100g)

    @property
    def carbs_g(self) -> float:
        """Carbohydrates of this portion."""
        return self._part(self.carbs_100g)

    @property
    def fat_g(self) -> float:
        """Fat of this portion."""
        return self._part(self.fat_100g)

    def __repr__(self) -> str:
        return f"<FoodEntry {self.logged_on} {self.name} {self.grams} g>"
