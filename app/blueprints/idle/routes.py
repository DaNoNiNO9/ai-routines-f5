"""Closing idle sessions on the web, without ever getting in the way on the phone.

Rules (``IDLE_TIMEOUT_MINUTES``, two hours by default):

- In a browser, a session with no request for that long is closed: the next
  page (a reload, a click) leads to the login with an explanation. Two minutes
  before, a dialog offers to stay signed in.
- Phones and tablets (``Sec-CH-UA-Mobile: ?1`` or a mobile user agent),
  where the app is installed and used in the gym, and whoever ticked «Mantener
  la sesión iniciada» (the remember cookie) are never closed for being idle:
  that is what people expect there. (A cookie set by the installed app would
  not do: on Android it shares cookies with the browser.)
- A workout in progress never closes the session halfway, whatever the device:
  sets queued without signal would be lost.

Every request counts as activity except ``/sesion/estado``, which the dialog
asks to know how long is left without resetting the clock.
"""

from __future__ import annotations

import re
import time
from datetime import timedelta

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    request,
    session,
    url_for,
)
from flask_babel import gettext as _
from flask_login import current_user, logout_user
from sqlalchemy import select
from werkzeug.wrappers import Response as WerkzeugResponse

from app.engine.enums import WorkoutStatus
from app.extensions import db
from app.models import WorkoutSession
from app.models.base import utcnow

bp = Blueprint("idle", __name__)

LAST_SEEN_KEY = "last_seen"
MOBILE_UA = re.compile(r"Mobi|Android|iPhone|iPod|iPad", re.IGNORECASE)
# Un entreno que lleva abierto más que esto ya no se está haciendo.
WORKOUT_SHIELD = timedelta(hours=6)
# Peticiones que no cuentan como actividad ni se cortan.
PASSIVE_ENDPOINTS = frozenset(
    {
        "static",
        "idle.status",
        "idle.expired",
        "main.health",
        "main.manifest",
        "main.service_worker",
        "main.favicon",
    }
)


def _timeout_seconds() -> int:
    return int(current_app.config.get("IDLE_TIMEOUT_MINUTES", 120)) * 60


def _training_now() -> bool:
    started = db.session.scalar(
        select(WorkoutSession.started_at)
        .where(
            WorkoutSession.user_id == current_user.id,
            WorkoutSession.status == WorkoutStatus.IN_PROGRESS,
        )
        .order_by(WorkoutSession.started_at.desc())
        .limit(1)
    )
    return started is not None and utcnow() - started < WORKOUT_SHIELD


def _on_a_phone() -> bool:
    if request.headers.get("Sec-CH-UA-Mobile") == "?1":
        return True
    return bool(MOBILE_UA.search(request.headers.get("User-Agent", "")))


def idle_applies() -> bool:
    """Whether this session can be closed for being idle (a computer, without «remember me»)."""
    if not current_user.is_authenticated or _timeout_seconds() <= 0:
        return False
    if _on_a_phone():
        return False
    remember = current_app.config.get("REMEMBER_COOKIE_NAME", "remember_token")
    if request.cookies.get(remember) or session.get("_remember") == "set":
        return False
    return not _training_now()


def _close(reason_next: str | None) -> WerkzeugResponse:
    logout_user()
    session.pop(LAST_SEEN_KEY, None)
    flash(_("Tu sesión se cerró tras un rato sin actividad. Vuelve a entrar para seguir."), "info")
    response = redirect(
        url_for("auth.login", next=reason_next) if reason_next else url_for("auth.login")
    )
    # Lo que la app guardó en este navegador para usarla sin red, fuera también.
    response.headers["Clear-Site-Data"] = '"cache", "storage"'
    return response


@bp.before_app_request
def _check_idle() -> WerkzeugResponse | None:
    """Close an idle web session; otherwise note this request as activity."""
    endpoint = request.endpoint or ""
    if endpoint in PASSIVE_ENDPOINTS or not current_user.is_authenticated:
        return None
    now = int(time.time())
    last = session.get(LAST_SEEN_KEY)
    if isinstance(last, int) and now - last > _timeout_seconds() and idle_applies():
        safe_next = request.full_path if request.method == "GET" else None
        return _close(safe_next.rstrip("?") if safe_next else None)
    session[LAST_SEEN_KEY] = now
    g.idle_timeout = _timeout_seconds() if idle_applies() else None
    return None


@bp.get("/sesion/estado")
def status() -> Response:
    """Seconds left before an idle close (without counting as activity)."""
    if not current_user.is_authenticated:
        return jsonify(signed_in=False, remaining=0)
    if not idle_applies():
        return jsonify(signed_in=True, remaining=None)
    last = session.get(LAST_SEEN_KEY)
    elapsed = int(time.time()) - last if isinstance(last, int) else 0
    return jsonify(signed_in=True, remaining=max(0, _timeout_seconds() - elapsed))


@bp.post("/sesion/seguir")
def keep_alive() -> Response:
    """«Seguir conectado»: the request itself already counted as activity."""
    return jsonify(signed_in=current_user.is_authenticated, remaining=_timeout_seconds())


@bp.get("/sesion/caducada")
def expired() -> WerkzeugResponse:
    """Where the dialog sends an unattended page when the time is up."""
    if current_user.is_authenticated:
        last = session.get(LAST_SEEN_KEY)
        elapsed = int(time.time()) - last if isinstance(last, int) else 0
        if idle_applies() and elapsed >= _timeout_seconds() - 5:
            return _close(None)
        return redirect(url_for("dashboard.index"))  # otra pestaña seguía activa
    return redirect(url_for("auth.login"))
