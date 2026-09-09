"""Forja (working title: AI Routines F5): application factory.

Phase 0 skeleton. Per-environment configuration, structured logging, global
error handling and blueprints arrive in Phase 1.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from flask import Flask, Response, jsonify

__version__ = "0.0.1"


def create_app(test_config: Mapping[str, Any] | None = None) -> Flask:
    """Build and return the Flask application.

    Args:
        test_config: Optional mapping that overrides the default configuration.
            The test suite passes ``{"TESTING": True}``.

    Returns:
        A configured :class:`flask.Flask` instance.
    """
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(APP_NAME="Forja")
    if test_config is not None:
        app.config.from_mapping(test_config)

    @app.get("/")
    def index() -> str:
        return f"{app.config['APP_NAME']}: Fase 0 operativa."

    @app.get("/health")
    def health() -> Response:
        return jsonify(status="ok", version=__version__)

    return app
