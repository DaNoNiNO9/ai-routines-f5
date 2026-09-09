"""Outgoing email.

``MAIL_BACKEND`` selects the transport: ``log`` (development and tests: the
message is logged and kept in ``app.extensions["outbox"]`` so tests can read
it) or ``smtp`` (production, plain ``smtplib`` with STARTTLS). Delivery
failures are logged with their traceback and raised as
:class:`EmailDeliveryError` so the caller can show a useful message.
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from flask import current_app

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 10


class EmailDeliveryError(RuntimeError):
    """The message could not be handed to the mail server."""


@dataclass(frozen=True)
class Message:
    """A plain-text email."""

    to: str
    subject: str
    body: str


def send_email(to: str, subject: str, body: str) -> None:
    """Deliver a plain-text message through the configured backend."""
    backend = current_app.config["MAIL_BACKEND"]
    message = Message(to=to, subject=subject, body=body)
    if backend == "log":
        outbox: list[Message] = current_app.extensions.setdefault("outbox", [])
        outbox.append(message)
        # The whole body goes to the log so the reset link can be followed in
        # development; production refuses to start with this backend.
        logger.info("Email (log backend) to %s: %s\n%s", to, subject, body)
        return
    if backend == "smtp":
        _send_smtp(message)
        return
    raise EmailDeliveryError(f"Unknown MAIL_BACKEND {backend!r}")


def _send_smtp(message: Message) -> None:
    config = current_app.config
    email = EmailMessage()
    email["From"] = config["MAIL_FROM"]
    email["To"] = message.to
    email["Subject"] = message.subject
    email.set_content(message.body)
    try:
        with smtplib.SMTP(
            config["MAIL_SERVER"], int(config["MAIL_PORT"]), timeout=SMTP_TIMEOUT_SECONDS
        ) as smtp:
            if config["MAIL_USE_TLS"]:
                smtp.starttls()
            if config["MAIL_USERNAME"]:
                smtp.login(config["MAIL_USERNAME"], config["MAIL_PASSWORD"])
            smtp.send_message(email)
    except (smtplib.SMTPException, OSError) as exc:
        logger.exception("SMTP delivery to %s failed", message.to)
        raise EmailDeliveryError(str(exc)) from exc
    logger.info("Email sent to %s: %s", message.to, message.subject)
