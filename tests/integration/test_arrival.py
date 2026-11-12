"""«Tu llegada» on the home page: the date at the current pace, or from the plan."""

from __future__ import annotations

from datetime import timedelta

from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.models import User, WeightLog
from tests.integration.test_workout_flow import _with_routine


def _weigh(seeded: SQLAlchemy, kilos: list[float]) -> None:
    user = seeded.session.scalar(select(User))
    assert user is not None
    today = user.today()
    for days_ago, kg in enumerate(reversed(kilos)):
        seeded.session.add(
            WeightLog(user=user, logged_on=today - timedelta(days=days_ago + 1), weight_kg=kg)
        )
    seeded.session.commit()


def test_without_weigh_ins_the_date_comes_from_the_plan(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    html = client.get("/panel").get_data(as_text=True)
    assert "Tu llegada" in html
    assert "Si sigues el plan, llegas a 60 kg hacia el" in html


def test_a_steady_loss_gives_a_date_a_band_and_the_way_done(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    _weigh(
        seeded, [round(64.0 - 0.07 * day + (0.15 if day % 2 else -0.15), 2) for day in range(28)]
    )
    html = client.get("/panel").get_data(as_text=True)
    assert "A este ritmo llegas a 60 kg hacia el" in html
    assert "Lo más probable, entre el" in html
    assert 'role="progressbar"' in html
    assert "Previsto:" in html


def test_gaining_when_the_goal_is_to_lose_is_said_plainly(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    _weigh(seeded, [round(62.0 + 0.08 * day, 2) for day in range(21)])
    html = client.get("/panel").get_data(as_text=True)
    assert "Tu peso va en dirección contraria a tu objetivo de 60 kg" in html


def test_the_card_speaks_english_too(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    html = client.get("/panel?lang=en").get_data(as_text=True)
    assert "If you follow the plan, you reach 60 kg around" in html
