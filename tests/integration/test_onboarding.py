"""The questionnaire through HTTP: steps, drafts, review, generation and the result page."""

from __future__ import annotations

import re
from typing import Any

from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.engine.equipment_presets import preset_for
from app.models import Plan, Profile, QuestionnaireDraft, Routine, WeightLog
from app.services import onboarding
from tests.integration.test_auth import _register

STEP_ANSWERS: dict[int, dict[str, Any]] = {
    1: {
        "sex": "female",
        "birth_date": "1992-05-20",
        "height_cm": "168",
        "weight_kg": "64",
        "neck_cm": "33",
        "waist_cm": "74",
        "hip_cm": "96",
        "body_fat_pct": "",
        "body_fat_method": "none",
    },
    2: {
        "job_activity": "sedentary",
        "daily_steps": "6000",
        "sleep_hours": "7",
        "stress_level": "3",
        "other_activity_type": "",
        "other_activity_sessions_per_week": "0",
        "other_activity_minutes": "0",
        "other_activity_intensity": "",
    },
    3: {
        "training_experience": "6_to_24_months",
        "training_days_per_week": "4",
        "session_minutes": "60",
        "training_location": "basic_gym",
        "training_time": "evening",
    },
    4: {
        "equipment": sorted(preset_for("basic_gym")),
        "priority_muscles": ["glutes", "shoulders"],
        "injury_knee": "mild",
    },
    5: {
        "goal": "fat_loss",
        "aggressiveness": "moderate",
        "target_weight_kg": "60",
        "target_date": "",
    },
    6: {
        "meals_per_day": "4",
        "diet_pattern": "omnivore",
        "food_aversions": "hígado, coles",
        "allergies": "",
        "budget_level": "medium",
        "cooking_time": "medium",
        "alcohol_drinks_per_week": "1",
        "caffeine_cups_per_day": "2",
    },
    7: {"notes": "Nada más."},
}


def _signup(client: FlaskClient) -> None:
    assert _register(client).status_code == 302


def _post_step(client: FlaskClient, number: int, **overrides: Any) -> Any:
    data = {**STEP_ANSWERS[number], **overrides}
    return client.post(f"/cuestionario/paso/{number}", data=data)


def _fill_all(client: FlaskClient) -> None:
    for number in range(1, 8):
        response = _post_step(client, number)
        assert response.status_code == 302, response.get_data(as_text=True)


def test_anonymous_users_are_sent_to_login(client: FlaskClient, database: SQLAlchemy) -> None:
    response = client.get("/cuestionario")
    assert response.status_code == 302
    assert "/entrar" in response.headers["Location"]


def test_dashboard_offers_the_questionnaire_until_there_is_a_profile(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _signup(client)
    page = client.get("/panel").get_data(as_text=True)
    assert "Empezar el cuestionario" in page
    _post_step(client, 1)
    page = client.get("/panel").get_data(as_text=True)
    assert "Continuar el cuestionario" in page


def test_index_starts_at_the_first_pending_step(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    start = client.get("/cuestionario")
    assert start.headers["Location"].endswith("/cuestionario/paso/1")
    assert client.get("/cuestionario/paso/1").status_code == 200
    _post_step(client, 1)
    assert client.get("/cuestionario").headers["Location"].endswith("/cuestionario/paso/2")
    ahead = client.get("/cuestionario/paso/5", follow_redirects=True)
    assert "Completa primero" in ahead.get_data(as_text=True)
    assert client.get("/cuestionario/paso/9").status_code == 404


def test_step_validation_errors_are_shown_in_place(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    minor = _post_step(client, 1, birth_date="2015-01-01")
    assert minor.status_code == 200
    assert "mayores de 18" in minor.get_data(as_text=True)
    no_method = _post_step(client, 1, body_fat_pct="25", body_fat_method="none")
    assert "cómo has medido" in no_method.get_data(as_text=True)
    no_hip = _post_step(client, 1, hip_cm="")
    assert "también la cadera" in no_hip.get_data(as_text=True)
    assert onboarding.get_draft(_user(seeded)).data == {}

    _post_step(client, 1)
    sport = _post_step(client, 2, other_activity_sessions_per_week="2", other_activity_minutes="0")
    assert "cuánto dura" in sport.get_data(as_text=True)


def _user(database: SQLAlchemy) -> Any:
    from app.models import User

    user = database.session.scalar(select(User))
    assert user is not None
    return user


def test_the_equipment_step_starts_solved_and_asks_less(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    """El paso 4 llega resuelto: el material del sitio marcado y lo demás plegado."""
    _signup(client)
    for number in (1, 2, 3):
        _post_step(client, number)
    page = client.get("/cuestionario/paso/4").get_data(as_text=True)

    assert 'value="barbell" checked' in page
    assert 'value="hack_squat" checked' not in page  # no está en el preset de gimnasio básico
    assert "Gimnasio básico" in page  # el resumen dice de dónde sale
    assert "Ajustar lo que tengo" in page
    assert "La barra corta con ondulaciones" in page  # la ayuda de la barra EZ
    # Ni texto libre de ejercicios ni ocho desplegables de lesiones a la vista.
    assert 'name="disliked_exercises"' not in page
    assert 'id="exercise-names"' not in page
    assert 'name="has_injuries"' in page

    too_many = _post_step(client, 4, priority_muscles=["glutes", "shoulders", "chest"])
    assert "como mucho dos" in too_many.get_data(as_text=True)
    nothing = _post_step(client, 4, equipment=[])
    assert "al menos una opción" in nothing.get_data(as_text=True)

    assert _post_step(client, 4).status_code == 302
    draft = onboarding.get_draft(_user(seeded))
    assert draft.data["injuries"] == {"knee": "mild"}
    assert draft.data["equipment_for_location"] == "basic_gym"
    assert "has_injuries" not in draft.data  # solo abre el bloque, no es una respuesta

    # Al cambiar de sitio, el material vuelve al preset nuevo.
    _post_step(client, 3, training_location="home_bodyweight")
    page = client.get("/cuestionario/paso/4").get_data(as_text=True)
    assert 'value="body_only" checked' in page
    assert 'value="barbell" checked' not in page


def test_review_blocks_until_complete_and_shows_the_answers(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _signup(client)
    for number in range(1, 5):
        _post_step(client, number)
    early = client.get("/cuestionario/revisar", follow_redirects=True)
    assert "Faltan respuestas en el paso 5" in early.get_data(as_text=True)
    for number in range(5, 8):
        _post_step(client, number)
    assert client.get("/cuestionario").headers["Location"].endswith("/cuestionario/revisar")
    page = client.get("/cuestionario/revisar").get_data(as_text=True)
    for text in (
        "Mujer",
        "1992-05-20",
        "Gimnasio básico",
        "Perder grasa",
        "Rodilla",
        "hígado, coles",
    ):
        assert text in page, text
    assert "Generar mi plan" in page


def test_completing_generates_plan_and_routine(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    _fill_all(client)
    done = client.post("/cuestionario/revisar")
    assert done.status_code == 302
    assert done.headers["Location"].endswith("/cuestionario/resultado")

    user = _user(seeded)
    profile = seeded.session.scalar(select(Profile))
    assert profile is not None
    assert profile.version == 1
    assert profile.user_id == user.id
    plan = seeded.session.scalar(select(Plan))
    routine = seeded.session.scalar(select(Routine))
    assert plan is not None
    assert routine is not None
    assert seeded.session.scalar(select(WeightLog)) is not None
    assert seeded.session.scalar(select(QuestionnaireDraft)) is None

    page = client.get("/cuestionario/resultado").get_data(as_text=True)
    assert "Plan y rutina generados" in page
    assert f"{plan.calorie_target}" in page
    assert routine.name in page
    assert "Día 1" in page

    panel = client.get("/panel").get_data(as_text=True)
    assert "Ver plan de nutrición" in panel
    assert f"{plan.calorie_target}" in panel


def test_updating_the_questionnaire_creates_a_new_version(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _signup(client)
    _fill_all(client)
    client.post("/cuestionario/revisar")
    again = client.get("/cuestionario")
    assert again.headers["Location"].endswith("/cuestionario/revisar")  # pre-filled draft
    page = client.get("/cuestionario/paso/1").get_data(as_text=True)
    assert 'value="1992-05-20"' in page
    assert _post_step(client, 5, goal="maintenance").status_code == 302
    client.post("/cuestionario/revisar")
    versions = seeded.session.scalars(select(Profile).order_by(Profile.version)).all()
    assert [v.version for v in versions] == [1, 2]
    assert versions[1].goal.value == "maintenance"
    plans_ = seeded.session.scalars(select(Plan).order_by(Plan.version)).all()
    assert [p.status.value for p in plans_] == ["superseded", "active"]


def test_hard_stop_saves_the_profile_but_no_plan(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    for number in range(1, 7):
        _post_step(client, number)
    _post_step(client, 7, is_pregnant_or_breastfeeding="y")
    done = client.post("/cuestionario/revisar", follow_redirects=True)
    text = done.get_data(as_text=True)
    assert "no podemos darte un plan" in text
    assert "embarazo" in text.lower()
    assert seeded.session.scalar(select(Profile)) is not None
    assert seeded.session.scalar(select(Plan)) is None
    panel = client.get("/panel").get_data(as_text=True)
    assert "Sin plan de nutrición" in panel


def test_engine_failure_keeps_the_draft_and_explains(
    client: FlaskClient, seeded: SQLAlchemy, monkeypatch: Any
) -> None:
    _signup(client)
    _fill_all(client)

    def explode(*_args: Any, **_kwargs: Any) -> None:
        from app.engine.safety import SafetyError
        from app.engine.types import Note

        raise SafetyError((Note("safety.below_floor", level="error"),))

    monkeypatch.setattr(onboarding.plans, "generate_for_profile", explode)
    response = client.post("/cuestionario/revisar", follow_redirects=True)
    assert "No se pudo generar el plan" in response.get_data(as_text=True)
    assert seeded.session.scalar(select(QuestionnaireDraft)) is not None
    assert seeded.session.scalar(select(Profile)) is None


def test_result_without_profile_redirects_to_the_questionnaire(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _signup(client)
    response = client.get("/cuestionario/resultado")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/cuestionario")


def test_more_validation_branches(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    assert _post_step(client, 1, birth_date="not-a-date").status_code == 200
    late_birthday_minor = _post_step(client, 1, birth_date="2008-12-01")
    assert "mayores de 18" in late_birthday_minor.get_data(as_text=True)
    ancient = _post_step(client, 1, birth_date="1900-01-01")
    assert "Revisa la fecha" in ancient.get_data(as_text=True)
    _post_step(client, 1)
    sport = _post_step(
        client,
        2,
        other_activity_sessions_per_week="2",
        other_activity_minutes="45",
        other_activity_intensity="",
    )
    assert "Indica la intensidad" in sport.get_data(as_text=True)
    for number in (2, 3, 4):
        _post_step(client, number)
    past = _post_step(client, 5, target_date="2020-01-01")
    assert "tiene que ser futura" in past.get_data(as_text=True)


def test_saved_answers_are_shown_again_on_every_step(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _signup(client)
    _fill_all(client)
    equipment_page = client.get("/cuestionario/paso/4").get_data(as_text=True)
    assert 'value="barbell" checked' in equipment_page
    assert (
        '<option selected value="mild">' in equipment_page
        or 'value="mild" selected' in equipment_page
    )
    marca = re.search(r'<input[^>]*name="has_injuries"[^>]*>', equipment_page)
    assert marca is not None
    assert "checked" in marca.group(0)  # la lesión declarada abre el bloque
    nutrition_page = client.get("/cuestionario/paso/6").get_data(as_text=True)
    assert 'value="hígado, coles"' in nutrition_page


def test_impossible_equipment_keeps_the_nutrition_plan(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _signup(client)
    for number in (1, 2, 3):
        _post_step(client, number)
    _post_step(client, 4, equipment=["cardio_machine"], disliked_exercises="")
    for number in (5, 6, 7):
        _post_step(client, number)
    done = client.post("/cuestionario/revisar", follow_redirects=True)
    text = done.get_data(as_text=True)
    assert "No pudimos montar una rutina" in text
    assert seeded.session.scalar(select(Plan)) is not None
    assert seeded.session.scalar(select(Routine)) is None
    assert "material" in text.lower()
