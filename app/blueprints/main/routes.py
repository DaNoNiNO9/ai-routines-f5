"""Public pages: landing and health check."""

from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify, render_template

bp = Blueprint("main", __name__)


@bp.get("/")
def index() -> str:
    """Landing page."""
    return render_template("main/index.html")


@bp.get("/health")
def health() -> Response:
    """Liveness probe: JSON with status, version and environment name."""
    return jsonify(
        status="ok",
        version=current_app.config["APP_VERSION"],
        env=current_app.config["ENV_NAME"],
    )
