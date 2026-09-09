"""Auditoría de los límites de seguridad (§3.5) desde fuera, intentando saltárselos.

El motor ya tiene sus tests; esto comprueba que la web no deja colar por el
formulario ni por una petición directa lo que el motor no aceptaría, y que el
aviso de herramienta orientativa está donde tiene que estar.
"""

from __future__ import annotations

from datetime import date

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.engine.safety import ABSOLUTE_CALORIE_FLOOR, MAX_WEEKLY_LOSS_FRACTION
from app.models import Plan, Routine, User
from tests.integration.test_auth import _register
from tests.integration.test_onboarding import STEP_ANSWERS, _fill_all, _post_step

TODAY = date(2026, 9, 9)


def _account(client: FlaskClient, email: str = "limites@example.com") -> None:
    assert _register(client, email=email).status_code == 302


def _fill_with(client: FlaskClient, **steps: dict[str, object]) -> None:
    """Rellena el cuestionario cambiando solo los pasos indicados."""
    for number in range(1, 8):
        overrides = steps.get(f"step{number}", {})
        response = _post_step(client, number, **overrides)  # type: ignore[arg-type]
        assert response.status_code == 302, response.get_data(as_text=True)


def test_the_questionnaire_refuses_a_minor(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _account(client)
    response = _post_step(client, 1, birth_date="2012-05-20")
    assert response.status_code == 200  # se queda en el paso, con el error
    page = response.get_data(as_text=True)
    assert "18" in page
    assert seeded.session.scalar(select(Plan)) is None


@pytest.mark.parametrize("flag", ["is_pregnant_or_breastfeeding", "has_eating_disorder_history"])
def test_a_declared_health_situation_stops_the_nutrition_plan(
    client: FlaskClient, seeded: SQLAlchemy, flag: str
) -> None:
    _account(client)
    _fill_with(client, step7={**STEP_ANSWERS[7], flag: "y"})
    assert client.post("/cuestionario/revisar").status_code == 302

    assert seeded.session.scalar(select(Plan)) is None
    page = client.get("/nutricion").get_data(as_text=True)
    assert "No hay plan de nutrición" in page
    assert "profesional sanitario" in page
    # El entrenamiento tampoco se genera cuando la seguridad bloquea el plan.
    assert seeded.session.scalar(select(Routine)) is None


def test_a_deficit_is_refused_with_a_low_bmi(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _account(client)
    # 45 kg y 175 cm: IMC 14,7.
    _fill_with(client, step1={**STEP_ANSWERS[1], "weight_kg": "45", "height_cm": "175"})
    assert client.post("/cuestionario/revisar").status_code == 302

    assert seeded.session.scalar(select(Plan)) is None
    page = client.get("/nutricion").get_data(as_text=True)
    assert "IMC" in page or "no es seguro" in page


def test_impossible_numbers_never_reach_the_engine(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _account(client)
    for field, value in (
        ("weight_kg", "10"),
        ("weight_kg", "400"),
        ("height_cm", "40"),
        ("height_cm", "260"),
        ("body_fat_pct", "90"),
        ("neck_cm", "5"),
    ):
        response = _post_step(client, 1, **{field: value})
        assert response.status_code == 200, f"{field}={value}"
    assert seeded.session.scalar(select(Plan)) is None


def test_smuggled_fields_are_ignored(client: FlaskClient, seeded: SQLAlchemy) -> None:
    """Mandar calorías en el formulario no cambia el plan: el motor las calcula."""
    _account(client)
    _fill_with(client)
    assert (
        client.post(
            "/cuestionario/revisar",
            data={"calorie_target": "800", "protein_g": "999", "aggressiveness": "extreme"},
        ).status_code
        == 302
    )
    plan = seeded.session.scalar(select(Plan))
    assert plan is not None
    assert plan.calorie_target != 800
    assert plan.protein_g != 999


def test_the_generated_plan_respects_the_hard_limits(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _account(client)
    _fill_all(client)
    assert client.post("/cuestionario/revisar").status_code == 302
    plan = seeded.session.scalar(select(Plan))
    user = seeded.session.scalar(select(User))
    assert plan is not None
    assert user is not None

    floor = max(plan.bmr_kcal, ABSOLUTE_CALORIE_FLOOR[plan.profile.sex])
    assert plan.calorie_target >= floor
    expected = plan.details["target"]["expected_weekly_change_kg"]
    assert -expected <= plan.profile.weight_kg * MAX_WEEKLY_LOSS_FRACTION + 0.02
    assert plan.protein_g > 0
    assert plan.carbs_g > 0
    assert plan.fat_g > 0


def test_the_disclaimer_is_on_every_screen_that_shows_a_plan(
    app: Flask, seeded: SQLAlchemy
) -> None:
    client = app.test_client()
    _account(client)
    _fill_all(client)
    assert client.post("/cuestionario/revisar").status_code == 302
    started = client.post("/entreno/empezar/1")
    assert started.status_code == 302
    session_path = started.headers["Location"]

    for path in (
        "/panel",
        "/nutricion",
        "/entrenamiento",
        "/entrenamiento/dia/1",
        "/diario",
        "/revision",
        "/cuenta",
        "/cuestionario/resultado",
        session_path,
    ):
        page = client.get(path).get_data(as_text=True)
        assert "herramienta orientativa" in page, path
        assert "profesional sanitario" in page, path
