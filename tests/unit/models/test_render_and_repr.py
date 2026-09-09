"""Migration type rendering and repr helpers (cheap but real behaviour)."""

from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import Integer, String

from app.models import (
    ActivityLog,
    BodyMeasurement,
    Equipment,
    Exercise,
    ExerciseAlternative,
    Injury,
    IntakeLog,
    Meal,
    Plan,
    PlanAdjustment,
    Profile,
    Routine,
    RoutineDay,
    RoutineExercise,
    SetLog,
    User,
    UTCDateTime,
    WeightLog,
    WorkoutSession,
)
from app.models.base import JSONType, render_migration_item


def test_render_migration_item_maps_project_types() -> None:
    context = SimpleNamespace(imports=set())
    assert render_migration_item("type", UTCDateTime(), context) == "sa.DateTime(timezone=True)"
    rendered = render_migration_item("type", JSONType, context)
    assert rendered == "sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')"
    assert "from sqlalchemy.dialects import postgresql" in context.imports
    assert render_migration_item("type", Integer(), context) is False
    assert render_migration_item("type", String(10), context) is False
    assert render_migration_item("column", UTCDateTime(), context) is False


def test_reprs_mention_identifying_fields() -> None:
    samples = [
        (User(id=1, email="a@b.com"), "a@b.com"),
        (Profile(user_id=1, version=2), "v2"),
        (Injury(area="knee", severity="mild"), "knee"),
        (WeightLog(logged_on="2026-09-09", weight_kg=70.0), "70.0"),
        (BodyMeasurement(measured_on="2026-09-09"), "2026-09-09"),
        (IntakeLog(logged_on="2026-09-09", calories=1800), "1800"),
        (ActivityLog(logged_on="2026-09-09"), "2026-09-09"),
        (Equipment(code="barbell"), "barbell"),
        (Exercise(slug="bench-press"), "bench-press"),
        (ExerciseAlternative(exercise_id=1, alternative_id=2), "1 -> 2"),
        (Plan(user_id=1, version=1, calorie_target=1800), "1800"),
        (Meal(position=1, name="Desayuno"), "Desayuno"),
        (PlanAdjustment(reason="initial", plan_id=3), "initial"),
        (Routine(user_id=1, version=1, split_type="full_body"), "full_body"),
        (RoutineDay(day_index=1, name="Día 1"), "Día 1"),
        (RoutineExercise(position=1, exercise_id=2, sets=3, rep_min=6, rep_max=10), "3x6-10"),
        (WorkoutSession(id=5, status="completed"), "completed"),
        (SetLog(exercise_id=2, set_index=1, reps=8, weight_kg=60.0), "8x60.0"),
    ]
    for row, expected in samples:
        assert expected in repr(row)
