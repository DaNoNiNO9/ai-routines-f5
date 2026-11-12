"""Structured logging.

The application logger (``app``) gets a readable stream handler on stderr and,
when ``LOG_TO_FILE`` is on, a rotating file handler that writes one JSON object
per line to ``LOG_DIR/alza.log``. Every record carries the request id, method,
path and remote address when emitted inside a request. Module loggers created
with ``logging.getLogger(__name__)`` under the ``app`` package propagate here.

Requests are logged by a dedicated ``app.request`` logger that only writes to
the JSON file, so the console keeps the Werkzeug access log without duplicates.
"""

from __future__ import annotations

import logging
import sys
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, Response, g, has_request_context, request
from pythonjsonlogger.json import JsonFormatter

LOG_FILENAME = "alza.log"
CONSOLE_FORMAT = "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s"
JSON_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s %(message)s "
    "%(request_id)s %(method)s %(path)s %(remote_addr)s"
)
REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_LENGTH = 12
MAX_INCOMING_REQUEST_ID = 64
REQUEST_LOGGER_NAME = "app.request"


class RequestContextFilter(logging.Filter):
    """Inject request metadata into every record (dashes outside a request)."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Always keep the record; only annotate it."""
        if has_request_context():
            record.request_id = getattr(g, "request_id", "-")
            record.method = request.method
            record.path = request.path
            record.remote_addr = request.remote_addr or "-"
        else:
            record.request_id = "-"
            record.method = "-"
            record.path = "-"
            record.remote_addr = "-"
        return True


def resolve_level(name: str) -> int:
    """Translate a level name such as ``"INFO"`` into its numeric value.

    Raises:
        ValueError: If the name is not a standard logging level.
    """
    try:
        return logging.getLevelNamesMapping()[name.upper()]
    except KeyError as exc:
        raise ValueError(f"Unknown LOG_LEVEL {name!r}") from exc


def configure_logging(app: Flask) -> None:
    """Replace the default Flask handler with the console and JSON file handlers."""
    logger = app.logger
    logger.handlers.clear()
    logger.setLevel(resolve_level(app.config["LOG_LEVEL"]))
    context_filter = RequestContextFilter()

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter(CONSOLE_FORMAT))
    console.addFilter(context_filter)
    logger.addHandler(console)

    request_logger = logging.getLogger(REQUEST_LOGGER_NAME)
    request_logger.handlers.clear()
    request_logger.propagate = False
    request_logger.setLevel(logging.INFO)

    if app.config["LOG_TO_FILE"]:
        file_handler = _build_file_handler(app, context_filter)
        logger.addHandler(file_handler)
        request_logger.addHandler(file_handler)
    else:
        request_logger.addHandler(logging.NullHandler())

    app.before_request(_assign_request_id)
    app.after_request(_log_request)


def _build_file_handler(app: Flask, context_filter: logging.Filter) -> logging.Handler:
    log_dir = Path(app.config["LOG_DIR"])
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / LOG_FILENAME,
        maxBytes=app.config["LOG_MAX_BYTES"],
        backupCount=app.config["LOG_BACKUP_COUNT"],
        encoding="utf-8",
    )
    handler.setFormatter(
        JsonFormatter(JSON_FORMAT, rename_fields={"asctime": "timestamp", "levelname": "level"})
    )
    handler.addFilter(context_filter)
    return handler


def _assign_request_id() -> None:
    incoming = request.headers.get(REQUEST_ID_HEADER, "").strip()
    if incoming:
        g.request_id = incoming[:MAX_INCOMING_REQUEST_ID]
    else:
        g.request_id = uuid.uuid4().hex[:REQUEST_ID_LENGTH]


def _log_request(response: Response) -> Response:
    if request.endpoint != "static":
        logging.getLogger(REQUEST_LOGGER_NAME).info(
            "%s %s -> %s", request.method, request.full_path.rstrip("?"), response.status_code
        )
    response.headers.setdefault(REQUEST_ID_HEADER, g.get("request_id", "-"))
    return response
