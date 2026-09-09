"""Idempotent loaders for reference data.

Each loader reads a JSON file from this folder, inserts what is missing and
updates what changed, keyed by a stable code. Running a loader twice is a
no-op. Validation errors are raised as :class:`SeedError` with the offending
entry, never swallowed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.enums import EquipmentCategory
from app.models import Equipment

SEEDS_DIR = Path(__file__).resolve().parent
EQUIPMENT_FILE = SEEDS_DIR / "equipment.json"

EQUIPMENT_REQUIRED_KEYS = ("code", "name_es", "name_en", "category")


class SeedError(ValueError):
    """A seed file is missing, malformed or contains an invalid entry."""


@dataclass
class SeedResult:
    """Counts reported by a loader."""

    created: int = 0
    updated: int = 0

    @property
    def total(self) -> int:
        """Rows touched (created plus updated)."""
        return self.created + self.updated


def load_json_list(path: Path) -> list[dict[str, Any]]:
    """Read a JSON file that must contain a list of objects.

    Raises:
        SeedError: If the file is missing, is not valid JSON or is not a list.
    """
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise SeedError(f"Seed file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SeedError(f"Seed file {path.name} is not valid JSON: {exc}") from exc
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise SeedError(f"Seed file {path.name} must contain a list of objects")
    return data


def _require_keys(entry: dict[str, Any], keys: tuple[str, ...], file_name: str) -> None:
    missing = [key for key in keys if key not in entry]
    if missing:
        raise SeedError(f"{file_name}: entry {entry.get('code', entry)!r} lacks {missing}")


def seed_equipment(session: Session, path: Path = EQUIPMENT_FILE) -> SeedResult:
    """Insert or update the equipment catalogue from ``equipment.json``.

    Args:
        session: An open SQLAlchemy session; the caller commits.
        path: Alternative JSON file (tests).

    Returns:
        How many rows were created and updated.

    Raises:
        SeedError: On malformed entries or unknown categories.
    """
    rows = load_json_list(path)
    existing = {item.code: item for item in session.scalars(select(Equipment)).all()}
    result = SeedResult()
    seen: set[str] = set()

    for row in rows:
        _require_keys(row, EQUIPMENT_REQUIRED_KEYS, path.name)
        code = str(row["code"]).strip()
        if code in seen:
            raise SeedError(f"{path.name}: duplicated equipment code {code!r}")
        seen.add(code)
        try:
            category = EquipmentCategory(row["category"])
        except ValueError as exc:
            raise SeedError(f"{path.name}: unknown category for {code!r}: {exc}") from exc

        values = {
            "name_es": str(row["name_es"]),
            "name_en": str(row["name_en"]),
            "category": category,
            "sort_order": int(row.get("sort_order", 100)),
        }
        item = existing.get(code)
        if item is None:
            session.add(Equipment(code=code, **values))
            result.created += 1
            continue
        changed = False
        for field, value in values.items():
            if getattr(item, field) != value:
                setattr(item, field, value)
                changed = True
        if changed:
            result.updated += 1

    session.flush()
    return result
