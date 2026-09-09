"""Routes that only exist to exercise error handling, by hand and in tests.

Mounted under ``/_debug`` when ``ENABLE_DEBUG_ROUTES`` is true (development and
testing). Production refuses to start with that flag on (see ``config.py``).
"""

from __future__ import annotations

from typing import NoReturn

from flask import Blueprint, abort, render_template
from flask_wtf import FlaskForm
from werkzeug.exceptions import default_exceptions
from wtforms import StringField
from wtforms.validators import DataRequired, Length

from app.extensions import limiter

bp = Blueprint("debug", __name__)

MESSAGE_MAX_LENGTH = 200


class EchoForm(FlaskForm):
    """Minimal form used to verify CSRF protection end to end."""

    message = StringField("Mensaje", validators=[DataRequired(), Length(max=MESSAGE_MAX_LENGTH)])


@bp.get("/boom")
def boom() -> NoReturn:
    """Raise an unhandled exception on purpose (verifies the 500 page and the log)."""
    raise RuntimeError("Deliberate failure from /_debug/boom")


@bp.route("/echo", methods=["GET", "POST"])
def echo() -> str:
    """Echo a posted message; posting without a CSRF token must fail with 400."""
    form = EchoForm()
    echoed = form.message.data if form.validate_on_submit() else None
    return render_template("debug/echo.html", form=form, echoed=echoed)


@bp.get("/limited")
@limiter.limit("2 per minute")
def limited() -> str:
    """Allow two requests per minute, then answer 429."""
    return "ok"


@bp.get("/abort/<int:code>")
def abort_with(code: int) -> NoReturn:
    """Abort with a known HTTP status code (verifies the generic error page)."""
    if code not in default_exceptions:
        abort(404)
    abort(code)
