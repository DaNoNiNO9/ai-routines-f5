"""Plate and bar connected: how you arrive sets today's load; training sets today's food."""

from __future__ import annotations

import re
from datetime import timedelta

from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.models import IntakeLog, Plan, User, WorkoutSession
from tests.integration.test_onboarding import _post_step, _signup
from tests.integration.test_workout_flow import _log, _routine, _with_routine


def _open(client: FlaskClient, seeded: SQLAlchemy) -> WorkoutSession:
    client.post("/entreno/empezar/1")
    session = seeded.session.scalars(
        select(WorkoutSession).order_by(WorkoutSession.id.desc())
    ).first()
    assert session is not None
    return session


def _loads(html: str) -> float:
    """Sum of every suggested weight on the page (the bare bar cannot go lower)."""
    values = [float(value) for value in re.findall(r'name="weight_kg"[^>]*value="([0-9.]+)"', html)]
    assert values
    return sum(values)


def test_the_session_asks_how_you_slept_once(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    session = _open(client, seeded)
    page = client.get(f"/entreno/{session.id}").get_data(as_text=True)
    assert "¿cómo has dormido?" in page
    client.post(f"/entreno/{session.id}/estado", data={"sueno": "good"})
    assert "¿cómo has dormido?" not in client.get(f"/entreno/{session.id}").get_data(as_text=True)
    assert client.post(f"/entreno/{session.id}/estado", data={"sueno": "fatal"}).status_code == 400


def test_bad_sleep_makes_an_easy_day_with_lighter_loads(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    session = _open(client, seeded)
    client.post(f"/entreno/{session.id}/estado", data={"sueno": "skip"})
    normal = _loads(client.get(f"/entreno/{session.id}").get_data(as_text=True))
    client.post(f"/entreno/{session.id}/estado", data={"sueno": "bad"})
    easy_page = client.get(f"/entreno/{session.id}").get_data(as_text=True)
    assert "Hoy, sesión suave" in easy_page
    assert "Has dormido mal." in easy_page
    assert _loads(easy_page) < normal
    client.post(f"/entreno/{session.id}/estado", data={"sueno": "normal"})
    back = client.get(f"/entreno/{session.id}").get_data(as_text=True)
    assert "Hoy, sesión suave" not in back
    assert _loads(back) == normal


def test_eating_little_yesterday_counts(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    user = seeded.session.scalar(select(User))
    plan = seeded.session.scalar(select(Plan))
    assert user is not None
    assert plan is not None
    seeded.session.add(
        IntakeLog(
            user=user,
            logged_on=user.today() - timedelta(days=1),
            calories=round(plan.calorie_target * 0.6),
        )
    )
    seeded.session.commit()
    session = _open(client, seeded)
    client.post(f"/entreno/{session.id}/estado", data={"sueno": "ok"})
    page = client.get(f"/entreno/{session.id}").get_data(as_text=True)
    assert "Hoy, sesión" in page
    assert "Ayer comiste el 60 % de lo previsto." in page


def test_no_question_once_sets_are_logged(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    session = _open(client, seeded)
    _log(client, session.id, _routine(seeded).days[0].exercises[0])
    assert "¿cómo has dormido?" not in client.get(f"/entreno/{session.id}").get_data(as_text=True)


def test_training_turns_today_into_a_training_day(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    for number in range(1, 8):
        overrides = {"wants_carb_cycling": "y"} if number == 6 else {}
        _post_step(client, number, **overrides)
    client.post("/cuestionario/revisar")
    plan = seeded.session.scalar(select(Plan))
    assert plan is not None
    assert plan.details["carb_cycle"]
    before = client.get("/panel").get_data(as_text=True)
    assert "Hoy, de momento, día de descanso." in before
    client.post("/entreno/empezar/1")
    after = client.get("/panel").get_data(as_text=True)
    assert "Hoy entrenas: te tocan los números de día de entreno" in after
