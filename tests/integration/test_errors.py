"""Global error handling: HTML pages, JSON for API clients, CSRF and logging."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from tests.conftest import AppFactory


def test_404_renders_error_page(client: FlaskClient) -> None:
    response = client.get("/no-existe")
    assert response.status_code == 404
    assert response.mimetype == "text/html"
    html = response.get_data(as_text=True)
    assert "404" in html
    assert "Página no encontrada" in html


def test_404_under_api_prefix_returns_json(client: FlaskClient) -> None:
    response = client.get("/api/no-existe")
    assert response.status_code == 404
    assert response.mimetype == "application/json"
    body = response.get_json()
    assert body["error"]["code"] == 404
    assert body["error"]["request_id"]


def test_404_with_json_accept_header_returns_json(client: FlaskClient) -> None:
    response = client.get("/no-existe", headers={"Accept": "application/json"})
    assert response.status_code == 404
    assert response.get_json()["error"]["title"] == "Página no encontrada"


def test_405_keeps_allow_header(client: FlaskClient) -> None:
    response = client.post("/health")
    assert response.status_code == 405
    assert "GET" in response.headers["Allow"]
    assert "Método no permitido" in response.get_data(as_text=True)


def test_403_renders_generic_page(client: FlaskClient) -> None:
    response = client.get("/_debug/abort/403")
    assert response.status_code == 403
    assert "Acceso denegado" in response.get_data(as_text=True)


def test_abort_with_unknown_code_falls_back_to_404(client: FlaskClient) -> None:
    assert client.get("/_debug/abort/999").status_code == 404


def test_unhandled_exception_propagates_in_testing_by_default(client: FlaskClient) -> None:
    with pytest.raises(RuntimeError, match="Deliberate failure"):
        client.get("/_debug/boom")


def test_500_page_when_exceptions_are_not_propagated(make_app: AppFactory) -> None:
    app = make_app(PROPAGATE_EXCEPTIONS=False)
    response = app.test_client().get("/_debug/boom")
    assert response.status_code == 500
    html = response.get_data(as_text=True)
    assert "500" in html
    assert "Error interno" in html


def test_500_is_logged_with_traceback_to_json_file(make_app: AppFactory, tmp_path: Path) -> None:
    app = make_app(PROPAGATE_EXCEPTIONS=False, LOG_TO_FILE=True)
    app.test_client().get("/_debug/boom", headers={"X-Request-ID": "req-boom-1"})

    log_file = tmp_path / "logs" / "alza.log"
    assert log_file.exists()
    records = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    errors = [r for r in records if r["level"] == "ERROR" and r["request_id"] == "req-boom-1"]
    assert errors, records
    assert "Deliberate failure from /_debug/boom" in errors[0]["exc_info"]
    assert errors[0]["path"] == "/_debug/boom"


def test_error_page_shows_request_id(client: FlaskClient) -> None:
    response = client.get("/no-existe", headers={"X-Request-ID": "trace-abc-123"})
    assert response.headers["X-Request-ID"] == "trace-abc-123"
    assert "trace-abc-123" in response.get_data(as_text=True)


def test_csrf_missing_token_returns_400_page(make_app: AppFactory) -> None:
    app = make_app(WTF_CSRF_ENABLED=True)
    response = app.test_client().post("/_debug/echo", data={"message": "hola"})
    assert response.status_code == 400
    assert "formulario no válido" in response.get_data(as_text=True)


def test_csrf_valid_token_is_accepted(make_app: AppFactory) -> None:
    app: Flask = make_app(WTF_CSRF_ENABLED=True)
    client = app.test_client()
    page = client.get("/_debug/echo").get_data(as_text=True)
    match = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page)
    assert match, page
    response = client.post("/_debug/echo", data={"message": "hola", "csrf_token": match.group(1)})
    assert response.status_code == 200
    assert 'class="echoed">hola<' in response.get_data(as_text=True)
