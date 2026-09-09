"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from flask import Flask, g, has_app_context
from flask.testing import FlaskClient
from flask_babel import refresh
from flask_sqlalchemy import SQLAlchemy

from app import create_app
from app.extensions import db
from app.seeds.loaders import seed_equipment, seed_exercises

AppFactory = Callable[..., Flask]


@pytest.fixture
def make_app(tmp_path: Path) -> AppFactory:
    """Factory that builds a testing app with optional config overrides."""

    def _make(**overrides: Any) -> Flask:
        overrides.setdefault("LOG_DIR", str(tmp_path / "logs"))
        instance = create_app("testing", overrides)
        instance.test_client_class = FreshClient
        return instance

    return _make


class FreshClient(FlaskClient):
    """Cliente que no se lleva de una petición a otra lo que se guarda en ``g``.

    El fixture de base de datos mantiene abierto un contexto de aplicación
    durante todo el test y las peticiones lo reutilizan, cosa que en
    producción no pasa nunca: cada petición trae el suyo. Sin esta limpieza,
    Flask-Login serviría la segunda petición con el usuario de la primera y
    Flask-Babel con su idioma, y un test de "esto no lo puede ver otra
    persona" pasaría sin comprobar nada.
    """

    def open(self, *args: Any, **kwargs: Any) -> Any:
        if has_app_context():
            g.pop("_login_user", None)
            refresh()
        return super().open(*args, **kwargs)


@pytest.fixture
def app(make_app: AppFactory) -> Flask:
    """Application instance configured for testing."""
    return make_app()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """HTTP test client bound to the test application."""
    return app.test_client()


@pytest.fixture
def database(app: Flask) -> Iterator[SQLAlchemy]:
    """Fresh in-memory schema for one test, inside an application context."""
    with app.app_context():
        db.create_all()
        yield db
        db.session.remove()
        db.drop_all()


@pytest.fixture
def seeded(database: SQLAlchemy) -> SQLAlchemy:
    """``database`` plus the equipment and exercise catalogues (about 0.2 s)."""
    seed_equipment(database.session)
    seed_exercises(database.session)
    database.session.commit()
    return database
