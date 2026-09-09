"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app import create_app

AppFactory = Callable[..., Flask]


@pytest.fixture
def make_app(tmp_path: Path) -> AppFactory:
    """Factory that builds a testing app with optional config overrides."""

    def _make(**overrides: Any) -> Flask:
        overrides.setdefault("LOG_DIR", str(tmp_path / "logs"))
        return create_app("testing", overrides)

    return _make


@pytest.fixture
def app(make_app: AppFactory) -> Flask:
    """Application instance configured for testing."""
    return make_app()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """HTTP test client bound to the test application."""
    return app.test_client()
