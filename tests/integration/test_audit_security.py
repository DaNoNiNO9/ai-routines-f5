"""Auditoría de seguridad (Fase 13): IDOR, XSS, inyección, CSRF y puertas cerradas.

Lo que aquí se prueba no es que la app haga bien su trabajo, sino que no se
la pueda usar para hacer daño: leer lo de otra persona, colar HTML en una
página, saltarse el token o entrar sin sesión.
"""

from __future__ import annotations

import re

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select, text

from app.models import SetLog, User, WorkoutSession
from tests.conftest import AppFactory
from tests.integration.test_auth import PASSWORD, _register
from tests.integration.test_onboarding import _fill_all

XSS = '"><img src=x onerror=alert(1)><script>alert("xss")</script>'
INJECTION = "' OR 1=1; DROP TABLE users;--"

PUBLIC_PATHS = {
    "/",
    "/health",
    "/sesion/estado",  # a un visitante solo le dice que no ha entrado
    "/favicon.ico",
    "/manifest.webmanifest",
    "/sw.js",
    "/sin-conexion",
    "/precios",
    "/acerca",
    "/privacidad",
    "/entrar",
    "/registro",
    "/recuperar",
    "/tema",
    "/_auth/whoami",
    "/_debug/boom",
    "/_debug/echo",
    "/_debug/limited",
}


def _account(client: FlaskClient, email: str, *, with_plan: bool = False) -> None:
    assert _register(client, email=email).status_code == 302
    if with_plan:
        _fill_all(client)
        assert client.post("/cuestionario/revisar").status_code == 302


def _a_session_with_a_set(client: FlaskClient, database: SQLAlchemy) -> tuple[int, int]:
    started = client.post("/entreno/empezar/1")
    assert started.status_code == 302
    session_row = database.session.scalars(select(WorkoutSession)).first()
    assert session_row is not None
    item = session_row.routine_day.exercises[0]
    logged = client.post(
        f"/entreno/{session_row.id}/serie",
        data={
            "routine_exercise_id": item.id,
            "set_index": 1,
            "weight_kg": "40",
            "reps": "8",
            "rir": "2",
        },
    )
    assert logged.status_code == 302
    set_row = database.session.scalars(select(SetLog)).first()
    assert set_row is not None
    return session_row.id, set_row.id


def test_no_one_can_touch_another_persons_workout(app: Flask, seeded: SQLAlchemy) -> None:
    """IDOR: los identificadores de sesión y de serie son adivinables por diseño."""
    owner = app.test_client()
    _account(owner, "duena@example.com", with_plan=True)
    session_id, set_id = _a_session_with_a_set(owner, seeded)

    intruder = app.test_client()
    _account(intruder, "intrusa@example.com", with_plan=True)

    reads = (f"/entreno/{session_id}", f"/entreno/{session_id}/resumen")
    writes = (
        (
            f"/entreno/{session_id}/serie",
            {"routine_exercise_id": 1, "set_index": 1, "weight_kg": "40", "reps": "8"},
        ),
        (f"/entreno/{session_id}/serie/{set_id}/borrar", {}),
        (f"/entreno/{session_id}/sustituir", {"routine_exercise_id": 1, "exercise_id": 1}),
        (f"/entreno/{session_id}/terminar", {"fatigue": "3"}),
        (f"/entreno/{session_id}/abandonar", {}),
    )
    for path in reads:
        assert intruder.get(path).status_code == 404, path
    for path, payload in writes:
        assert intruder.post(path, data=payload).status_code == 404, path

    # Y la sesión de la dueña sigue viva y sin tocar.
    assert owner.get(f"/entreno/{session_id}").status_code == 200
    assert seeded.session.get(SetLog, set_id) is not None


def test_every_private_page_sends_an_anonymous_visitor_to_the_login(
    app: Flask, seeded: SQLAlchemy
) -> None:
    anonymous = app.test_client()
    checked = 0
    for rule in app.url_map.iter_rules():
        path = str(rule)
        if "GET" not in (rule.methods or set()) or "<" in path or path in PUBLIC_PATHS:
            continue
        response = anonymous.get(path)
        assert response.status_code == 302, path
        assert "/entrar" in response.headers["Location"], path
        checked += 1
    assert checked >= 8


def test_free_text_never_comes_back_as_html(app: Flask, seeded: SQLAlchemy) -> None:
    """Autoescape de Jinja, comprobado donde de verdad se pinta lo que escribe la gente."""
    client = app.test_client()
    assert _register(client, email="xss@example.com", display_name=XSS).status_code == 302
    _fill_all(client)
    assert client.post("/cuestionario/revisar").status_code == 302
    client.post("/diario/peso", data={"day": "2026-09-09", "weight_kg": "64", "notes": XSS})
    client.post(
        "/cuenta/perfil", data={"display_name": XSS, "locale": "es", "timezone": "Europe/Madrid"}
    )

    for path in ("/panel", "/diario", "/cuenta", "/nutricion", "/entrenamiento"):
        page = client.get(path).get_data(as_text=True)
        assert "<img src=x onerror" not in page, path
        assert "<script>alert" not in page, path
        # El texto sale escapado, que es justo lo que se espera ver.
        assert "&lt;script&gt;alert" in page or XSS[:5] not in page, path


def test_injection_payloads_are_data_not_sql(app: Flask, seeded: SQLAlchemy) -> None:
    client = app.test_client()
    assert client.post("/entrar", data={"email": INJECTION, "password": INJECTION}).status_code in {
        200,
        302,
    }
    assert client.post("/recuperar", data={"email": INJECTION}).status_code in {200, 302}

    _account(client, "sql@example.com", with_plan=True)
    saved = client.post(
        "/diario/peso", data={"day": "2026-09-09", "weight_kg": "64", "notes": INJECTION}
    )
    assert saved.status_code == 302
    assert client.get(f"/entreno/progreso?ejercicio={INJECTION}").status_code == 200

    # Las tablas siguen ahí y la nota se guardó tal cual, como texto.
    assert seeded.session.scalar(select(User).where(User.email == "sql@example.com")) is not None
    rows = seeded.session.execute(text("SELECT notes FROM weight_logs")).scalars().all()
    assert INJECTION in rows


def test_a_form_without_its_token_is_refused(make_app: AppFactory) -> None:
    app = make_app(WTF_CSRF_ENABLED=True)
    client = app.test_client()
    response = client.post(
        "/registro",
        data={
            "email": "sin-token@example.com",
            "display_name": "Ana",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "consent": "y",
        },
    )
    assert response.status_code == 400
    with app.app_context():
        from app.extensions import db

        db.create_all()
        assert db.session.scalar(select(User)) is None


def test_passwords_are_stored_hashed_with_a_slow_algorithm(database: SQLAlchemy) -> None:
    from app.services import auth

    user = auth.register_user(email="hash@example.com", password=PASSWORD, display_name="Ana")
    assert PASSWORD not in user.password_hash
    assert user.password_hash.startswith("$argon2")
    assert auth.verify_password(user.password_hash, PASSWORD)
    assert not auth.verify_password(user.password_hash, PASSWORD.upper())


@pytest.mark.parametrize("name", [".env", ".env.production", "instance/alza.db"])
def test_secrets_are_not_in_the_repository(name: str) -> None:
    import subprocess

    from config import BASE_DIR

    tracked = subprocess.run(
        ["git", "ls-files", name],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tracked.stdout.strip() == ""
    ignored = (BASE_DIR / ".gitignore").read_text(encoding="utf-8")
    assert re.search(r"^\.env$", ignored, re.MULTILINE)
    assert "instance/" in ignored
