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
    url_for,
)
from flask_babel import get_locale
from flask_babel import gettext as _
from werkzeug.wrappers import Response as WerkzeugResponse

from app.security import safe_redirect_target

bp = Blueprint("main", __name__)

THEMES = ("dark", "light")


@bp.get("/")
def index() -> str:
    """Landing page."""
    return render_template("main/index.html")


@bp.get("/favicon.ico")
def favicon() -> Response:
    """Los navegadores piden /favicon.ico aunque la página declare otro icono."""
    return current_app.send_static_file("img/favicon.ico")


@bp.get("/manifest.webmanifest")
def manifest() -> Response:
    """Lo que hace instalable la app: nombre, colores, iconos y por dónde empieza."""
    icon = lambda name, size, purpose="any": {  # noqa: E731 - tiny local helper
        "src": url_for("static", filename=f"img/{name}"),
        "sizes": size,
        "type": "image/png",
        "purpose": purpose,
    }
    data = {
        "name": current_app.config["APP_NAME"],
        "short_name": current_app.config["APP_NAME"],
        "description": str(_("Tu plan de entrenamiento y nutrición, calculado y no inventado.")),
        "lang": str(get_locale() or "es"),
        "start_url": url_for("dashboard.index"),
        "scope": "/",
        "display": "standalone",
        "background_color": "#0e1013",
        "theme_color": "#0e1013",
        "icons": [
            icon("icon-192.png", "192x192"),
            icon("icon-512.png", "512x512"),
            icon("icon-maskable-512.png", "512x512", "maskable"),
        ],
    }
    response = jsonify(data)
    response.mimetype = "application/manifest+json"
    return response


@bp.get("/sw.js")
def service_worker() -> Response:
    """El service worker se sirve desde la raíz: así su alcance es toda la app."""
    response = current_app.send_static_file("js/sw.js")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@bp.get("/acerca")
def about() -> str:
    """What Alza is, its limits, and the open projects it relies on (with their licences)."""
    return render_template("main/about.html")


@bp.get("/sin-conexion")
def offline() -> str:
    """Lo que enseña el service worker cuando no hay red ni copia guardada."""
    return render_template("main/offline.html")


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
