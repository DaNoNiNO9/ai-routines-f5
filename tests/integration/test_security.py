"""Security headers, cookie flags and rate limiting."""

from __future__ import annotations

from flask.testing import FlaskClient

from app.extensions import limiter
from tests.conftest import AppFactory


def test_security_headers_on_every_response(client: FlaskClient) -> None:
    headers = client.get("/").headers
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in headers["Permissions-Policy"]
    assert "Strict-Transport-Security" not in headers


def test_hsts_only_when_enabled(make_app: AppFactory) -> None:
    app = make_app(ENABLE_HSTS=True)
    headers = app.test_client().get("/").headers
    assert headers["Strict-Transport-Security"].startswith("max-age=31536000")


def test_session_cookie_is_httponly_and_samesite(make_app: AppFactory) -> None:
    app = make_app(WTF_CSRF_ENABLED=True)
    response = app.test_client().get("/_debug/echo")
    cookie = response.headers.get("Set-Cookie", "")
    assert "session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie


def test_rate_limit_returns_429_page_with_retry_after(make_app: AppFactory) -> None:
    app = make_app(RATELIMIT_ENABLED=True)
    limiter.reset()
    client = app.test_client()
    assert client.get("/_debug/limited").status_code == 200
    assert client.get("/_debug/limited").status_code == 200
    blocked = client.get("/_debug/limited")
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
    assert "Demasiadas peticiones" in blocked.get_data(as_text=True)


def test_rate_limit_disabled_in_testing_by_default(client: FlaskClient) -> None:
    for _ in range(5):
        assert client.get("/_debug/limited").status_code == 200
