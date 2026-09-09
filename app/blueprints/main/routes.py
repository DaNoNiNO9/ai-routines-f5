"""Public pages: landing and health check."""

from __future__ import annotations

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
)
from werkzeug.wrappers import Response as WerkzeugResponse

from app.security import safe_redirect_target

bp = Blueprint("main", __name__)

THEMES = ("dark", "light")


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


@bp.post("/tema")
def toggle_theme() -> WerkzeugResponse:
    """Switch between the dark and light themes (kept in the session, no JS needed)."""
    session["theme"] = THEMES[1] if session.get("theme", THEMES[0]) == THEMES[0] else THEMES[0]
    return redirect(safe_redirect_target(request.form.get("next"), "main.index"))
