"""The plan in a minute: one screen, the same rules, prudent defaults for the rest."""

from __future__ import annotations

from typing import Any

from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.models import Plan, Profile, QuestionnaireDraft, Routine
from tests.integration.test_onboarding import _signup

ANSWERS: dict[str, Any] = {
    "sex": "male",
    "birth_date": "1990-04-02",
    "height_cm": "178",
    "weight_kg": "84,5",
    "goal": "fat_loss",
    "target_weight_kg": "78",
    "training_experience": "6_to_24_months",
    "training_days_per_week": "4",
    "session_minutes": "60",
    "training_location": "full_gym",
}


def test_a_new_account_is_offered_the_quick_road(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    assert client.get("/cuestionario").headers["Location"].endswith("/cuestionario/rapido")
    page = client.get("/cuestionario/rapido").get_data(as_text=True)
    assert "Tu plan en un minuto" in page
    assert "Prefiero el cuestionario completo" in page


def test_one_screen_gives_plan_and_routine(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    response = client.post("/cuestionario/rapido", data=ANSWERS)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/cuestionario/resultado")
    assert seeded.session.scalar(select(Plan)) is not None
    assert seeded.session.scalar(select(Routine)) is not None
    profile = seeded.session.scalar(select(Profile))
    assert profile is not None
    assert profile.weight_kg == 84.5
    assert profile.target_weight_kg == 78
    # Lo que no se pregunta toma el valor prudente.
    assert profile.job_activity.value == "sedentary"
    assert profile.meals_per_day == 4
    assert profile.alcohol_drinks_per_week == 0
    draft = seeded.session.scalar(select(QuestionnaireDraft))
    assert draft is None or draft.step == 7


def test_the_material_is_the_preset_of_the_place(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    client.post("/cuestionario/rapido", data={**ANSWERS, "training_location": "home_bodyweight"})
    routine = seeded.session.scalar(select(Routine))
    assert routine is not None
    equipment = {
        code
        for day in routine.days
        for item in day.exercises
        for code in item.exercise.equipment_codes
    }
    assert equipment <= {"body_only"}


def test_the_same_rules_apply_minors_are_refused(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    page = client.post("/cuestionario/rapido", data={**ANSWERS, "birth_date": "2015-01-01"})
    assert page.status_code == 200
    assert "Alza es solo para mayores de 18 años." in page.get_data(as_text=True)
    assert seeded.session.scalar(select(Plan)) is None


def test_health_questions_still_block_the_nutrition_plan(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _signup(client)
    client.post("/cuestionario/rapido", data={**ANSWERS, "has_eating_disorder_history": "y"})
    assert seeded.session.scalar(select(Plan)) is None
    result = client.get("/cuestionario/resultado").get_data(as_text=True)
    assert "profesional sanitario" in result


def test_aches_go_on_to_the_injuries_step_already_filled(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _signup(client)
    response = client.post("/cuestionario/rapido", data={**ANSWERS, "has_injuries": "y"})
    assert response.headers["Location"].endswith("/cuestionario/paso/4")
    assert seeded.session.scalar(select(Plan)) is None
    step = client.get("/cuestionario/paso/4").get_data(as_text=True)
    assert "Tengo alguna molestia o lesión" in step
    # Los pasos siguientes ya están contestados: se puede seguir sin reescribir nada.
    assert client.get("/cuestionario/paso/5").status_code in (200, 302)


def test_missing_answers_are_shown_in_place(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    page = client.post("/cuestionario/rapido", data={"sex": "male"}).get_data(as_text=True)
    assert "field-error" in page
    assert seeded.session.scalar(select(Plan)) is None
