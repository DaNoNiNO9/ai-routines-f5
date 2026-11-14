"""Per-environment configuration classes.

The environment is chosen by ``create_app(config_name)`` or the ``ALZA_ENV``
variable (``development`` by default). Secrets and machine-specific values are
read from the environment; a ``.env`` file at the project root is loaded first
(see ``.env.example``). Values already present in the real environment win over
``.env``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

MIN_SECRET_KEY_LENGTH = 32


def env_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable (``1``, ``true``, ``yes`` and ``on`` are true)."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class BaseConfig:
    """Settings shared by every environment. Subclasses override what differs."""

    APP_NAME = "Alza"
    SECRET_KEY = os.environ.get("SECRET_KEY", "")

    # Database. Empty means "SQLite file in the instance folder" (resolved by create_app).
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS: dict[str, Any] = {"pool_pre_ping": True}
    SQLALCHEMY_ECHO = env_bool("SQLALCHEMY_ECHO", False)

    # Sessions and cookies
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = False
    PERMANENT_SESSION_LIFETIME = timedelta(days=14)

    # CSRF (Flask-WTF). Tokens live as long as the session.
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    # Rate limiting (Flask-Limiter). Limits are declared on the sensitive routes.
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True

    # Internationalisation via Flask-Babel
    BABEL_DEFAULT_LOCALE = "es"
    BABEL_DEFAULT_TIMEZONE = "Europe/Madrid"
    LANGUAGES = {"es": "Español", "en": "English"}

    # Logging
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_DIR = os.environ.get("LOG_DIR", str(BASE_DIR / "logs"))
    LOG_TO_FILE = True
    LOG_RETENTION_DAYS = 30
    # Lo más grande que se sube: la exportación de Hevy (8 MB) con margen.
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    # Más que lo que viven las copias de seguridad (30 días): ver app/models/privacy.py.
    ERASURE_LOG_DAYS = 35

    # Email (app/email.py): "log" keeps messages in memory and in the log; "smtp" delivers.
    MAIL_BACKEND = os.environ.get("MAIL_BACKEND", "log")
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USE_TLS = env_bool("MAIL_USE_TLS", True)
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_FROM = os.environ.get("MAIL_FROM", "Alza <no-reply@alza.fit>")

    # Accounts
    PASSWORD_MIN_LENGTH = 10
    PASSWORD_RESET_MAX_AGE = 3600

    # Billing (app/services/billing). "fake" simulates Stripe end to end without an
    # account (checkout, trial, portal, cancellations); "stripe" talks to the real API.
    BILLING_BACKEND = os.environ.get("BILLING_BACKEND", "fake")
    PAYWALL_ENABLED = env_bool("PAYWALL_ENABLED", True)
    BILLING_TRIAL_DAYS = 7
    BILLING_CURRENCY = "eur"
    BILLING_PLANS: dict[str, dict[str, Any]] = {
        "monthly": {"amount_cents": 799, "interval": "month"},
        "yearly": {"amount_cents": 4999, "interval": "year"},
    }
    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_PRICE_MONTHLY = os.environ.get("STRIPE_PRICE_MONTHLY", "")
    STRIPE_PRICE_YEARLY = os.environ.get("STRIPE_PRICE_YEARLY", "")
    # Pinned so the shape of Stripe's objects does not change under our feet.
    STRIPE_API_VERSION = os.environ.get("STRIPE_API_VERSION", "2024-06-20")

    # Open Food Facts (app/services/food.py): product search and barcodes.
    OFF_ENABLED = env_bool("OFF_ENABLED", True)

    # Security headers
    ENABLE_HSTS = False

    # Routes that only exist to exercise error handling (app/blueprints/debug)
    ENABLE_DEBUG_ROUTES = False


class DevelopmentConfig(BaseConfig):
    """Local development: debug on, verbose logs, debug routes available."""

    DEBUG = True
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-only-insecure-secret-key-do-not-deploy"
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "DEBUG")
    ENABLE_DEBUG_ROUTES = True


class TestingConfig(BaseConfig):
    """Test suite: in-memory SQLite, CSRF and rate limiting off unless a test enables them."""

    TESTING = True
    SECRET_KEY = "testing-secret-key-not-for-real-use"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    LOG_TO_FILE = False
    LOG_LEVEL = "DEBUG"
    ENABLE_DEBUG_ROUTES = True
    MAIL_BACKEND = "log"
    # Existing tests exercise every feature; the paywall has its own tests.
    PAYWALL_ENABLED = False
    BILLING_BACKEND = "fake"
    OFF_ENABLED = False  # sin red en los tests; los de comida inyectan respuestas


class ProductionConfig(BaseConfig):
    """Deployment behind HTTPS: secure cookies, HSTS, no debug routes, secrets required."""

    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"
    ENABLE_HSTS = True
    ENABLE_DEBUG_ROUTES = False

    @staticmethod
    def validate(config: Mapping[str, Any]) -> None:
        """Refuse to start with an incomplete or unsafe production configuration.

        Args:
            config: The final application configuration (class values plus overrides).

        Raises:
            RuntimeError: Listing every problem found, so they can be fixed at once.
        """
        problems: list[str] = []
        secret = config.get("SECRET_KEY") or ""
        if len(secret) < MIN_SECRET_KEY_LENGTH:
            problems.append(f"SECRET_KEY must have at least {MIN_SECRET_KEY_LENGTH} characters")
        if not config.get("SQLALCHEMY_DATABASE_URI"):
            problems.append("DATABASE_URL must be set")
        if config.get("DEBUG"):
            problems.append("DEBUG must be false")
        if config.get("ENABLE_DEBUG_ROUTES"):
            problems.append("ENABLE_DEBUG_ROUTES must be false")
        if config.get("MAIL_BACKEND") != "smtp":
            problems.append("MAIL_BACKEND must be smtp (password recovery needs email)")
        elif not config.get("MAIL_SERVER") or not config.get("MAIL_FROM"):
            problems.append("MAIL_SERVER and MAIL_FROM must be set")
        if config.get("PAYWALL_ENABLED"):
            if config.get("BILLING_BACKEND") != "stripe":
                problems.append(
                    "BILLING_BACKEND must be stripe while PAYWALL_ENABLED (the simulated "
                    "checkout would give Pro away)"
                )
            else:
                for key in (
                    "STRIPE_SECRET_KEY",
                    "STRIPE_WEBHOOK_SECRET",
                    "STRIPE_PRICE_MONTHLY",
                    "STRIPE_PRICE_YEARLY",
                ):
                    if not config.get(key):
                        problems.append(f"{key} must be set")
        if problems:
            raise RuntimeError("Invalid production configuration: " + "; ".join(problems))


CONFIGS: dict[str, type[BaseConfig]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
