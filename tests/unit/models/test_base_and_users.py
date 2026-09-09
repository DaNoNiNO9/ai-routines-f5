"""Column types, mixins, constraints and cascades on users and profiles."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import pytest
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, StatementError

from app.models import (
    Injury,
    Meal,
    Plan,
    PlanAdjustment,
    Profile,
    RoutineDay,
    RoutineExercise,
    SetLog,
    User,
    UTCDateTime,
    WeightLog,
    WorkoutSession,
)
from tests.factories import (
    aware,
    make_exercise,
    make_plan,
    make_profile,
    make_routine,
    make_user,
)


def test_utc_datetime_rejects_naive_values() -> None:
    with pytest.raises(ValueError, match="Naive datetime"):
        UTCDateTime().process_bind_param(datetime(2026, 1, 1, 12, 0), None)  # noqa: DTZ001


def test_utc_datetime_normalises_offsets() -> None:
    madrid = timezone(timedelta(hours=2))
    bound = UTCDateTime().process_bind_param(datetime(2026, 7, 1, 12, 0, tzinfo=madrid), None)
    assert bound == datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    naive = datetime(2026, 7, 1, 10, 0)  # noqa: DTZ001
    read = UTCDateTime().process_result_value(naive, None)
    assert read is not None
    assert read.tzinfo == UTC


def test_timestamps_are_aware_utc_and_updated(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    database.session.commit()
    assert user.created_at.tzinfo == UTC
    assert user.updated_at >= user.created_at
    before = user.updated_at
    user.display_name = "Ana María"
    database.session.commit()
    assert user.updated_at >= before


def test_soft_delete_mixin(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    assert user.is_deleted is False
    user.soft_delete()
    assert user.is_deleted is True
    assert user.deleted_at is not None
    user.restore()
    assert user.deleted_at is None


def test_email_is_normalised_and_unique(database: SQLAlchemy) -> None:
    user = make_user(database.session, email="  Ana@Example.COM ")
    assert user.email == "ana@example.com"
    database.session.commit()
    database.session.add(User(email="ANA@example.com", password_hash="x", display_name="Otra"))
    with pytest.raises(IntegrityError):
        database.session.flush()


def test_sqlite_enforces_foreign_keys(database: SQLAlchemy) -> None:
    database.session.add(WeightLog(user_id=999, logged_on=date(2026, 9, 9), weight_kg=70.0))
    with pytest.raises(IntegrityError):
        database.session.flush()


def test_enum_columns_reject_unknown_values(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    database.session.add(Profile(user=user, version=1, **{**_profile_values(), "sex": "other"}))
    with pytest.raises(StatementError):
        database.session.flush()


def test_enum_values_are_stored_as_plain_strings(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    make_profile(database.session, user)
    database.session.commit()
    raw = database.session.execute(select(Profile.__table__.c.sex)).scalar_one()
    assert raw == "female"


def test_profile_versioning_and_current(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    first = make_profile(database.session, user, version=1)
    first.supersede()
    second = make_profile(database.session, user, version=2, weight_kg=63.0)
    database.session.commit()
    assert user.current_profile is second
    assert first.is_current is False
    database.session.add(Profile(user=user, version=2, **_profile_values()))
    with pytest.raises(IntegrityError):
        database.session.flush()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("height_cm", 90.0),
        ("weight_kg", 10.0),
        ("stress_level", 9),
        ("training_days_per_week", 0),
        ("session_minutes", 5),
        ("meals_per_day", 0),
        ("body_fat_pct", 90.0),
        ("sleep_hours", 20.0),
    ],
)
def test_profile_check_constraints_reject_garbage(
    database: SQLAlchemy, field: str, value: Any
) -> None:
    user = make_user(database.session)
    database.session.add(Profile(user=user, version=1, **{**_profile_values(), field: value}))
    with pytest.raises(IntegrityError):
        database.session.flush()


def test_profile_age_on() -> None:
    profile = Profile(birth_date=date(1990, 6, 15))
    assert profile.age_on(date(2026, 6, 14)) == 35
    assert profile.age_on(date(2026, 6, 15)) == 36


def test_json_columns_round_trip(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    profile = make_profile(
        database.session, user, priority_muscles=["glutes", "back"], allergies=["nuts"]
    )
    database.session.commit()
    database.session.expire_all()
    reloaded = database.session.get(Profile, profile.id)
    assert reloaded is not None
    assert reloaded.priority_muscles == ["glutes", "back"]
    assert reloaded.allergies == ["nuts"]
    assert reloaded.food_aversions == []


def test_injury_unique_per_profile_and_area(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    profile = make_profile(database.session, user)
    profile.injuries.append(Injury(area="shoulder", severity="mild"))
    profile.injuries.append(Injury(area="shoulder", severity="severe"))
    with pytest.raises(IntegrityError):
        database.session.flush()


def test_deleting_a_user_removes_everything_they_own(database: SQLAlchemy) -> None:
    session = database.session
    user = make_user(session)
    profile = make_profile(session, user)
    profile.injuries.append(Injury(area="knee", severity="moderate"))
    session.add(WeightLog(user=user, logged_on=date(2026, 9, 9), weight_kg=64.0))
    plan = make_plan(session, user, profile)
    plan.meals.append(
        Meal(position=1, name="Desayuno", calories=500, protein_g=30, carbs_g=60, fat_g=15)
    )
    session.add(PlanAdjustment(user=user, plan=plan, reason="initial", explanation="Primer plan"))
    exercise = make_exercise(session)
    routine = make_routine(session, user, profile)
    day = RoutineDay(day_index=1, name="Día 1")
    day.exercises.append(
        RoutineExercise(
            exercise=exercise, position=1, sets=3, rep_min=6, rep_max=10, rest_seconds=120
        )
    )
    routine.days.append(day)
    workout = WorkoutSession(user=user, routine_day=day, started_at=aware(2026, 9, 9))
    workout.sets.append(
        SetLog(
            exercise=exercise, set_index=1, reps=8, weight_kg=60.0, completed_at=aware(2026, 9, 9)
        )
    )
    session.add(workout)
    session.commit()

    session.delete(user)
    session.commit()

    for model in (
        User,
        Profile,
        Injury,
        WeightLog,
        Plan,
        Meal,
        PlanAdjustment,
        RoutineDay,
        RoutineExercise,
        WorkoutSession,
        SetLog,
    ):
        count = session.execute(select(func.count()).select_from(model)).scalar_one()
        assert count == 0, model.__name__
    assert session.get(type(exercise), exercise.id) is not None


def _profile_values() -> dict[str, Any]:
    from tests.factories import PROFILE_DEFAULTS

    return dict(PROFILE_DEFAULTS)


def test_today_falls_back_to_utc_with_a_broken_time_zone(database: SQLAlchemy) -> None:
    """La zona la escribe la persona: si un día deja de existir, no se rompe el día."""
    user = make_user(database.session, timezone="Marte/Olimpo")
    database.session.commit()
    assert user.today() == datetime.now(UTC).date()


def test_the_current_profile_is_the_one_not_superseded(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    assert user.current_profile is None
    old = make_profile(database.session, user, version=1)
    old.superseded_at = datetime.now(UTC)
    current = make_profile(database.session, user, version=2)
    database.session.commit()
    assert user.current_profile is current
