"""Smoke tests: the application boots and answers HTTP requests."""

from __future__ import annotations

from flask import Flask
from flask.testing import FlaskClient

from app import __version__


def test_app_is_in_testing_mode(app: Flask) -> None:
    assert app.testing is True
    assert app.config["ENV_NAME"] == "testing"


def test_index_responds_200_with_brand(client: FlaskClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Forja" in html
    assert "herramienta orientativa" in html


def test_health_returns_status_version_and_env(client: FlaskClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "version": __version__, "env": "testing"}


def test_unknown_route_returns_404(client: FlaskClient) -> None:
    assert client.get("/no-existe").status_code == 404
