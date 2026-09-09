"""Exercise catalogue, equipment and the seed loaders / CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import Equipment, ExerciseAlternative, RoutineDay, RoutineExercise
from app.seeds.loaders import SeedError, load_json_list, seed_equipment
from tests.factories import make_equipment, make_exercise, make_profile, make_routine, make_user


def test_exercise_requires_a_set_of_equipment(database: SQLAlchemy) -> None:
    barbell = make_equipment(database.session, "barbell")
    bench = make_equipment(database.session, "flat_bench", category="accessories")
    exercise = make_exercise(database.session)
    exercise.equipment.extend([barbell, bench])
    database.session.commit()
    assert exercise.equipment_codes == {"barbell", "flat_bench"}


def test_alternatives_are_directed_and_ordered(database: SQLAlchemy) -> None:
    bench = make_exercise(database.session, "bench-press")
    dumbbell = make_exercise(database.session, "dumbbell-press", name_es="Press con mancuernas")
    machine = make_exercise(database.session, "machine-press", name_es="Press en máquina")
    bench.alternatives.append(
        ExerciseAlternative(alternative=machine, priority=2, reason="mismo patrón, guiado")
    )
    bench.alternatives.append(ExerciseAlternative(alternative=dumbbell, priority=1))
    database.session.commit()
    database.session.expire_all()
    assert [alt.alternative.slug for alt in bench.alternatives] == [
        "dumbbell-press",
        "machine-press",
    ]
    assert dumbbell.alternatives == []


def test_exercise_cannot_be_its_own_alternative(database: SQLAlchemy) -> None:
    bench = make_exercise(database.session)
    bench.alternatives.append(ExerciseAlternative(alternative=bench))
    with pytest.raises(IntegrityError):
        database.session.flush()


def test_exercise_in_use_cannot_be_deleted(database: SQLAlchemy) -> None:
    session = database.session
    user = make_user(session)
    profile = make_profile(session, user)
    exercise = make_exercise(session)
    routine = make_routine(session, user, profile)
    day = RoutineDay(day_index=1, name="Día 1")
    day.exercises.append(
        RoutineExercise(
            exercise=exercise, position=1, sets=3, rep_min=8, rep_max=12, rest_seconds=90
        )
    )
    routine.days.append(day)
    session.commit()

    session.delete(exercise)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_seed_equipment_is_idempotent_and_updates_changes(database: SQLAlchemy) -> None:
    session = database.session
    first = seed_equipment(session)
    session.commit()
    assert first.created >= 30
    assert first.updated == 0

    second = seed_equipment(session)
    assert (second.created, second.updated) == (0, 0)

    barbell = session.scalar(select(Equipment).where(Equipment.code == "barbell"))
    assert barbell is not None
    barbell.name_es = "cambiado a mano"
    session.commit()
    third = seed_equipment(session)
    assert (third.created, third.updated) == (0, 1)
    assert barbell.name_es == "Barra olímpica y discos"
    total = session.execute(select(func.count()).select_from(Equipment)).scalar_one()
    assert total == first.created


def test_seed_rejects_unknown_category(database: SQLAlchemy, tmp_path: Path) -> None:
    bad = tmp_path / "equipment.json"
    bad.write_text(
        json.dumps([{"code": "x", "name_es": "x", "name_en": "x", "category": "lasers"}]),
        encoding="utf-8",
    )
    with pytest.raises(SeedError, match="unknown category for 'x'"):
        seed_equipment(database.session, bad)


def test_seed_rejects_missing_keys_and_duplicates(database: SQLAlchemy, tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    missing.write_text(json.dumps([{"code": "x", "name_es": "x"}]), encoding="utf-8")
    with pytest.raises(SeedError, match="lacks"):
        seed_equipment(database.session, missing)

    duplicated = tmp_path / "dup.json"
    entry = {"code": "x", "name_es": "x", "name_en": "x", "category": "machines"}
    duplicated.write_text(json.dumps([entry, entry]), encoding="utf-8")
    with pytest.raises(SeedError, match="duplicated equipment code"):
        seed_equipment(database.session, duplicated)


def test_load_json_list_errors(tmp_path: Path) -> None:
    with pytest.raises(SeedError, match="not found"):
        load_json_list(tmp_path / "nope.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(SeedError, match="not valid JSON"):
        load_json_list(broken)
    not_list = tmp_path / "obj.json"
    not_list.write_text('{"a": 1}', encoding="utf-8")
    with pytest.raises(SeedError, match="list of objects"):
        load_json_list(not_list)


def test_seed_cli_reports_counts(app: Flask, database: SQLAlchemy) -> None:
    runner = app.test_cli_runner()
    result = runner.invoke(args=["seed", "equipment"])
    assert result.exit_code == 0, result.output
    assert "created, 0 updated" in result.output
    again = runner.invoke(args=["seed", "all"])
    assert again.exit_code == 0, again.output
    assert "0 created, 0 updated" in again.output


def test_seed_cli_fails_cleanly_on_bad_file(
    app: Flask, database: SQLAlchemy, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.cli as cli_module
    import app.seeds.loaders as loaders

    bad = tmp_path / "equipment.json"
    bad.write_text("[]garbage", encoding="utf-8")
    monkeypatch.setattr(loaders, "EQUIPMENT_FILE", bad)
    monkeypatch.setattr(
        cli_module, "seed_equipment", lambda session: loaders.seed_equipment(session, bad)
    )
    result = app.test_cli_runner().invoke(args=["seed", "equipment"])
    assert result.exit_code == 1
    assert "not valid JSON" in result.output
