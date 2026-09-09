"""Error paths of the diary, the live session and the review: nothing is written by halves."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.engine.safety import SafetyError
from app.engine.types import Note
from app.models import BodyMeasurement, Plan, SetLog, User, WorkoutSession
from tests.integration.test_review_page import _log_daily_weights, _with_plan
from tests.integration.test_workout_flow import _log, _routine, _with_routine


def test_a_review_that_would_break_the_limits_changes_nothing(
    client: FlaskClient, seeded: SQLAlchemy, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, plan = _with_plan(client, seeded)
    _log_daily_weights(seeded, user, plan, -0.15)

    def unsafe(*_args: Any, **_kwargs: Any) -> None:
        raise SafetyError((Note("safety.below_floor", level="error"),))

    from app.blueprints.review import routes

    monkeypatch.setattr(routes.adjustments, "apply", unsafe)
    response = client.post("/revision/aplicar", follow_redirects=True)
    assert "No se pudo aplicar la revisión" in response.get_data(as_text=True)
    seeded.session.expire_all()
    assert len(seeded.session.scalars(select(Plan)).all()) == 1


def test_measurements_reject_a_day_in_the_future(client: FlaskClient, seeded: SQLAlchemy) -> None:
    from tests.integration.test_onboarding import _signup

    _signup(client)
    user = seeded.session.scalar(select(User))
    assert user is not None
    response = client.post(
        "/diario/perimetros",
        data={"day": (user.today() + timedelta(days=2)).isoformat(), "waist_cm": "80"},
    )
    assert "todavía no ha llegado" in response.get_data(as_text=True)
    assert seeded.session.scalar(select(BodyMeasurement)) is None


def test_a_closed_session_refuses_more_sets(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    client.post("/entreno/empezar/1")
    session = seeded.session.scalar(select(WorkoutSession))
    item = _routine(seeded).days[0].exercises[0]
    _log(client, session.id, item)
    client.post(f"/entreno/{session.id}/terminar", data={"perceived_fatigue": "3"})

    blocked = _log(client, session.id, item, set_index=2)
    assert blocked.status_code == 302
    assert "ya está cerrada" in client.get(
        f"/entreno/{session.id}/resumen", follow_redirects=True
    ).get_data(as_text=True)
    seeded.session.expire_all()
    assert len(seeded.session.scalars(select(SetLog)).all()) == 1


def test_closing_with_an_impossible_fatigue_is_refused(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    client.post("/entreno/empezar/1")
    session = seeded.session.scalar(select(WorkoutSession))
    item = _routine(seeded).days[0].exercises[0]
    _log(client, session.id, item)

    response = client.post(
        f"/entreno/{session.id}/terminar", data={"perceived_fatigue": "9"}, follow_redirects=True
    )
    assert "Revisa el formulario de cierre" in response.get_data(as_text=True)
    seeded.session.expire_all()
    assert seeded.session.scalar(select(WorkoutSession)).finished_at is None


def test_a_malformed_substitution_is_refused(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    client.post("/entreno/empezar/1")
    session = seeded.session.scalar(select(WorkoutSession))
    response = client.post(
        f"/entreno/{session.id}/sustituir", data={"exercise_id": "1"}, follow_redirects=True
    )
    assert "Petición no válida" in response.get_data(as_text=True)
    seeded.session.expire_all()
    assert seeded.session.scalar(select(WorkoutSession)).substitutions == {}
