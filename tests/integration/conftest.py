"""Fixtures shared by the integration sweeps (coherence and brand)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.models import User, WeightLog, WorkoutSession
from tests.integration.test_workout_flow import _log, _routine, _with_routine


@pytest.fixture
def lived_in(client: FlaskClient, seeded: SQLAlchemy) -> FlaskClient:
    """An account with a plan, two weeks of weights, a finished and an open session."""
    _with_routine(client)
    user = seeded.session.scalar(select(User))
    assert user is not None
    for days_ago in range(1, 15):
        seeded.session.add(
            WeightLog(
                user=user,
                logged_on=user.today() - timedelta(days=days_ago),
                weight_kg=64.3 + days_ago * 0.05,
            )
        )
    seeded.session.commit()
    client.post("/diario/ingesta", data={"calories": "1850", "protein_g": "120.5"})
    client.post(
        "/diario/actividad", data={"steps": "8500", "cardio_kind": "liss", "cardio_minutes": "30"}
    )
    item = _routine(seeded).days[0].exercises[0]
    client.post("/entreno/empezar/1")
    finished = seeded.session.scalar(select(WorkoutSession))
    assert finished is not None
    _log(client, finished.id, item, set_index=1, weight_kg="62.5", reps="9", rir="2")
    client.post(f"/entreno/{finished.id}/terminar", data={"perceived_fatigue": "3"})
    client.post("/entreno/empezar/2")
    return client
