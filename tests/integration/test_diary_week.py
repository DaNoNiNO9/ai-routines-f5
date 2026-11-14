"""Diary: «Tu semana» and first steps instead of fourteen empty rows."""

from __future__ import annotations

from datetime import timedelta

from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.models import User, WeightLog
from app.services import tracking
from tests.integration.test_workout_flow import _with_routine


def _user(database: SQLAlchemy) -> User:
    user = database.session.scalar(select(User))
    assert user is not None
    return user


def test_a_new_account_sees_its_week_and_first_steps_not_empty_rows(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    html = client.get("/diario").get_data(as_text=True)
    assert "Tu semana" in html
    assert "Últimos 14 días" not in html
    assert "Tu historial" not in html  # nada que enseñar todavía
    assert "Tus primeros pasos" in html
    assert "Pésate por la mañana y apúntalo." in html
    # El cuestionario apunta el peso de hoy: ese paso ya está hecho.
    assert 'class="is-done"' in html


def test_days_before_signup_and_in_the_future_cannot_be_opened(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    user = _user(seeded)
    today = user.today()
    week = tracking.week_of(user, today, today)
    for d in week.days:
        assert d.before_signup == (d.day < today)
        assert d.future == (d.day > today)
    assert week.previous is None  # la semana pasada es anterior al alta
    assert week.following is None


def test_logged_days_get_their_mark(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    user = _user(seeded)
    today = user.today()
    client.post("/diario/actividad", data={"day": today.isoformat(), "steps": "9000"})
    week = tracking.week_of(user, today, today)
    mark = next(d for d in week.days if d.day == today)
    assert mark.weight
    assert mark.activity
    assert not mark.food


def test_history_appears_with_a_week_of_data_and_only_logged_days(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    user = _user(seeded)
    today = user.today()
    user.created_at = user.created_at - timedelta(days=30)
    for offset in range(0, 20, 2):  # un día sí y otro no: 10 días con datos
        day = today - timedelta(days=offset)
        if (
            seeded.session.scalar(
                select(WeightLog).where(WeightLog.user_id == user.id, WeightLog.logged_on == day)
            )
            is None
        ):
            seeded.session.add(WeightLog(user_id=user.id, logged_on=day, weight_kg=80))
    seeded.session.commit()
    rows = tracking.history_rows(user, today)
    assert len(rows) == 10
    assert all(not row.is_empty for row in rows)
    html = client.get("/diario").get_data(as_text=True)
    assert "Tu historial" in html
    assert "Tus primeros pasos" in html or tracking.first_steps(user, today) is None
    # Con un mes de cuenta ya se puede ir a la semana anterior.
    assert tracking.week_of(user, today, today).previous is not None


def test_first_steps_go_away_after_two_weeks(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    user = _user(seeded)
    user.created_at = user.created_at - timedelta(days=20)
    seeded.session.commit()
    assert tracking.first_steps(user, user.today()) is None
