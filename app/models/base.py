"""Shared model infrastructure: naming convention, column types, mixins.

Everything here is portable between SQLite (development) and PostgreSQL
(production): enums are stored as VARCHAR with a CHECK constraint, datetimes
are always timezone-aware UTC, JSON columns become JSONB on PostgreSQL.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from enum import Enum as PyEnum
from typing import Any

import sqlalchemy as sa
from sqlalchemy import JSON, DateTime, event
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

ENUM_LENGTH = 32


def utcnow() -> datetime:
    """Current time as an aware UTC datetime (the only kind stored)."""
    return datetime.now(tz=UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware datetimes normalised to UTC on the way in and out.

    SQLite drops the offset when storing datetimes, so values are converted to
    UTC before binding and get ``tzinfo=UTC`` attached when read back. Naive
    datetimes are rejected: every caller must be explicit about the zone.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, _dialect: Any) -> datetime | None:
        """Convert an aware datetime to UTC; refuse naive ones."""
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetime not allowed; use an aware UTC datetime")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, _dialect: Any) -> datetime | None:
        """Attach UTC to naive values coming from SQLite."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


JSONType = JSON().with_variant(postgresql.JSONB(), "postgresql")


def render_migration_item(type_: str, obj: Any, autogen_context: Any) -> str | bool:
    """Render the project column types inside generated migrations.

    ``UTCDateTime`` becomes plain ``sa.DateTime(timezone=True)`` (Alembic would
    otherwise emit ``app.models.base.UTCDateTime()``, coupling migration files to
    application code) and the JSON/JSONB variant is rendered with the explicit
    ``postgresql`` import Alembic forgets for ``astext_type``.
    """
    if type_ != "type":
        return False
    if isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    if isinstance(obj, JSON):
        autogen_context.imports.add("from sqlalchemy.dialects import postgresql")
        return "sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')"
    return False


def enum_column(enum_cls: type[PyEnum], *, name: str | None = None) -> sa.Enum:
    """Portable enum column: VARCHAR plus a CHECK constraint over the ``.value`` strings.

    Args:
        enum_cls: The :class:`enum.Enum` subclass (usually a ``StrEnum``).
        name: Constraint name; defaults to the lower-cased class name. Give an
            explicit one when the same enum appears twice in a table.
    """
    return sa.Enum(
        enum_cls,
        native_enum=False,
        length=ENUM_LENGTH,
        values_callable=lambda cls: [member.value for member in cls],
        name=name or enum_cls.__name__.lower(),
        create_constraint=True,
        validate_strings=True,
    )


class TimestampMixin:
    """``created_at`` / ``updated_at`` maintained by the ORM in UTC."""

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class SoftDeleteMixin:
    """Logical deletion: rows stay for audit and undo, filtered out by services."""

    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    @property
    def is_deleted(self) -> bool:
        """Whether the row has been soft-deleted."""
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Mark the row as deleted now."""
        self.deleted_at = utcnow()

    def restore(self) -> None:
        """Undo a soft delete."""
        self.deleted_at = None


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    """SQLite ignores foreign keys unless the pragma is set per connection."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
