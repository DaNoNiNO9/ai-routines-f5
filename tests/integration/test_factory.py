"""Application factory and per-environment configuration."""

from __future__ import annotations

import pytest

from app import create_app
from config import MIN_SECRET_KEY_LENGTH

NO_FILE_LOG = {"LOG_TO_FILE": False}


def test_default_environment_is_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FORJA_ENV", raising=False)
    app = create_app(overrides=NO_FILE_LOG)
    assert app.config["ENV_NAME"] == "development"
    assert app.debug is True
    assert app.config["ENABLE_DEBUG_ROUTES"] is True


def test_environment_variable_selects_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORJA_ENV", "Testing")
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
    assert uri.endswith("/instance/forja.db")


def test_production_refuses_missing_secret_and_database() -> None:
    with pytest.raises(RuntimeError) as excinfo:
        create_app("production", {**NO_FILE_LOG, "SECRET_KEY": "", "SQLALCHEMY_DATABASE_URI": ""})
    message = str(excinfo.value)
    assert "SECRET_KEY" in message
    assert "DATABASE_URL" in message


def test_production_refuses_debug_flags() -> None:
    overrides = {
        **NO_FILE_LOG,
        "SECRET_KEY": "x" * MIN_SECRET_KEY_LENGTH,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "DEBUG": True,
        "ENABLE_DEBUG_ROUTES": True,
    }
    with pytest.raises(
        RuntimeError, match=r"DEBUG must be false.*ENABLE_DEBUG_ROUTES must be false"
    ):
        create_app("production", overrides)


def test_production_boots_with_valid_configuration() -> None:
    overrides = {
        **NO_FILE_LOG,
        "SECRET_KEY": "s" * MIN_SECRET_KEY_LENGTH,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
    }
    app = create_app("production", overrides)
    assert app.debug is False
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["ENABLE_HSTS"] is True
    # Debug routes are not mounted in production.
    assert app.test_client().get("/_debug/boom").status_code == 404
