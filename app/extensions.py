"""Flask extension instances, created once and bound to the app in ``create_app``.

Keeping them here (instead of inside the factory) lets models, blueprints and
services import ``db``, ``limiter``... without importing the factory.
"""

from __future__ import annotations

from flask_babel import Babel
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base shared by every model (SQLAlchemy 2.0 typed style)."""


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
csrf = CSRFProtect()
login_manager = LoginManager()
limiter = Limiter(key_func=get_remote_address)
babel = Babel()
