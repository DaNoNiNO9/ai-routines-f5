"""Records celebrated on the spot, and the weekly streak with one day of slack."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.models import User, WorkoutSession
from app.services import workouts
from tests.integration.test_workout_flow import _log, _routine, _with_routine


def _finished_session(client: FlaskClient, seeded: SQLAlchemy, kg: str, reps: str) -> None:
    item = _routine(seeded).days[0].exercises[0]
    client.post("/entreno/empezar/1")
    session = seeded.session.scalars(
        select(WorkoutSession).order_by(WorkoutSession.id.desc())
    ).first()
    assert session is not None
    _log(client, session.id, item, set_index=1, weight_kg=kg, reps=reps)
    client.post(f"/entreno/{session.id}/terminar", data={"perceived_fatigue": "3"})
    session.started_at = session.started_at - timedelta(days=2)  # «antes» de la siguiente
    seeded.session.commit()


def _open_session(client: FlaskClient, seeded: SQLAlchemy) -> WorkoutSession:
    client.post("/entreno/empezar/1")
    session = seeded.session.scalars(
        select(WorkoutSession).order_by(WorkoutSession.id.desc())
    ).first()
    assert session is not None
    return session


def test_beating_your_best_is_celebrated_on_the_spot(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    _finished_session(client, seeded, "60", "8")
    session = _open_session(client, seeded)
    item = _routine(seeded).days[0].exercises[0]
    response = _log(client, session.id, item, set_index=1, weight_kg="65", reps="8")
    assert "marca=" in response.headers["Location"]
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "¡Marca nueva en" in page
    assert "data-vibrate" in page


def test_repeating_the_record_in_the_same_session_is_not_a_second_one(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    _finished_session(client, seeded, "60", "8")
    session = _open_session(client, seeded)
    item = _routine(seeded).days[0].exercises[0]
    _log(client, session.id, item, set_index=1, weight_kg="65", reps="8")
    again = _log(client, session.id, item, set_index=2, weight_kg="65", reps="8")
    assert "marca=" not in again.headers["Location"]


def test_a_lighter_set_or_a_first_time_is_not_a_record(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    first = _open_session(client, seeded)
    item = _routine(seeded).days[0].exercises[0]
    response = _log(client, first.id, item, set_index=1, weight_kg="60", reps="8")
    assert "marca=" not in response.headers["Location"]  # nada que batir todavía
    client.post(f"/entreno/{first.id}/terminar", data={"perceived_fatigue": "3"})
    first.started_at = first.started_at - timedelta(days=2)
    seeded.session.commit()
    session = _open_session(client, seeded)
    lighter = _log(client, session.id, item, set_index=1, weight_kg="55", reps="8")
    assert "marca=" not in lighter.headers["Location"]


def test_a_forged_record_link_shows_nothing(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    session = _open_session(client, seeded)
    page = client.get(f"/entreno/{session.id}?marca=999999").get_data(as_text=True)
    assert "¡Marca nueva en" not in page


def _sessions_on(seeded: SQLAlchemy, user: User, days: list) -> None:
    routine = _routine(seeded)
    for day in days:
        moment = datetime.combine(day, time(18, 0), tzinfo=UTC)
        seeded.session.add(
            WorkoutSession(
                user=user,
                routine_day=routine.days[0],
                started_at=moment,
                finished_at=moment + timedelta(hours=1),
                status=workouts.WorkoutStatus.COMPLETED,
            )
        )
    seeded.session.commit()


def test_the_streak_counts_weeks_with_one_day_of_slack(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    user = seeded.session.scalar(select(User))
    assert user is not None
    today = user.today()
    monday = today - timedelta(days=today.weekday())
    planned = len(_routine(seeded).days)
    target = max(1, planned - 1)
    # Las tres semanas anteriores cumplen (con un día de margen); esta va a medias.
    days = []
    for weeks_back in (1, 2, 3):
        start = monday - timedelta(weeks=weeks_back)
        days += [start + timedelta(days=offset) for offset in range(target)]
    _sessions_on(seeded, user, days)
    streak = workouts.weekly_streak(user, today, planned)
    assert streak.weeks == 3
    assert streak.this_week == 0
    assert not streak.met_this_week  # la semana en curso no rompe la racha
    html = client.get("/panel").get_data(as_text=True)
    assert "Constancia" in html
    assert "3 semanas" in html
    assert "Saltarte un día no rompe la racha" in html


def test_a_short_week_breaks_the_streak(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    user = seeded.session.scalar(select(User))
    assert user is not None
    today = user.today()
    monday = today - timedelta(days=today.weekday())
    planned = len(_routine(seeded).days)
    target = max(1, planned - 1)
    week_ago = monday - timedelta(weeks=1)
    three_ago = monday - timedelta(weeks=3)
    days = [week_ago + timedelta(days=offset) for offset in range(target)]
    days += [three_ago + timedelta(days=offset) for offset in range(target)]
    _sessions_on(seeded, user, days)  # la semana de hace dos no tiene nada
    assert workouts.weekly_streak(user, today, planned).weeks == 1


def test_one_week_is_said_in_singular(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    user = seeded.session.scalar(select(User))
    assert user is not None
    today = user.today()
    monday = today - timedelta(days=today.weekday())
    target = max(1, len(_routine(seeded).days) - 1)
    week_ago = monday - timedelta(weeks=1)
    _sessions_on(seeded, user, [week_ago + timedelta(days=offset) for offset in range(target)])
    html = client.get("/panel").get_data(as_text=True)
    assert "1 semana" in html
    assert "seguidas" not in html
