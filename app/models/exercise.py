"""Exercise catalogue: equipment, exercises and equivalent alternatives."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, Column, ForeignKey, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.engine.enums import (
    EquipmentCategory,
    Force,
    Mechanic,
    MovementPattern,
    MuscleGroup,
    TechnicalLevel,
)
from app.extensions import db
from app.models.base import JSONType, TimestampMixin, UTCDateTime, enum_column, utcnow

SLUG_MAX_LENGTH = 80
NAME_MAX_LENGTH = 120

exercise_equipment = Table(
    "exercise_equipment",
    db.metadata,
    Column("exercise_id", ForeignKey("exercises.id", ondelete="CASCADE"), primary_key=True),
    Column("equipment_id", ForeignKey("equipment.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", UTCDateTime, default=utcnow, nullable=False),
)


class Equipment(TimestampMixin, db.Model):
    """A piece of equipment a user may own and an exercise may require."""

    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name_es: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    name_en: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    category: Mapped[EquipmentCategory] = mapped_column(
        enum_column(EquipmentCategory), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(default=100, nullable=False)

    def __repr__(self) -> str:
        return f"<Equipment {self.code}>"


class Exercise(TimestampMixin, db.Model):
    """Catalogue entry with everything the routine generator needs to pick it.

    ``contraindications`` is a JSON list of ``{"area": InjuryArea, "min_severity":
    Severity}`` objects: the exercise is excluded when the user reports that
    area at that severity or worse. ``secondary_muscles`` is a JSON list of
    ``MuscleGroup`` values. Both are validated by the seed loader.
    """

    __tablename__ = "exercises"
    __table_args__ = (CheckConstraint("length(slug) >= 3", name="slug_min_length"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(SLUG_MAX_LENGTH), unique=True, nullable=False)
    name_es: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    name_en: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    primary_muscle: Mapped[MuscleGroup] = mapped_column(
        enum_column(MuscleGroup, name="primary_muscle"), nullable=False, index=True
    )
    secondary_muscles: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    movement_pattern: Mapped[MovementPattern] = mapped_column(
        enum_column(MovementPattern), nullable=False, index=True
    )
    mechanic: Mapped[Mechanic] = mapped_column(enum_column(Mechanic), nullable=False)
    force: Mapped[Force] = mapped_column(enum_column(Force), nullable=False)
    technical_level: Mapped[TechnicalLevel] = mapped_column(
        enum_column(TechnicalLevel), nullable=False
    )
    is_unilateral: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_bodyweight: Mapped[bool] = mapped_column(default=False, nullable=False)
    contraindications: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONType, default=list, nullable=False
    )
    instructions_es: Mapped[str | None] = mapped_column(Text)
    instructions_en: Mapped[str | None] = mapped_column(Text)
    video_url: Mapped[str | None] = mapped_column(String(300))
    image_path: Mapped[str | None] = mapped_column(String(200))
    source_id: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    equipment: Mapped[list[Equipment]] = relationship(secondary=exercise_equipment)
    alternatives: Mapped[list[ExerciseAlternative]] = relationship(
        back_populates="exercise",
        cascade="all, delete-orphan",
        foreign_keys="ExerciseAlternative.exercise_id",
        order_by="ExerciseAlternative.priority",
    )

    @property
    def equipment_codes(self) -> set[str]:
        """Codes of the equipment this exercise requires (all of them)."""
        return {item.code for item in self.equipment}

    def __repr__(self) -> str:
        return f"<Exercise {self.slug}>"


class ExerciseAlternative(db.Model):
    """Directed link: ``alternative`` can replace ``exercise`` (same pattern, other constraints)."""

    __tablename__ = "exercise_alternatives"
    __table_args__ = (
        CheckConstraint("exercise_id <> alternative_id", name="not_self"),
        CheckConstraint("priority >= 1", name="priority_positive"),
    )

    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id", ondelete="CASCADE"), primary_key=True
    )
    alternative_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id", ondelete="CASCADE"), primary_key=True
    )
    priority: Mapped[int] = mapped_column(default=1, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    exercise: Mapped[Exercise] = relationship(
        back_populates="alternatives", foreign_keys=[exercise_id]
    )
    alternative: Mapped[Exercise] = relationship(foreign_keys=[alternative_id])

    def __repr__(self) -> str:
        return f"<ExerciseAlternative {self.exercise_id} -> {self.alternative_id}>"
