"""The Alembic migrations must build exactly the schema the models describe."""

from __future__ import annotations

from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from config import BASE_DIR

MIGRATIONS_DIR = str(BASE_DIR / "migrations")

EXPECTED_TABLES = {
    "activity_logs",
    "billing_events",
    "erasure_log",
    "body_measurements",
    "equipment",
    "exercise_alternatives",
    "exercise_equipment",
    "exercises",
    "food_entries",
    "injuries",
    "intake_logs",
    "meals",
    "plan_adjustments",
    "plans",
    "profiles",
    "questionnaire_drafts",
    "routine_days",
    "routine_exercises",
    "routines",
    "set_logs",
    "subscriptions",
    "user_equipment",
    "users",
    "weight_logs",
    "workout_sessions",
}


def test_upgrade_matches_models_and_downgrade_is_clean(tmp_path: Path) -> None:
    db_file = tmp_path / "migrations.db"
    app = create_app(
        "testing",
        {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_file.as_posix()}", "LOG_TO_FILE": False},
    )
    with app.app_context():
        upgrade(directory=MIGRATIONS_DIR)

        tables = set(inspect(db.engine).get_table_names())
        assert tables == EXPECTED_TABLES | {"alembic_version"}

        with db.engine.connect() as connection:
            context = MigrationContext.configure(
                connection, opts={"compare_type": True, "render_as_batch": True}
            )
            diffs = compare_metadata(context, db.metadata)
        assert diffs == [], diffs

        downgrade(directory=MIGRATIONS_DIR, revision="base")
        assert set(inspect(db.engine).get_table_names()) == {"alembic_version"}

        upgrade(directory=MIGRATIONS_DIR)
        assert set(inspect(db.engine).get_table_names()) == EXPECTED_TABLES | {"alembic_version"}


def test_migration_files_do_not_reference_application_types() -> None:
    versions = list((BASE_DIR / "migrations" / "versions").glob("*.py"))
    assert versions, "no migration files found"
    for path in versions:
        source = path.read_text(encoding="utf-8")
        assert "app.models" not in source, path.name
        assert "UTCDateTime" not in source, path.name
