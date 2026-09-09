"""Locale selection for Flask-Babel.

Order of precedence: explicit ``?lang=`` query parameter (remembered in the
session), the value stored in the session, the Accept-Language header sent by
the browser, and finally the default locale (Spanish).
"""

from __future__ import annotations

from flask import current_app, has_request_context, request, session

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

    return request.accept_languages.best_match(languages, default=default) or default
