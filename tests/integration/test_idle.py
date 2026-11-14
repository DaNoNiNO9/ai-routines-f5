"""Idle sessions: closed on a computer after the time, never on a phone or mid-workout."""

from __future__ import annotations

import time

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy

from tests.integration.test_auth import PASSWORD, _register
from tests.integration.test_workout_flow import _with_routine

DESKTOP = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36"}
PHONE = {"User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) Chrome/130.0 Mobile Safari/537.36"}


def _age_session(client: FlaskClient, seconds: int) -> None:
    with client.session_transaction() as session:
        session["last_seen"] = int(time.time()) - seconds


@pytest.fixture
def short(app: Flask) -> Flask:
    app.config["IDLE_TIMEOUT_MINUTES"] = 10
    return app


def test_a_computer_left_idle_goes_to_the_login(
    client: FlaskClient, database: SQLAlchemy, short: Flask
) -> None:
    _register(client)
    assert client.get("/panel", headers=DESKTOP).status_code == 200
    _age_session(client, 11 * 60)
    response = client.get("/panel", headers=DESKTOP)
    assert response.status_code == 302
    assert "/entrar" in response.headers["Location"]
    assert "next=/panel" in response.headers["Location"]
    assert response.headers["Clear-Site-Data"] == '"cache", "storage"'
    page = client.get("/entrar").get_data(as_text=True)
    assert "Tu sesión se cerró tras un rato sin actividad" in page
    assert client.get("/panel", headers=DESKTOP).status_code == 302  # ya no hay sesión


def test_activity_keeps_it_open(client: FlaskClient, database: SQLAlchemy, short: Flask) -> None:
    _register(client)
    _age_session(client, 9 * 60)
    assert client.get("/panel", headers=DESKTOP).status_code == 200
    _age_session(client, 9 * 60)  # el reloj volvió a empezar con la visita anterior
    assert client.get("/panel", headers=DESKTOP).status_code == 200


def test_the_status_does_not_count_as_activity(
    client: FlaskClient, database: SQLAlchemy, short: Flask
) -> None:
    _register(client)
    _age_session(client, 9 * 60)
    state = client.get("/sesion/estado", headers=DESKTOP).get_json()
    assert state["signed_in"] is True
    assert 50 <= state["remaining"] <= 60
    again = client.get("/sesion/estado", headers=DESKTOP).get_json()
    assert again["remaining"] <= state["remaining"]
    kept = client.post("/sesion/seguir", headers=DESKTOP).get_json()
    assert kept["remaining"] == 600
    assert client.get("/sesion/estado", headers=DESKTOP).get_json()["remaining"] >= 595


def test_phones_are_never_closed_for_being_idle(
    client: FlaskClient, database: SQLAlchemy, short: Flask
) -> None:
    _register(client)
    _age_session(client, 5 * 3600)
    assert client.get("/panel", headers=PHONE).status_code == 200
    _age_session(client, 5 * 3600)
    assert client.get("/panel", headers={"Sec-CH-UA-Mobile": "?1"}).status_code == 200
    assert client.get("/sesion/estado", headers=PHONE).get_json()["remaining"] is None


def test_remember_me_is_never_closed_for_being_idle(
    client: FlaskClient, database: SQLAlchemy, short: Flask
) -> None:
    _register(client)
    client.post("/salir")
    client.post("/entrar", data={"email": "ana@example.com", "password": PASSWORD, "remember": "y"})
    _age_session(client, 5 * 3600)
    assert client.get("/panel", headers=DESKTOP).status_code == 200


def test_never_closed_in_the_middle_of_a_workout(
    client: FlaskClient, seeded: SQLAlchemy, short: Flask
) -> None:
    _with_routine(client)
    client.post("/entreno/empezar/1")
    _age_session(client, 3600)
    assert client.get("/panel", headers=DESKTOP).status_code == 200


def test_the_dialog_is_only_on_pages_that_can_close(
    client: FlaskClient, database: SQLAlchemy, short: Flask
) -> None:
    _register(client)
    assert 'id="idle-dialog"' in client.get("/panel", headers=DESKTOP).get_data(as_text=True)
    assert 'data-timeout="600"' in client.get("/panel", headers=DESKTOP).get_data(as_text=True)
    assert 'id="idle-dialog"' not in client.get("/panel", headers=PHONE).get_data(as_text=True)


def test_an_unattended_page_is_sent_to_the_login(
    client: FlaskClient, database: SQLAlchemy, short: Flask
) -> None:
    _register(client)
    _age_session(client, 10 * 60)
    response = client.get("/sesion/caducada", headers=DESKTOP)
    assert response.headers["Location"].endswith("/entrar")
    # Si otra pestaña seguía activa, no se cierra.
    _register(client, email="otra@example.com")
    response = client.get("/sesion/caducada", headers=DESKTOP)
    assert response.headers["Location"].endswith("/panel")
