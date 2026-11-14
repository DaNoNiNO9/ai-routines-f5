"""Application factory and per-environment configuration."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from flask import Flask

from app import create_app
from config import MIN_SECRET_KEY_LENGTH

NO_FILE_LOG = {"LOG_TO_FILE": False}


def test_default_environment_is_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALZA_ENV", raising=False)
    app = create_app(overrides=NO_FILE_LOG)
    assert app.config["ENV_NAME"] == "development"
    assert app.debug is True
    assert app.config["ENABLE_DEBUG_ROUTES"] is True


def test_environment_variable_selects_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALZA_ENV", "Testing")
    app = create_app(overrides=NO_FILE_LOG)
    assert app.config["ENV_NAME"] == "testing"
    assert app.testing is True


def test_unknown_configuration_name_raises() -> None:
    with pytest.raises(ValueError, match="Unknown configuration 'staging'"):
        create_app("staging")


def test_sqlite_default_points_to_instance_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app = create_app("development", {**NO_FILE_LOG, "SQLALCHEMY_DATABASE_URI": ""})
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    assert uri.startswith("sqlite:///")
    assert uri.endswith("/instance/alza.db")


def test_production_refuses_missing_secret_and_database() -> None:
    with pytest.raises(RuntimeError) as excinfo:
        create_app("production", {**NO_FILE_LOG, "SECRET_KEY": "", "SQLALCHEMY_DATABASE_URI": ""})
    message = str(excinfo.value)
    assert "SECRET_KEY" in message
    assert "DATABASE_URL" in message


def test_production_refuses_debug_flags() -> None:
    overrides = {
        **NO_FILE_LOG,
        **PRODUCTION_MAIL,
        "SECRET_KEY": "x" * MIN_SECRET_KEY_LENGTH,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "DEBUG": True,
        "ENABLE_DEBUG_ROUTES": True,
    }
    with pytest.raises(
        RuntimeError, match=r"DEBUG must be false.*ENABLE_DEBUG_ROUTES must be false"
    ):
        create_app("production", overrides)


PRODUCTION_MAIL = {"MAIL_BACKEND": "smtp", "MAIL_SERVER": "smtp.example.com", "MAIL_FROM": "a@b.c"}
PRODUCTION_BILLING = {
    "BILLING_BACKEND": "stripe",
    "STRIPE_SECRET_KEY": "sk_test_x",
    "STRIPE_WEBHOOK_SECRET": "whsec_x",
    "STRIPE_PRICE_MONTHLY": "price_monthly",
    "STRIPE_PRICE_YEARLY": "price_yearly",
}


def test_production_requires_smtp_mail() -> None:
    overrides = {
        **NO_FILE_LOG,
        "SECRET_KEY": "s" * MIN_SECRET_KEY_LENGTH,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "MAIL_BACKEND": "log",
    }
    with pytest.raises(RuntimeError, match="MAIL_BACKEND must be smtp"):
        create_app("production", overrides)
    with pytest.raises(RuntimeError, match="MAIL_SERVER and MAIL_FROM"):
        create_app("production", {**overrides, "MAIL_BACKEND": "smtp", "MAIL_SERVER": ""})


def test_production_refuses_the_simulated_checkout_behind_a_paywall() -> None:
    base = {
        **NO_FILE_LOG,
        **PRODUCTION_MAIL,
        "SECRET_KEY": "s" * MIN_SECRET_KEY_LENGTH,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
    }
    with pytest.raises(RuntimeError, match="BILLING_BACKEND must be stripe"):
        create_app("production", {**base, "BILLING_BACKEND": "fake", "PAYWALL_ENABLED": True})
    with pytest.raises(RuntimeError, match="STRIPE_WEBHOOK_SECRET must be set"):
        create_app("production", {**base, **PRODUCTION_BILLING, "STRIPE_WEBHOOK_SECRET": ""})
    # Sin muro de pago (todo gratis) no hace falta pasarela.
    create_app("production", {**base, "BILLING_BACKEND": "fake", "PAYWALL_ENABLED": False})


def test_production_boots_with_valid_configuration() -> None:
    overrides = {
        **NO_FILE_LOG,
        **PRODUCTION_MAIL,
        **PRODUCTION_BILLING,
        "SECRET_KEY": "s" * MIN_SECRET_KEY_LENGTH,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
    }
    app = create_app("production", overrides)
    assert app.debug is False
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["ENABLE_HSTS"] is True
    # Debug routes are not mounted in production.
    assert app.test_client().get("/_debug/boom").status_code == 404


def test_no_two_endpoints_share_a_url_and_method(app: Flask) -> None:
    """A blueprint prefix must not shadow an existing page.

    "/registro" (sign-up) once swallowed the diary, which was registered later
    under the same prefix: Flask keeps both rules and the first one wins.
    """
    seen: dict[tuple[str, str], str] = {}
    clashes: list[str] = []
    for rule in app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            key = (rule.rule, method)
            if key in seen:
                clashes.append(f"{method} {rule.rule}: {seen[key]} y {rule.endpoint}")
            seen[key] = rule.endpoint
    assert clashes == []


def test_behind_a_tunnel_links_use_the_public_https_address(make_app: Callable[..., Flask]) -> None:
    app = make_app(BEHIND_PROXY=True, SERVER_NAME=None)

    @app.get("/_enlace")
    def _enlace() -> str:
        from flask import request, url_for

        return f"{url_for('main.index', _external=True)} {request.remote_addr}"

    headers = {
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "demo.alza.fit",
        "X-Forwarded-For": "203.0.113.7",
    }
    text = app.test_client().get("/_enlace", headers=headers).get_data(as_text=True)
    assert text == "https://demo.alza.fit/ 203.0.113.7"


def test_without_a_proxy_forwarded_headers_are_ignored(make_app: Callable[..., Flask]) -> None:
    app = make_app()

    @app.get("/_enlace")
    def _enlace() -> str:
        from flask import url_for

        return url_for("main.index", _external=True)

    text = app.test_client().get("/_enlace", headers={"X-Forwarded-Host": "evil.example"})
    assert "evil" not in text.get_data(as_text=True)
