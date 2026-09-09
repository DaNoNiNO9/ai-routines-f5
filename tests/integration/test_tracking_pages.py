"""The diary through HTTP: weight, intake, activity, measurements and their validation."""

from __future__ import annotations

from datetime import timedelta

from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.models import ActivityLog, BodyMeasurement, IntakeLog, User, WeightLog
from tests.integration.test_onboarding import _fill_all, _signup


def _user(database: SQLAlchemy) -> User:
    user = database.session.scalar(select(User))
    assert user is not None
    return user


def test_diary_requires_a_session(client: FlaskClient, database: SQLAlchemy) -> None:
    for path in ("/diario", "/diario/perimetros"):
        response = client.get(path)
        assert response.status_code == 302
        assert "/entrar" in response.headers["Location"]


def test_signing_up_does_not_hijack_the_diary_url(client: FlaskClient, seeded: SQLAlchemy) -> None:
    # "/registro" is the sign-up page; the diary lives at "/diario".
    assert "Crear cuenta" in client.get("/registro").get_data(as_text=True)
    _signup(client)
    assert "Diario" in client.get("/diario").get_data(as_text=True)


def test_weight_intake_and_activity_are_saved_for_the_chosen_day(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _signup(client)
    user = _user(seeded)
    today = user.today()
    yesterday = today - timedelta(days=1)

    saved = client.post(
        "/diario/peso", data={"day": today.isoformat(), "weight_kg": "80.4"}, follow_redirects=True
    )
    assert "Peso guardado" in saved.get_data(as_text=True)

    client.post(
        "/diario/ingesta",
        data={
            "day": yesterday.isoformat(),
            "calories": "2150",
            "protein_g": "160",
            "carbs_g": "200",
            "fat_g": "62",
            "adherence_pct": "90",
        },
    )
    client.post(
        "/diario/actividad",
        data={
            "day": today.isoformat(),
            "steps": "9500",
            "cardio_kind": "liss",
            "cardio_minutes": "30",
        },
    )
    seeded.session.expire_all()

    weight = seeded.session.scalar(select(WeightLog).where(WeightLog.logged_on == today))
    assert weight is not None
    assert weight.weight_kg == 80.4
    intake = seeded.session.scalar(select(IntakeLog))
    assert intake is not None
    assert intake.logged_on == yesterday
    assert intake.calories == 2150
    assert intake.adherence_pct == 90
    activity = seeded.session.scalar(select(ActivityLog))
    assert activity is not None
    assert activity.steps == 9500
    assert activity.cardio_minutes == 30

    page = client.get("/diario").get_data(as_text=True)
    assert "80.4" in page
    assert "2150" in page
    assert "9500" in page


def test_the_diary_shows_the_day_asked_for_and_never_the_future(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _signup(client)
    today = _user(seeded).today()
    past = today - timedelta(days=3)
    page = client.get(f"/diario?fecha={past.isoformat()}").get_data(as_text=True)
    assert f'value="{past.isoformat()}"' in page

    future = (today + timedelta(days=5)).isoformat()
    assert f'value="{today.isoformat()}"' in client.get(f"/diario?fecha={future}").get_data(
        as_text=True
    )
    assert client.get("/diario?fecha=no-es-una-fecha").status_code == 200


def test_invalid_entries_are_rejected_with_their_message(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _signup(client)
    today = _user(seeded).today()

    heavy = client.post("/diario/peso", data={"day": today.isoformat(), "weight_kg": "700"})
    assert heavy.status_code == 200
    assert "El número debe estar entre 25 y 350" in heavy.get_data(as_text=True)

    future = client.post(
        "/diario/peso",
        data={"day": (today + timedelta(days=1)).isoformat(), "weight_kg": "80"},
    )
    assert "todavía no ha llegado" in future.get_data(as_text=True)

    text = client.post("/diario/ingesta", data={"day": today.isoformat(), "calories": "muchas"})
    assert text.status_code == 200
    assert seeded.session.scalar(select(IntakeLog)) is None

    half_cardio = client.post(
        "/diario/actividad",
        data={"day": today.isoformat(), "steps": "8000", "cardio_minutes": "40"},
    )
    assert "qué tipo de cardio" in half_cardio.get_data(as_text=True)
    no_minutes = client.post(
        "/diario/actividad",
        data={"day": today.isoformat(), "steps": "8000", "cardio_kind": "hiit"},
    )
    assert "cuántos minutos" in no_minutes.get_data(as_text=True)
    assert seeded.session.scalar(select(ActivityLog)) is None


def test_measurements_are_saved_and_listed(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    today = _user(seeded).today()

    empty = client.post("/diario/perimetros", data={"day": today.isoformat()})
    assert "al menos una medida" in empty.get_data(as_text=True)

    no_method = client.post(
        "/diario/perimetros",
        data={"day": today.isoformat(), "waist_cm": "78", "body_fat_pct": "18"},
    )
    assert "cómo has medido" in no_method.get_data(as_text=True)

    saved = client.post(
        "/diario/perimetros",
        data={
            "day": today.isoformat(),
            "neck_cm": "34",
            "waist_cm": "78",
            "hip_cm": "96",
            "body_fat_pct": "22",
            "body_fat_method": "calipers",
        },
        follow_redirects=True,
    )
    assert "Medidas guardadas" in saved.get_data(as_text=True)
    row = seeded.session.scalar(select(BodyMeasurement))
    assert row is not None
    assert row.waist_cm == 78
    assert row.body_fat_pct == 22
    page = saved.get_data(as_text=True)
    assert "78" in page
    assert "22" in page


def test_the_diary_shows_the_steps_target_once_there_is_a_plan(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _signup(client)
    assert "pasos al día" not in client.get("/diario").get_data(as_text=True)
    _fill_all(client)
    client.post("/cuestionario/revisar")
    assert "pasos al día" in client.get("/diario").get_data(as_text=True)


def test_one_diary_never_leaks_into_another(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    today = _user(seeded).today()
    client.post(
        "/diario/peso", data={"day": today.isoformat(), "weight_kg": "80.4"}, follow_redirects=True
    )
    client.post("/salir", follow_redirects=True)

    other = client.post(
        "/registro",
        data={
            "email": "otra@example.com",
            "display_name": "Otra",
            "password": "una contraseña larga",
            "password_confirm": "una contraseña larga",
            "consent": "y",
        },
    )
    assert other.status_code == 302
    page = client.get("/diario").get_data(as_text=True)
    assert "80.4" not in page
