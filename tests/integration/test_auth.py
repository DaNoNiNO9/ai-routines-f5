"""Registration, login, logout, protected routes, password recovery and abuse limits."""

from __future__ import annotations

import re

from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy

from app.extensions import limiter
from app.services import auth as auth_service
from tests.conftest import AppFactory

PASSWORD = "una contraseña larga"


def _register(client: FlaskClient, email: str = "ana@example.com", **overrides: str) -> object:
    data = {
        "email": email,
        "display_name": "Ana",
        "password": PASSWORD,
        "password_confirm": PASSWORD,
        "consent": "y",
    }
    data.update(overrides)
    return client.post("/registro", data=data)


def _login(
    client: FlaskClient, email: str = "ana@example.com", password: str = PASSWORD, **extra: str
) -> object:
    return client.post("/entrar", data={"email": email, "password": password, **extra})


def test_register_creates_the_account_and_signs_in(
    client: FlaskClient, database: SQLAlchemy
) -> None:
    assert client.get("/registro").status_code == 200
    response = _register(client)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/panel")
    page = client.get("/panel")
    assert page.status_code == 200
    assert "Hola, Ana" in page.get_data(as_text=True)
    user = auth_service.find_by_email("ana@example.com")
    assert user is not None
    assert user.consent_accepted_at is not None
    assert client.get("/_auth/whoami").get_json()["email"] == "ana@example.com"


def test_register_validation_errors(client: FlaskClient, database: SQLAlchemy) -> None:
    _register(client)
    client.post("/salir")
    duplicated = _register(client)
    assert duplicated.status_code == 200
    assert "Ya existe una cuenta" in duplicated.get_data(as_text=True)

    weak = _register(client, email="otra@example.com", password="corta", password_confirm="corta")
    assert "al menos 10 caracteres" in weak.get_data(as_text=True)

    mismatch = _register(client, email="otra@example.com", password_confirm="different one!")
    assert "no coinciden" in mismatch.get_data(as_text=True)

    no_consent = _register(client, email="otra@example.com", consent="")
    assert "aceptar el aviso" in no_consent.get_data(as_text=True)
    assert auth_service.find_by_email("otra@example.com") is None


def test_register_explains_common_and_email_passwords(
    client: FlaskClient, database: SQLAlchemy
) -> None:
    common = _register(client, password="1234567890", password_confirm="1234567890")
    assert "demasiado común" in common.get_data(as_text=True)
    same = _register(client, password="ana@example.com", password_confirm="ana@example.com")
    assert "no puede ser tu correo" in same.get_data(as_text=True)
    _register(client)
    assert client.get("/registro").status_code == 302  # already signed in


def test_login_and_logout(client: FlaskClient, database: SQLAlchemy) -> None:
    _register(client)
    client.post("/salir")
    assert client.get("/_auth/whoami").get_json()["id"] is None

    wrong = _login(client, password="wrong password here")
    assert wrong.status_code == 200
    assert "incorrectos" in wrong.get_data(as_text=True)
    unknown = _login(client, email="nadie@example.com")
    assert "incorrectos" in unknown.get_data(as_text=True)

    ok = _login(client)
    assert ok.status_code == 302
    assert ok.headers["Location"].endswith("/panel")
    assert client.get("/entrar").status_code == 302  # already signed in

    assert client.get("/salir").status_code == 405
    out = client.post("/salir")
    assert out.status_code == 302
    assert client.get("/panel").status_code == 302


def test_inactive_account_cannot_sign_in(client: FlaskClient, database: SQLAlchemy) -> None:
    _register(client)
    client.post("/salir")
    user = auth_service.find_by_email("ana@example.com")
    assert user is not None
    user.is_active = False
    database.session.commit()
    response = _login(client)
    assert "desactivada" in response.get_data(as_text=True)


def test_protected_route_redirects_anonymous_users(
    client: FlaskClient, database: SQLAlchemy
) -> None:
    response = client.get("/panel")
    assert response.status_code == 302
    assert "/entrar?next=%2Fpanel" in response.headers["Location"]
    login_page = client.get(response.headers["Location"])
    assert "Inicia sesión para continuar" in login_page.get_data(as_text=True)


def test_next_parameter_only_accepts_local_paths(client: FlaskClient, database: SQLAlchemy) -> None:
    _register(client)
    client.post("/salir")
    local = client.post(
        "/entrar?next=/panel", data={"email": "ana@example.com", "password": PASSWORD}
    )
    assert local.headers["Location"].endswith("/panel")
    client.post("/salir")
    external = client.post(
        "/entrar?next=https://evil.example.com/",
        data={"email": "ana@example.com", "password": PASSWORD},
    )
    assert external.headers["Location"].endswith("/panel")
    client.post("/salir")
    protocol_relative = client.post(
        "/entrar?next=//evil.example.com", data={"email": "ana@example.com", "password": PASSWORD}
    )
    assert protocol_relative.headers["Location"].endswith("/panel")


def test_remember_me_sets_a_persistent_cookie(client: FlaskClient, database: SQLAlchemy) -> None:
    _register(client)
    client.post("/salir")
    response = _login(client, remember="y")
    cookies = response.headers.getlist("Set-Cookie")
    assert any(cookie.startswith("remember_token=") for cookie in cookies)


def test_password_recovery_flow(app: Flask, client: FlaskClient, database: SQLAlchemy) -> None:
    _register(client)
    client.post("/salir")

    unknown = client.post("/recuperar", data={"email": "nadie@example.com"}, follow_redirects=True)
    assert "Si el correo existe" in unknown.get_data(as_text=True)
    assert "outbox" not in app.extensions

    known = client.post("/recuperar", data={"email": "ana@example.com"}, follow_redirects=True)
    assert "Si el correo existe" in known.get_data(as_text=True)
    outbox = app.extensions["outbox"]
    assert len(outbox) == 1
    match = re.search(r"/restablecer/(\S+)", outbox[0].body)
    assert match, outbox[0].body
    token = match.group(1)

    assert client.get(f"/restablecer/{token}").status_code == 200
    weak = client.post(
        f"/restablecer/{token}", data={"password": "corta", "password_confirm": "corta"}
    )
    assert "al menos 10" in weak.get_data(as_text=True)
    new_password = "otra contraseña larga"
    done = client.post(
        f"/restablecer/{token}",
        data={"password": new_password, "password_confirm": new_password},
    )
    assert done.status_code == 302
    assert _login(client, password=new_password).status_code == 302
    client.post("/salir")

    reused = client.get(f"/restablecer/{token}", follow_redirects=True)
    assert "no es válido o ha caducado" in reused.get_data(as_text=True)
    bogus = client.get("/restablecer/not-a-token", follow_redirects=True)
    assert "no es válido" in bogus.get_data(as_text=True)


def test_recovery_reports_delivery_problems(
    app: Flask, client: FlaskClient, database: SQLAlchemy
) -> None:
    _register(client)
    client.post("/salir")
    app.config["MAIL_BACKEND"] = "pigeon"
    response = client.post("/recuperar", data={"email": "ana@example.com"})
    assert response.status_code == 200
    assert "No se pudo enviar" in response.get_data(as_text=True)


def test_login_is_rate_limited(make_app: AppFactory) -> None:
    app = make_app(RATELIMIT_ENABLED=True)
    limiter.reset()
    with app.app_context():
        from app.extensions import db

        db.create_all()
        client = app.test_client()
        for _ in range(5):
            assert _login(client).status_code == 200
        assert _login(client).status_code == 429
        db.session.remove()
        db.drop_all()


def test_login_requires_a_csrf_token_when_enabled(make_app: AppFactory) -> None:
    app = make_app(WTF_CSRF_ENABLED=True)
    with app.app_context():
        from app.extensions import db

        db.create_all()
        response = app.test_client().post("/entrar", data={"email": "a@b.com", "password": "x"})
        assert response.status_code == 400
        db.session.remove()
        db.drop_all()


def test_whoami_is_hidden_outside_debug(make_app: AppFactory) -> None:
    app = make_app(ENABLE_DEBUG_ROUTES=False)
    assert app.test_client().get("/_auth/whoami").status_code == 404
