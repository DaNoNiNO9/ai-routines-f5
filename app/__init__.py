"""Forja (working title: AI Routines F5): application factory.

``create_app()`` builds a fully configured Flask application: per-environment
configuration, logging, extensions, blueprints, error handlers and security
headers. The calculation engine, models and services are imported from here
and never import this module back.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flask import Flask, current_app
from flask_babel import get_locale
from flask_babel import lazy_gettext as _l

from app.cli import register_cli
from app.errors import register_error_handlers
from app.extensions import babel, csrf, db, limiter, login_manager, migrate
from app.i18n import select_locale
from app.logging_config import configure_logging
from app.models.base import render_migration_item
from app.security import register_security_headers
from config import CONFIGS, ProductionConfig

__version__ = "0.1.0"

DEFAULT_ENV = "development"
SQLITE_FILENAME = "forja.db"


def create_app(
    config_name: str | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> Flask:
    """Build and return the Flask application.

    Args:
        config_name: ``"development"``, ``"testing"`` or ``"production"``. Defaults to
            the ``FORJA_ENV`` environment variable, then to ``"development"``.
        overrides: Extra configuration applied last (used by the test suite).

    Returns:
        A configured :class:`flask.Flask` instance.

    Raises:
        ValueError: If ``config_name`` is not a known environment.
        RuntimeError: If the production configuration is incomplete or unsafe.
    """
    name = (config_name or os.environ.get("FORJA_ENV") or DEFAULT_ENV).strip().lower()
    try:
        config_class = CONFIGS[name]
    except KeyError as exc:
        known = ", ".join(sorted(CONFIGS))
        raise ValueError(f"Unknown configuration {name!r}; expected one of: {known}") from exc

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    if overrides:
        app.config.from_mapping(overrides)
    app.config["ENV_NAME"] = name
    app.config["APP_VERSION"] = __version__

    if config_class is ProductionConfig:
        ProductionConfig.validate(app.config)
    _prepare_instance_folder(app)

    configure_logging(app)
    _register_models()
    _init_extensions(app)
    register_cli(app)
    _register_blueprints(app)
    register_error_handlers(app)
    register_security_headers(app)
    app.context_processor(_template_context)

    app.logger.info("Application created (env=%s, debug=%s)", name, app.debug)
    return app


def _prepare_instance_folder(app: Flask) -> None:
    """Create the instance folder and point SQLite there when no DATABASE_URL is set."""
    instance_path = Path(app.instance_path)
    instance_path.mkdir(parents=True, exist_ok=True)
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        db_path = (instance_path / SQLITE_FILENAME).as_posix()
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"


def _register_models() -> None:
    """Import the models package so every table is on ``db.metadata`` before Migrate runs."""
    import app.models  # noqa: F401


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True, render_item=render_migration_item)
    csrf.init_app(app)
    limiter.init_app(app)
    babel.init_app(app, locale_selector=select_locale)
    from app.services.auth import load_user

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = _l("Inicia sesión para continuar.")
    login_manager.login_message_category = "warning"
    login_manager.session_protection = "basic"
    login_manager.user_loader(load_user)


def _register_blueprints(app: Flask) -> None:
    from app.blueprints.auth.routes import bp as auth_bp
    from app.blueprints.dashboard.routes import bp as dashboard_bp
    from app.blueprints.main.routes import bp as main_bp
    from app.blueprints.nutrition.routes import bp as nutrition_bp
    from app.blueprints.onboarding.routes import bp as onboarding_bp
    from app.blueprints.training.routes import bp as training_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(onboarding_bp)
    app.register_blueprint(nutrition_bp)
    app.register_blueprint(training_bp)

    if app.config["ENABLE_DEBUG_ROUTES"]:
        from app.blueprints.debug.routes import bp as debug_bp

        app.register_blueprint(debug_bp, url_prefix="/_debug")


def _template_context() -> dict[str, Any]:
    return {
        "app_name": current_app.config["APP_NAME"],
        "app_version": current_app.config["APP_VERSION"],
        "current_locale": str(get_locale()),
        "current_year": datetime.now(tz=UTC).year,
        "password_min_length": current_app.config["PASSWORD_MIN_LENGTH"],
    }
