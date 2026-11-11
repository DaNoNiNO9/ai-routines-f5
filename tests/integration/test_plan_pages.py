"""Dashboard, nutrition and training pages rendered with real generated data."""

from __future__ import annotations

from datetime import timedelta

from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.models import Routine, User, WeightLog
from tests.integration.test_onboarding import _fill_all, _post_step, _signup


def _generate(client: FlaskClient) -> None:
    _signup(client)
    _fill_all(client)
    assert client.post("/cuestionario/revisar").status_code == 302


def test_pages_redirect_to_the_questionnaire_without_a_profile(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _signup(client)
    for path in ("/nutricion", "/entrenamiento", "/entrenamiento/dia/1"):
        response = client.get(path)
        assert response.status_code == 302, path
        assert response.headers["Location"].endswith("/cuestionario"), path


def test_dashboard_shows_today_next_session_weight_and_review(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _generate(client)
    page = client.get("/panel").get_data(as_text=True)
    assert "Hoy" in page
    assert "kcal" in page
    assert "Próxima sesión" in page
    assert "Día 1" in page
    assert "Ver la sesión" in page
    assert "64 <small>kg" in page  # today's weigh-in from the questionnaire, no ".0"
    assert 'id="weight-data"' not in page  # one point: no chart yet
    assert "Revisión" in page
    assert 'href="/panel" aria-current="page"' in page
    assert "chart-4.5.1.umd.js" not in page

    user = seeded.session.scalar(select(User))
    assert user is not None
    seeded.session.add(
        WeightLog(user=user, logged_on=user.today() - timedelta(days=1), weight_kg=64.4)
    )
    seeded.session.commit()
    page = client.get("/panel").get_data(as_text=True)
    assert 'id="weight-data"' in page
    assert "chart-4.5.1.umd.js" in page
    assert "alpine-3.17.2.min.js" in page


def test_nutrition_page_explains_the_plan(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _generate(client)
    page = client.get("/nutricion").get_data(as_text=True)
    for text in (
        "Objetivo diario",
        "Macronutrientes",
        "Comidas",
        "Cómo lo calculamos",
        "Katch-McArdle",
        "usada",
        "Cómo se ajusta",
        "Cambios del plan",
        "Plan inicial",
        'id="macros-data"',
        'id="tdee-data"',
        "chart-4.5.1.umd.js",
        'href="/nutricion" aria-current="page"',
    ):
        assert text in page, text


def test_training_pages_show_days_volume_and_alternatives(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _generate(client)
    overview = client.get("/entrenamiento").get_data(as_text=True)
    routine = seeded.session.scalar(select(Routine))
    assert routine is not None
    for text in (routine.name, "Volumen semanal", "Cardio y pasos", "Día 1", "Ver la sesión"):
        assert text in overview, text
    assert "Semana 1" in overview

    day = client.get("/entrenamiento/dia/1").get_data(as_text=True)
    first = routine.days[0].exercises[0]
    assert first.exercise.name_es in day
    assert "img/exercises/" in day
    assert "posición inicial" in day
    assert "Alternativas" in day
    assert "Reserva por semana" in day
    assert f"{first.sets}</dd>" in day
    assert "Día 2" in day  # link to the following day
    assert client.get("/entrenamiento/dia/9").status_code == 404
    assert client.get("/entrenamiento/dia/0").status_code == 404


def test_blocked_plan_has_honest_empty_states(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    for number in range(1, 7):
        _post_step(client, number)
    _post_step(client, 7, is_pregnant_or_breastfeeding="y")
    client.post("/cuestionario/revisar")
    assert "Sin plan de nutrición" in client.get("/panel").get_data(as_text=True)
    nutrition = client.get("/nutricion").get_data(as_text=True)
    assert "No hay plan de nutrición" in nutrition
    assert "embarazo" in nutrition.lower()
    training = client.get("/entrenamiento").get_data(as_text=True)
    assert "Sin rutina" in training
    assert client.get("/entrenamiento/dia/1").headers["Location"].endswith("/entrenamiento")


def test_impossible_equipment_explains_the_missing_routine(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _signup(client)
    for number in (1, 2, 3):
        _post_step(client, number)
    _post_step(client, 4, equipment=["cardio_machine"], disliked_exercises="")
    for number in (5, 6, 7):
        _post_step(client, number)
    client.post("/cuestionario/revisar")
    training = client.get("/entrenamiento").get_data(as_text=True)
    assert "No pudimos montar una rutina" in training
    panel = client.get("/panel").get_data(as_text=True)
    assert "Sin rutina activa" in panel


def test_alpine_loads_after_the_components_it_needs(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    """Alpine starts in a microtask, so ``alpine:init`` fires before any later script.

    With the order swapped, `x-data="restTimer(...)"` resolves to nothing and the
    rest timer disappears instead of counting down.
    """
    _signup(client)
    page = client.get("/panel").get_data(as_text=True)
    assert "forja.js" in page
    assert "alpine-3.17.2.min.js" in page
    assert page.index("forja.js") < page.index("alpine-3.17.2.min.js")


def test_the_theme_starts_dark_and_can_be_switched(
    client: FlaskClient, database: SQLAlchemy
) -> None:
    dark = client.get("/").get_data(as_text=True)
    assert 'data-theme="dark"' in dark
    assert "Cambiar al tema claro" in dark

    switched = client.post("/tema", data={"next": "/"}, follow_redirects=True)
    light = switched.get_data(as_text=True)
    assert 'data-theme="light"' in light
    assert "Cambiar al tema oscuro" in light

    back = client.post("/tema", data={"next": "/"}, follow_redirects=True)
    assert 'data-theme="dark"' in back.get_data(as_text=True)


def test_the_theme_switch_never_redirects_off_site(
    client: FlaskClient, database: SQLAlchemy
) -> None:
    for target in ("https://evil.example.com/", "//evil.example.com", "javascript:alert(1)"):
        response = client.post("/tema", data={"next": target})
        assert response.headers["Location"].endswith("/"), target
        assert "evil" not in response.headers["Location"], target
