"""Auditoría de robustez (Fase 13): fallos a medias, doble clic y datos que faltan.

Nadie pulsa una vez. Nadie tiene siempre datos. Y cuando algo revienta a mitad
de una transacción, lo que no puede quedar es media cosa escrita.
"""

from __future__ import annotations

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.models import Plan, PlanAdjustment, Profile, SetLog, WeightLog, WorkoutSession
from app.services import plans
from tests.conftest import AppFactory
from tests.integration.test_auth import _register
from tests.integration.test_onboarding import _fill_all
from tests.integration.test_review_page import _log_daily_weights, _with_plan


def _ready(client: FlaskClient, email: str = "robusta@example.com") -> None:
    assert _register(client, email=email).status_code == 302
    _fill_all(client)
    assert client.post("/cuestionario/revisar").status_code == 302


def test_a_crash_while_generating_the_plan_leaves_nothing_written(
    make_app: AppFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El cuestionario escribe perfil, peso y plan: o entra todo o no entra nada."""
    app = make_app(PROPAGATE_EXCEPTIONS=False)
    with app.app_context():
        from app.extensions import db
        from app.seeds.loaders import seed_equipment, seed_exercises

        db.create_all()
        seed_equipment(db.session)
        seed_exercises(db.session)
        db.session.commit()

        client = app.test_client()
        assert _register(client, email="revienta@example.com").status_code == 302
        _fill_all(client)

        def boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("fallo a mitad de la generación")

        monkeypatch.setattr(plans, "generate_for_profile", boom)
        assert client.post("/cuestionario/revisar").status_code == 500

        db.session.rollback()
        assert db.session.scalar(select(Profile)) is None
        assert db.session.scalar(select(Plan)) is None
        assert db.session.scalar(select(WeightLog)) is None


def test_starting_the_same_session_twice_continues_the_first(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _ready(client)
    first = client.post("/entreno/empezar/1")
    second = client.post("/entreno/empezar/1")
    assert first.headers["Location"] == second.headers["Location"]
    assert len(seeded.session.scalars(select(WorkoutSession)).all()) == 1


def test_a_second_day_does_not_open_a_second_session(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    """Con una sesión en marcha, empezar otra devuelve a la misma y avisa."""
    _ready(client)
    client.post("/entreno/empezar/1")
    response = client.post("/entreno/empezar/2", follow_redirects=True)
    assert "Ya tienes una sesión en marcha" in response.get_data(as_text=True)
    assert len(seeded.session.scalars(select(WorkoutSession)).all()) == 1


def test_finishing_and_deleting_twice_are_not_errors(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _ready(client)
    client.post("/entreno/empezar/1")
    session_row = seeded.session.scalars(select(WorkoutSession)).first()
    assert session_row is not None
    item = session_row.routine_day.exercises[0]
    client.post(
        f"/entreno/{session_row.id}/serie",
        data={
            "routine_exercise_id": item.id,
            "set_index": 1,
            "weight_kg": "40",
            "reps": "8",
            "rir": "2",
        },
    )
    set_row = seeded.session.scalars(select(SetLog)).first()
    assert set_row is not None

    first = client.post(f"/entreno/{session_row.id}/serie/{set_row.id}/borrar")
    assert first.status_code == 302
    second = client.post(f"/entreno/{session_row.id}/serie/{set_row.id}/borrar")
    assert second.status_code in {302, 404}

    assert client.post(
        f"/entreno/{session_row.id}/terminar", data={"fatigue": "3"}
    ).status_code in {
        302,
        404,
    }
    again = client.post(f"/entreno/{session_row.id}/terminar", data={"fatigue": "3"})
    assert again.status_code in {302, 404}
    seeded.session.expire_all()
    assert len(seeded.session.scalars(select(WorkoutSession)).all()) == 1


def test_applying_the_same_review_twice_only_changes_the_plan_once(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    user, plan = _with_plan(client, seeded)
    _log_daily_weights(seeded, user, plan, -0.15)  # mucho más lento de lo previsto
    first = client.post("/revision/aplicar", follow_redirects=True)
    assert first.status_code == 200
    plans_after_first = len(seeded.session.scalars(select(Plan)).all())
    adjustments_after_first = len(seeded.session.scalars(select(PlanAdjustment)).all())

    second = client.post("/revision/aplicar", follow_redirects=True)
    assert second.status_code == 200
    assert "Todavía no toca" in second.get_data(as_text=True)
    seeded.session.expire_all()
    assert len(seeded.session.scalars(select(Plan)).all()) == plans_after_first
    assert len(seeded.session.scalars(select(PlanAdjustment)).all()) == adjustments_after_first


def test_pages_survive_a_user_with_no_data_at_all(app: Flask, seeded: SQLAlchemy) -> None:
    client = app.test_client()
    assert _register(client, email="vacia@example.com").status_code == 302
    for path in ("/panel", "/diario", "/entreno/historial", "/entreno/progreso", "/cuenta"):
        assert client.get(path).status_code == 200, path
    for path in ("/nutricion", "/entrenamiento", "/revision", "/entrenamiento/dia/1"):
        assert client.get(path).status_code in {200, 302}, path


def test_a_deleted_account_takes_its_sessions_with_it(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _ready(client)
    client.post("/entreno/empezar/1")
    assert seeded.session.scalar(select(WorkoutSession)) is not None

    response = client.post(
        "/cuenta/borrar",
        data={"current_password": "una contraseña larga", "confirmation": "BORRAR"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    seeded.session.expire_all()
    assert seeded.session.scalar(select(WorkoutSession)) is None
    assert seeded.session.scalar(select(Plan)) is None
    assert seeded.session.scalar(select(Profile)) is None
