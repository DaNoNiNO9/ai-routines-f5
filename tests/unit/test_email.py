"""Email backends: log outbox and SMTP delivery."""

from __future__ import annotations

import logging
import smtplib
from typing import Any

import pytest
from flask import Flask

from app import email as email_module
from app.email import EmailDeliveryError, send_email


def test_log_backend_keeps_messages_in_the_outbox(
    app: Flask, caplog: pytest.LogCaptureFixture
) -> None:
    with app.app_context(), caplog.at_level(logging.INFO, logger="app.email"):
        send_email("ana@example.com", "Hola", "Cuerpo con http://enlace")
        outbox = app.extensions["outbox"]
    assert len(outbox) == 1
    assert outbox[0].to == "ana@example.com"
    assert outbox[0].subject == "Hola"
    # The body (with the reset link) must be readable in the development log.
    assert "Cuerpo con http://enlace" in caplog.text


class FakeSMTP:
    """Records the calls a real SMTP client would receive."""

    instances: list[FakeSMTP] = []
    fail_on_send = False

    def __init__(self, server: str, port: int, timeout: int) -> None:
        self.server = server
        self.port = port
        self.timeout = timeout
        self.calls: list[tuple[str, Any]] = []
        FakeSMTP.instances.append(self)

    def __enter__(self) -> FakeSMTP:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def starttls(self) -> None:
        self.calls.append(("starttls", None))

    def login(self, username: str, password: str) -> None:
        self.calls.append(("login", (username, password)))

    def send_message(self, message: Any) -> None:
        if FakeSMTP.fail_on_send:
            raise smtplib.SMTPException("boom")
        self.calls.append(("send", message["To"]))


def test_smtp_backend_delivers(app: Flask, monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSMTP.instances.clear()
    FakeSMTP.fail_on_send = False
    monkeypatch.setattr(email_module.smtplib, "SMTP", FakeSMTP)
    app.config.update(
        MAIL_BACKEND="smtp",
        MAIL_SERVER="smtp.example.com",
        MAIL_PORT=587,
        MAIL_USE_TLS=True,
        MAIL_USERNAME="user",
        MAIL_PASSWORD="secret",
        MAIL_FROM="Forja <no-reply@example.com>",
    )
    with app.app_context():
        send_email("ana@example.com", "Hola", "Cuerpo")
    client = FakeSMTP.instances[-1]
    assert (client.server, client.port) == ("smtp.example.com", 587)
    assert [name for name, _ in client.calls] == ["starttls", "login", "send"]


def test_smtp_failure_is_wrapped(app: Flask, monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSMTP.fail_on_send = True
    monkeypatch.setattr(email_module.smtplib, "SMTP", FakeSMTP)
    app.config.update(MAIL_BACKEND="smtp", MAIL_SERVER="smtp.example.com", MAIL_USE_TLS=False)
    with app.app_context(), pytest.raises(EmailDeliveryError, match="boom"):
        send_email("ana@example.com", "Hola", "Cuerpo")
    FakeSMTP.fail_on_send = False


def test_unknown_backend_is_an_error(app: Flask) -> None:
    app.config["MAIL_BACKEND"] = "pigeon"
    with app.app_context(), pytest.raises(EmailDeliveryError, match="pigeon"):
        send_email("ana@example.com", "Hola", "Cuerpo")
