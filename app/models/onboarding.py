"""Partial questionnaire answers, so a person can stop and continue on any device."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import JSONType, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class QuestionnaireDraft(TimestampMixin, db.Model):
    """Answers given so far (one draft per user) and the last step completed.

    ``data`` holds plain JSON keyed by field name (dates as ISO strings, enums
    as their values). It is validated again, step by step, when it is turned
    into a :class:`~app.models.profile.Profile`, so a stale or edited draft can
    never produce an invalid profile.
    """

    __tablename__ = "questionnaire_drafts"
    __table_args__ = (CheckConstraint("step >= 0", name="step_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    step: Mapped[int] = mapped_column(default=0, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)

    user: Mapped[User] = relationship(back_populates="questionnaire_draft")

    def __repr__(self) -> str:
        return f"<QuestionnaireDraft user={self.user_id} step={self.step}>"
