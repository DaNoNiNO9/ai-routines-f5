"""Global error handling.

Every HTTP error (404, 405, 429, 500...) and every CSRF failure renders the same
``errors/error.html`` template with a code-specific title and message, or a JSON
body when the client is an API consumer (``/api/`` paths, or ``Accept:
application/json`` without HTML). Unhandled exceptions are logged with their
traceback by Flask (``app.logger``) before the 500 handler runs, so they end up
in the JSON log file with the request id.
"""

from __future__ import annotations

import logging

from flask import Flask, Response, g, jsonify, make_response, render_template, request
from flask_babel import lazy_gettext as _l
from flask_babel.speaklater import LazyString
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)

API_PREFIX = "/api/"
FORWARDED_HEADERS = ("Allow", "Retry-After", "WWW-Authenticate")

ERROR_TEXTS: dict[int, tuple[LazyString, LazyString]] = {
    400: (
        _l("Petición incorrecta"),
        _l("El servidor no ha podido procesar la petición."),
    ),
    403: (
        _l("Acceso denegado"),
        _l("No tienes permiso para ver esta página."),
    ),
    404: (
        _l("Página no encontrada"),
        _l("La dirección no existe o ha cambiado."),
    ),
    405: (
        _l("Método no permitido"),
        _l("Esta acción no está disponible en esta dirección."),
    ),
    429: (
        _l("Demasiadas peticiones"),
        _l("Has hecho demasiadas peticiones seguidas. Espera un momento y vuelve a intentarlo."),
    ),
    500: (
        _l("Error interno"),
        _l(
            "Algo ha fallado en el servidor. El error ha quedado registrado; "
            "inténtalo de nuevo en unos minutos."
        ),
    ),
}


def register_error_handlers(app: Flask) -> None:
    """Attach the CSRF and HTTP exception handlers to the application."""
    app.register_error_handler(CSRFError, _handle_csrf_error)
    app.register_error_handler(HTTPException, _handle_http_exception)


def _handle_csrf_error(error: CSRFError) -> tuple[Response, int]:
    logger.warning("CSRF validation failed: %s", error.description)
    title = _l("Sesión caducada o formulario no válido")
    message = _l(
        "Recarga la página y vuelve a enviar el formulario. "
        "Si sigue fallando, inicia sesión de nuevo."
    )
    return _respond(error.code or 400, title, message)


def _handle_http_exception(error: HTTPException) -> tuple[Response, int]:
    code = error.code or 500
    if code >= 500:
        logger.error("HTTP %s on %s %s: %s", code, request.method, request.path, error.description)
    elif code == 404:
        logger.info("HTTP 404 on %s %s", request.method, request.path)
    else:
        logger.warning(
            "HTTP %s on %s %s: %s", code, request.method, request.path, error.description
        )

    title, message = ERROR_TEXTS.get(code, ERROR_TEXTS[500])
    response, status = _respond(code, title, message)
    for name, value in error.get_headers(request.environ):
        if name in FORWARDED_HEADERS:
            response.headers[name] = value
    return response, status


def _wants_json() -> bool:
    if request.path.startswith(API_PREFIX):
        return True
    accept = request.accept_mimetypes
    return accept.accept_json and not accept.accept_html


def _respond(code: int, title: LazyString, message: LazyString) -> tuple[Response, int]:
    request_id = g.get("request_id", "-")
    if _wants_json():
        payload = {
            "error": {
                "code": code,
                "title": str(title),
                "message": str(message),
                "request_id": request_id,
            }
        }
        return jsonify(payload), code
    html = render_template(
        "errors/error.html", code=code, title=title, message=message, request_id=request_id
    )
    return make_response(html), code
