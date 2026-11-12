"""Erasures to apply again if a backup is ever restored.

A restored backup brings back the accounts deleted and the health data
withdrawn since it was taken. Each erasure leaves one row here with nothing but
the account number, what was erased and when: no email, no name, no data. After
a restore, ``flask privacy reapply-erasures`` deletes them again. Rows are kept
a little longer than the backups live (``ERASURE_LOG_DAYS``) and then purged.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.base import UTCDateTime, utcnow

ERASURE_ACCOUNT = "account"
ERASURE_HEALTH = "health"


class ErasureRecord(db.Model):
    """One erasure: the account number, what went, and when. Nothing else."""

    __tablename__ = "erasure_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Sin clave foránea: la cuenta ya no existe cuando se borra entera.
    user_id: Mapped[int] = mapped_column(nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    erased_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
