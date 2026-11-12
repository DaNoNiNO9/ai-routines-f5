"""Installable app: manifest, service worker, offline page, queued sets and wake lock."""

from __future__ import annotations

from pathlib import Path

from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.models import WorkoutSession
from tests.integration.test_workout_flow import _with_routine

STATIC = Path(__file__).resolve().parents[2] / "app" / "static"


def test_the_manifest_makes_the_app_installable(client: FlaskClient) -> None:
    response = client.get("/manifest.webmanifest")
    assert response.status_code == 200
    assert response.mimetype == "application/manifest+json"
    data = response.get_json(force=True)
    assert data["name"] == "Alza"
    assert data["display"] == "standalone"
    assert data["start_url"] == "/panel"
    sizes = {icon["sizes"] for icon in data["icons"]}
    assert {"192x192", "512x512"} <= sizes
    assert any(icon["purpose"] == "maskable" for icon in data["icons"])
    for icon in data["icons"]:
        assert client.get(icon["src"]).status_code == 200


def test_the_service_worker_covers_the_whole_app(client: FlaskClient) -> None:
    response = client.get("/sw.js?v=0.1.0")
    assert response.status_code == 200
    assert "javascript" in response.mimetype
    assert response.headers["Service-Worker-Allowed"] == "/"
    assert response.headers["Cache-Control"] == "no-cache"
    body = response.get_data(as_text=True)
    assert "/sin-conexion" in body
    assert "/static/video/" in body  # los vídeos no se guardan


def test_every_precached_file_exists(client: FlaskClient) -> None:
    body = (STATIC / "js" / "sw.js").read_text(encoding="utf-8")
    start = body.index("var PRECACHE = [")
    block = body[start : body.index("];", start)]
    paths = [line.strip().strip('",') for line in block.splitlines()[1:] if line.strip()]
    paths = [path for path in paths if path.startswith("/")]
    assert len(paths) >= 5
    for path in paths:
        if path == "OFFLINE_URL":
            continue
        assert client.get(path).status_code == 200, path


def test_the_offline_page_is_public(client: FlaskClient) -> None:
    response = client.get("/sin-conexion")
    assert response.status_code == 200
    assert "Sin conexión" in response.get_data(as_text=True)


def test_every_page_links_the_manifest_and_registers_the_worker(
    app: Flask, client: FlaskClient
) -> None:
    html = client.get("/").get_data(as_text=True)
    assert 'rel="manifest" href="/manifest.webmanifest"' in html
    assert f'data-sw="/sw.js?v={app.config["APP_VERSION"]}"' in html
    assert 'id="i18n-js"' in html


def test_the_session_keeps_the_screen_on_and_logout_clears_the_phone(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    client.post("/entreno/empezar/1")
    session = seeded.session.scalar(select(WorkoutSession))
    assert session is not None
    html = client.get(f"/entreno/{session.id}").get_data(as_text=True)
    assert "data-wake-lock" in html
    assert 'class="set-form"' in html
    assert "data-logout" in html


def test_the_account_page_explains_how_to_install(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    html = client.get("/cuenta").get_data(as_text=True)
    assert "data-install-button" in html
    assert "Añadir a pantalla de inicio" in html


def test_a_set_sent_twice_is_stored_once(client: FlaskClient, seeded: SQLAlchemy) -> None:
    """The offline queue may resend a set: the server overwrites, never duplicates."""
    from tests.integration.test_workout_flow import _log, _routine

    _with_routine(client)
    item = _routine(seeded).days[0].exercises[0]
    client.post("/entreno/empezar/1")
    session = seeded.session.scalar(select(WorkoutSession))
    assert session is not None
    _log(client, session.id, item, set_index=1, weight_kg="60", reps="8")
    _log(client, session.id, item, set_index=1, weight_kg="60", reps="8")
    seeded.session.refresh(session)
    assert len([row for row in session.sets if row.set_index == 1]) == 1
