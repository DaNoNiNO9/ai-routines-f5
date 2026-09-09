"""Diary entries (weight, intake, activity), measurements and the fortnight view."""

from __future__ import annotations

from datetime import date, timedelta

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.engine.enums import BodyFatMethod, CardioKind
from app.models import ActivityLog, BodyMeasurement, IntakeLog, WeightLog
from app.services import tracking
from tests.factories import make_user

TODAY = date(2026, 9, 9)


def test_weight_is_one_row_per_day(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    tracking.upsert_weight(user, TODAY, 80.5, notes="mañana")
    database.session.commit()
    tracking.upsert_weight(user, TODAY, 80.1)
    database.session.commit()

    rows = database.session.scalars(select(WeightLog)).all()
    assert len(rows) == 1
    assert rows[0].weight_kg == 80.1
    assert rows[0].notes is None  # saving again replaces the whole entry


def test_intake_keeps_optional_macros_and_adherence(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    tracking.upsert_intake(
        user, TODAY, 2100, protein_g=160, carbs_g=210, fat_g=60, adherence_pct=90
    )
    database.session.commit()
    row = database.session.scalar(select(IntakeLog))
    assert row is not None
    assert (row.calories, row.protein_g, row.adherence_pct) == (2100, 160, 90)

    tracking.upsert_intake(user, TODAY, 1900)
    database.session.commit()
    assert database.session.scalar(select(IntakeLog)).protein_g is None
    assert len(database.session.scalars(select(IntakeLog)).all()) == 1


def test_activity_pairs_cardio_kind_and_minutes(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    tracking.upsert_activity(user, TODAY, 9000, cardio_kind=CardioKind.LISS, cardio_minutes=30)
    database.session.commit()
    row = database.session.scalar(select(ActivityLog))
    assert row is not None
    assert row.steps == 9000
    assert row.cardio_kind is CardioKind.LISS
    assert row.cardio_minutes == 30

    tracking.upsert_activity(user, TODAY, 7000, cardio_kind=CardioKind.HIIT, cardio_minutes=None)
    database.session.commit()
    row = database.session.scalar(select(ActivityLog))
    assert row.steps == 7000
    assert row.cardio_kind is None  # a kind without minutes is not a cardio session
    assert row.cardio_minutes is None


def test_measurement_drops_the_method_without_a_percentage(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    tracking.upsert_measurement(
        user, TODAY, waist_cm=80.0, body_fat_pct=18.0, body_fat_method=BodyFatMethod.CALIPERS
    )
    database.session.commit()
    row = database.session.scalar(select(BodyMeasurement))
    assert row is not None
    assert row.body_fat_method is BodyFatMethod.CALIPERS

    tracking.upsert_measurement(user, TODAY, waist_cm=79.0, body_fat_method=BodyFatMethod.CALIPERS)
    database.session.commit()
    row = database.session.scalar(select(BodyMeasurement))
    assert row.waist_cm == 79.0
    assert row.body_fat_pct is None
    assert row.body_fat_method is BodyFatMethod.NONE
    assert len(database.session.scalars(select(BodyMeasurement)).all()) == 1


def test_diary_rows_cover_every_day_newest_first(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    tracking.upsert_weight(user, TODAY, 80.0)
    tracking.upsert_intake(user, TODAY - timedelta(days=1), 2000, adherence_pct=80)
    tracking.upsert_activity(user, TODAY - timedelta(days=2), 8000)
    tracking.upsert_weight(user, TODAY - timedelta(days=30), 82.0)  # outside the window
    database.session.commit()

    rows = tracking.diary_rows(user, TODAY)
    assert len(rows) == tracking.DIARY_DAYS
    assert rows[0].day == TODAY
    assert rows[-1].day == TODAY - timedelta(days=tracking.DIARY_DAYS - 1)
    assert rows[0].weight_kg == 80.0
    assert rows[0].is_empty is False
    assert rows[1].calories == 2000
    assert rows[1].adherence_pct == 80
    assert rows[2].steps == 8000
    assert rows[3].is_empty is True
    assert all(row.weight_kg != 82.0 for row in rows)


def test_entry_for_prefills_one_day(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    tracking.upsert_weight(user, TODAY, 75.5)
    database.session.commit()
    assert tracking.entry_for(user, TODAY).weight_kg == 75.5
    assert tracking.entry_for(user, TODAY - timedelta(days=1)).is_empty is True


def test_recent_measurements_are_newest_first_and_capped(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    for offset in range(15):
        tracking.upsert_measurement(user, TODAY - timedelta(days=offset * 7), waist_cm=80 + offset)
    database.session.commit()
    rows = tracking.recent_measurements(user)
    assert len(rows) == tracking.MEASUREMENTS_LIMIT
    assert rows[0].measured_on == TODAY
    assert rows[0].measured_on > rows[-1].measured_on
