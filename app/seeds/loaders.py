"""Idempotent loaders for reference data.

Each loader reads a JSON file from this folder, inserts what is missing and
updates what changed, keyed by a stable code (``equipment.code``,
``exercises.slug``). Running a loader twice is a no-op. Validation errors are
raised as :class:`SeedError` with the offending entry, never swallowed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.engine.enums import (
    EquipmentCategory,
    Force,
    InjuryArea,
    Mechanic,
    MovementPattern,
    MuscleGroup,
    Severity,
    TechnicalLevel,
)
from app.models import Equipment, Exercise, ExerciseAlternative

SEEDS_DIR = Path(__file__).resolve().parent
EQUIPMENT_FILE = SEEDS_DIR / "equipment.json"
EXERCISES_FILE = SEEDS_DIR / "exercises.json"

EQUIPMENT_REQUIRED_KEYS = ("code", "name_es", "name_en", "category")
EXERCISE_REQUIRED_KEYS = (
    "slug",
    "name_es",
    "name_en",
    "primary_muscle",
    "movement_pattern",
    "mechanic",
    "force",
    "technical_level",
    "equipment",
)


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
        label = entry.get("code") or entry.get("slug") or entry
        raise SeedError(f"{file_name}: entry {label!r} lacks {missing}")


def _apply_values(row: Any, values: dict[str, Any]) -> bool:
    """Set attributes that differ; return whether anything changed."""
    changed = False
    for field, value in values.items():
        if getattr(row, field) != value:
            setattr(row, field, value)
            changed = True
    return changed


# --------------------------------------------------------------------------- equipment


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
        elif _apply_values(item, values):
            result.updated += 1

    session.flush()
    return result


# --------------------------------------------------------------------------- exercises


def _enum_value(enum_cls: Any, raw: Any, slug: str, field: str, file_name: str) -> Any:
    try:
        return enum_cls(raw)
    except ValueError as exc:
        raise SeedError(f"{file_name}: {slug!r} has invalid {field} {raw!r}") from exc


def _exercise_values(row: dict[str, Any], file_name: str) -> dict[str, Any]:
    """Validate one exercise entry and return the column values."""
    slug = str(row["slug"])
    secondary = [
        _enum_value(MuscleGroup, muscle, slug, "secondary_muscles", file_name).value
        for muscle in row.get("secondary_muscles", [])
    ]
    contraindications = []
    for item in row.get("contraindications", []):
        if not isinstance(item, dict) or "area" not in item or "min_severity" not in item:
            raise SeedError(f"{file_name}: {slug!r} has a malformed contraindication {item!r}")
        contraindications.append(
            {
                "area": _enum_value(
                    InjuryArea, item["area"], slug, "contraindication", file_name
                ).value,
                "min_severity": _enum_value(
                    Severity, item["min_severity"], slug, "min_severity", file_name
                ).value,
            }
        )
    return {
        "name_es": str(row["name_es"]),
        "name_en": str(row["name_en"]),
        "primary_muscle": _enum_value(
            MuscleGroup, row["primary_muscle"], slug, "primary_muscle", file_name
        ),
        "secondary_muscles": secondary,
        "movement_pattern": _enum_value(
            MovementPattern, row["movement_pattern"], slug, "movement_pattern", file_name
        ),
        "mechanic": _enum_value(Mechanic, row["mechanic"], slug, "mechanic", file_name),
        "force": _enum_value(Force, row["force"], slug, "force", file_name),
        "technical_level": _enum_value(
            TechnicalLevel, row["technical_level"], slug, "technical_level", file_name
        ),
        "is_unilateral": bool(row.get("is_unilateral", False)),
        "is_bodyweight": bool(row.get("is_bodyweight", False)),
        "contraindications": contraindications,
        "instructions_es": row.get("instructions_es"),
        "instructions_en": row.get("instructions_en"),
        "video_url": row.get("video_url"),
        "image_path": row.get("image_path"),
        "source_id": row.get("source_id"),
        "is_active": bool(row.get("is_active", True)),
    }


def seed_exercises(session: Session, path: Path = EXERCISES_FILE) -> SeedResult:
    """Insert or update the exercise catalogue from ``exercises.json``.

    Equipment must be seeded first: every exercise references equipment codes.
    Alternatives are resolved in a second pass, once every slug exists.

    Raises:
        SeedError: On malformed entries, unknown enums, unknown equipment codes
            or alternatives pointing to missing slugs.
    """
    rows = load_json_list(path)
    equipment = {item.code: item for item in session.scalars(select(Equipment)).all()}
    if not equipment:
        raise SeedError("No equipment in the database; run `flask seed equipment` first")

    query = select(Exercise).options(
        selectinload(Exercise.equipment),
        selectinload(Exercise.alternatives).selectinload(ExerciseAlternative.alternative),
    )
    existing = {item.slug: item for item in session.scalars(query).all()}
    created: set[str] = set()
    changed: set[str] = set()
    alternatives_spec: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        _require_keys(row, EXERCISE_REQUIRED_KEYS, path.name)
        slug = str(row["slug"]).strip()
        if slug in alternatives_spec:
            raise SeedError(f"{path.name}: duplicated exercise slug {slug!r}")
        values = _exercise_values(row, path.name)
        codes = [str(code) for code in row["equipment"]]
        unknown = [code for code in codes if code not in equipment]
        if unknown:
            raise SeedError(f"{path.name}: {slug!r} uses unknown equipment {unknown}")

        exercise = existing.get(slug)
        if exercise is None:
            exercise = Exercise(slug=slug, **values)
            exercise.equipment = [equipment[code] for code in codes]
            session.add(exercise)
            existing[slug] = exercise
            created.add(slug)
        else:
            if _apply_values(exercise, values):
                changed.add(slug)
            if {item.code for item in exercise.equipment} != set(codes):
                exercise.equipment = [equipment[code] for code in codes]
                changed.add(slug)
        alternatives_spec[slug] = list(row.get("alternatives", []))

    session.flush()

    for slug, alternatives in alternatives_spec.items():
        exercise = existing[slug]
        desired: list[tuple[str, int, str | None]] = []
        for item in alternatives:
            target_slug = str(item.get("slug", ""))
            target = existing.get(target_slug)
            if target is None:
                raise SeedError(f"{path.name}: {slug!r} lists unknown alternative {target_slug!r}")
            if target is exercise:
                raise SeedError(f"{path.name}: {slug!r} lists itself as an alternative")
            desired.append((target_slug, int(item.get("priority", 1)), item.get("reason")))
        current = [
            (alt.alternative.slug, alt.priority, alt.reason) for alt in exercise.alternatives
        ]
        if sorted(current) != sorted(desired):
            exercise.alternatives = [
                ExerciseAlternative(alternative=existing[target], priority=priority, reason=reason)
                for target, priority, reason in desired
            ]
            if slug not in created:
                changed.add(slug)

    session.flush()
    return SeedResult(created=len(created), updated=len(changed - created))
