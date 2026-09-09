"""Locale selection for Flask-Babel.

Order of precedence: explicit ``?lang=`` query parameter (remembered in the
session), the value stored in the session, the Accept-Language header sent by
the browser, and finally the default locale (Spanish).
"""

from __future__ import annotations

from flask import current_app, has_app_context, has_request_context, request, session
from flask_babel import gettext
from flask_login import current_user

LANG_QUERY_PARAM = "lang"
LANG_SESSION_KEY = "lang"


def select_locale() -> str:
    """Return the locale code to use for the current request."""
    default: str = current_app.config["BABEL_DEFAULT_LOCALE"]
    if not has_request_context():
        return default
    languages: list[str] = list(current_app.config["LANGUAGES"])

    requested = request.args.get(LANG_QUERY_PARAM)
    if requested in languages:
        session[LANG_SESSION_KEY] = requested
        return requested

    stored = session.get(LANG_SESSION_KEY)
    if stored in languages:
        return stored

    # Lo que la persona eligió en su cuenta manda sobre el navegador.
    if current_user.is_authenticated and current_user.locale in languages:
        return str(current_user.locale)

    return request.accept_languages.best_match(languages, default=default) or default


def translate_engine_message(text: str) -> str:
    """Translate an engine template, or leave it as written outside a request.

    The engine renders notes from scripts and tests too, where there is no
    application to ask; there the Spanish reference wording is the answer.
    """
    if not has_app_context():
        return text
    return gettext(text)
