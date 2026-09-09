"""Phase 0 smoke tests: the application boots and answers HTTP requests."""

from __future__ import annotations

from flask import Flask
from flask.testing import FlaskClient

from app import __version__, create_app


def test_create_app_without_overrides_uses_defaults() -> None:
    application = create_app()
    assert application.testing is False
    assert application.config["APP_NAME"] == "Forja"


def test_app_is_in_testing_mode(app: Flask) -> None:
    assert app.testing is True


def test_index_responds_200(client: FlaskClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Fase 0 operativa" in response.get_data(as_text=True)


def test_health_returns_status_and_version(client: FlaskClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "version": __version__}


def test_unknown_route_returns_404(client: FlaskClient) -> None:
    assert client.get("/no-existe").status_code == 404
