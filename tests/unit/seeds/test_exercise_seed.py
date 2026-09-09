"""Loading the exercise catalogue into the database, and the CLI around it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, select

from app.models import Exercise, ExerciseAlternative
from app.seeds.loaders import (
    EXERCISES_FILE,
    SeedError,
    load_json_list,
    seed_equipment,
    seed_exercises,
)

EXERCISES = load_json_list(EXERCISES_FILE)
BENCH = "barbell-bench-press-medium-grip"


def _minimal_entry(**overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "slug": "test-move",
        "name_es": "Movimiento",
        "name_en": "Move",
        "primary_muscle": "chest",
        "secondary_muscles": ["triceps"],
        "movement_pattern": "horizontal_push",
        "mechanic": "compound",
        "force": "push",
        "technical_level": "beginner",
        "equipment": ["dumbbells"],
        "contraindications": [{"area": "shoulder", "min_severity": "moderate"}],
        "alternatives": [],
    }
    entry.update(overrides)
    return entry


def _write(tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
    path = tmp_path / "exercises.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def test_seed_exercises_requires_equipment(database: SQLAlchemy) -> None:
    with pytest.raises(SeedError, match="flask seed equipment"):
        seed_exercises(database.session)


def test_seed_exercises_loads_catalogue_and_is_idempotent(database: SQLAlchemy) -> None:
    session = database.session
    seed_equipment(session)
    first = seed_exercises(session)
    session.commit()
    assert first.created == len(EXERCISES)
    assert first.updated == 0

    second = seed_exercises(session)
    assert (second.created, second.updated) == (0, 0)

    bench = session.scalar(select(Exercise).where(Exercise.slug == BENCH))
    assert bench is not None
    assert bench.equipment_codes == {"barbell", "flat_bench"}
    assert bench.primary_muscle == "chest"
    assert bench.contraindications[0]["area"] == "shoulder"
    expected = next(e for e in EXERCISES if e["slug"] == BENCH)["alternatives"]
    assert [alt.alternative.slug for alt in bench.alternatives] == [a["slug"] for a in expected]

    total_alternatives = session.execute(
        select(func.count()).select_from(ExerciseAlternative)
    ).scalar_one()
    assert total_alternatives == sum(len(e["alternatives"]) for e in EXERCISES)


def test_seed_exercises_updates_changed_rows(database: SQLAlchemy) -> None:
    session = database.session
    seed_equipment(session)
    seed_exercises(session)
    session.commit()

    bench = session.scalar(select(Exercise).where(Exercise.slug == BENCH))
    assert bench is not None
    bench.name_es = "cambiado"
    bench.equipment = [item for item in bench.equipment if item.code != "flat_bench"]
    squat = session.scalar(select(Exercise).where(Exercise.slug == "barbell-squat"))
    assert squat is not None
    squat.alternatives.pop()
    session.commit()

    result = seed_exercises(session)
    session.commit()
    assert (result.created, result.updated) == (0, 2)
    session.expire_all()
    assert bench.name_es != "cambiado"
    assert bench.equipment_codes == {"barbell", "flat_bench"}
    expected = next(e for e in EXERCISES if e["slug"] == "barbell-squat")["alternatives"]
    assert len(squat.alternatives) == len(expected)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"equipment": ["laser_rack"]}, "unknown equipment"),
        ({"primary_muscle": "wings"}, "invalid primary_muscle"),
        ({"movement_pattern": "sideways"}, "invalid movement_pattern"),
        ({"contraindications": [{"area": "shoulder"}]}, "malformed contraindication"),
        (
            {"contraindications": [{"area": "tail", "min_severity": "mild"}]},
            "invalid contraindication",
        ),
        ({"alternatives": [{"slug": "nope", "priority": 1}]}, "unknown alternative"),
        ({"alternatives": [{"slug": "test-move", "priority": 1}]}, "lists itself"),
    ],
)
def test_seed_exercises_rejects_bad_entries(
    database: SQLAlchemy, tmp_path: Path, overrides: dict[str, Any], message: str
) -> None:
    seed_equipment(database.session)
    path = _write(tmp_path, [_minimal_entry(**overrides)])
    with pytest.raises(SeedError, match=message):
        seed_exercises(database.session, path)


def test_seed_exercises_rejects_duplicated_slugs(database: SQLAlchemy, tmp_path: Path) -> None:
    seed_equipment(database.session)
    path = _write(tmp_path, [_minimal_entry(), _minimal_entry()])
    with pytest.raises(SeedError, match="duplicated exercise slug"):
        seed_exercises(database.session, path)


def test_seed_exercises_minimal_entry_round_trip(database: SQLAlchemy, tmp_path: Path) -> None:
    session = database.session
    seed_equipment(session)
    other = _minimal_entry(slug="other-move", alternatives=[{"slug": "test-move", "priority": 1}])
    path = _write(tmp_path, [_minimal_entry(), other])
    result = seed_exercises(session, path)
    session.commit()
    assert (result.created, result.updated) == (2, 0)
    loaded = session.scalar(select(Exercise).where(Exercise.slug == "other-move"))
    assert loaded is not None
    assert loaded.alternatives[0].alternative.slug == "test-move"
    assert loaded.is_active is True
    assert loaded.image_path is None


def test_seed_cli_all_runs_both_loaders(app: Flask, database: SQLAlchemy) -> None:
    runner = app.test_cli_runner()
    result = runner.invoke(args=["seed", "all"])
    assert result.exit_code == 0, result.output
    assert "equipment:" in result.output
    assert f"exercises: {len(EXERCISES)} created, 0 updated" in result.output
    again = runner.invoke(args=["seed", "exercises"])
    assert again.exit_code == 0, again.output
    assert "exercises: 0 created, 0 updated" in again.output


def test_seed_cli_exercises_without_equipment_fails_cleanly(
    app: Flask, database: SQLAlchemy
) -> None:
    result = app.test_cli_runner().invoke(args=["seed", "exercises"])
    assert result.exit_code == 1
    assert "flask seed equipment" in result.output
