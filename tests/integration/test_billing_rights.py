"""Consumer rights: clear prices, one-click cancel, 14-day withdrawal and events out of order."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.models import Subscription
from app.services.billing.stripe_gateway import StripeGateway
from tests.integration.test_billing import _row, _subscribe
from tests.integration.test_stripe_gateway import CONFIG, Recorder, _post_event, _subscription_event
from tests.integration.test_workout_flow import _with_routine


@pytest.fixture
def paywall(app: Flask) -> Flask:
    app.config["PAYWALL_ENABLED"] = True
    return app


def test_prices_say_vat_renewal_cancellation_and_withdrawal(
    client: FlaskClient, paywall: Flask
) -> None:
    html = client.get("/precios").get_data(as_text=True)
    assert "IVA incluido." in html
    assert "Renovación automática." in html
    assert "Cancelar es un clic." in html
    assert "Derecho de desistimiento." in html
    assert "14 días naturales" in html
    assert "Los días de prueba cuentan dentro de esos 14" in html


def test_cancel_and_resume_are_one_click_each(
    client: FlaskClient, seeded: SQLAlchemy, paywall: Flask
) -> None:
    _with_routine(client)
    _subscribe(client)
    page = client.get("/suscripcion").get_data(as_text=True)
    assert "Cancelar la suscripción" in page
    client.post("/suscripcion/cancelar")
    assert _row(seeded).cancel_at_period_end is True
    assert _row(seeded).is_active  # sigue con Pro hasta el final
    assert "Reanudar la suscripción" in client.get("/suscripcion").get_data(as_text=True)
    client.post("/suscripcion/reanudar")
    assert _row(seeded).cancel_at_period_end is False


def test_withdrawal_within_14_days_ends_now(
    client: FlaskClient, seeded: SQLAlchemy, paywall: Flask
) -> None:
    _with_routine(client)
    _subscribe(client)
    assert _row(seeded).started_at is not None
    assert "Desistir y recuperar lo pagado" in client.get("/suscripcion").get_data(as_text=True)
    client.post("/suscripcion/desistir")
    assert _row(seeded).status == "canceled"
    assert "pro-teaser" in client.get("/panel").get_data(as_text=True)


def test_after_14_days_there_is_no_withdrawal(
    client: FlaskClient, seeded: SQLAlchemy, paywall: Flask
) -> None:
    _with_routine(client)
    _subscribe(client)
    row = _row(seeded)
    row.started_at = datetime.now(UTC) - timedelta(days=15)
    seeded.session.commit()
    assert "Desistir" not in client.get("/suscripcion").get_data(as_text=True)
    response = client.post("/suscripcion/desistir", follow_redirects=True)
    assert "El plazo de 14 días para desistir ha terminado." in response.get_data(as_text=True)
    assert _row(seeded).is_active


def test_an_older_event_arriving_late_does_not_win(
    client: FlaskClient, seeded: SQLAlchemy, app: Flask
) -> None:
    app.config.update(CONFIG, BILLING_BACKEND="stripe", PAYWALL_ENABLED=True)
    _with_routine(client)
    user_id = 1
    now = int(time.time())
    newer = _subscription_event(user_id, "evt_new", "canceled")
    newer["type"] = "customer.subscription.deleted"
    newer["created"] = now
    older = _subscription_event(user_id, "evt_old", "active")
    older["created"] = now - 60
    _post_event(client, newer)
    response = _post_event(client, older)  # llega después pero es de antes
    assert response.status_code == 200
    row = seeded.session.scalar(select(Subscription))
    assert row is not None
    assert row.status == "canceled"


def test_stripe_withdrawal_refunds_the_last_payment_then_cancels(
    seeded: SQLAlchemy, app: Flask
) -> None:
    del seeded
    calls: list[tuple[str, str]] = []
    answers = {
        "GET": {"data": [{"amount_paid": 4999, "payment_intent": "pi_123"}]},
        "POST": {"id": "re_1"},
        "DELETE": {"id": "sub_9", "status": "canceled", "customer": "cus_9", "metadata": {}},
    }

    def transport(method, url, fields, headers):  # type: ignore[no-untyped-def]
        del fields, headers
        calls.append((method, url))
        return answers[method]

    row = Subscription(customer_id="cus_9", subscription_id="sub_9", status="active")
    with app.test_request_context():
        StripeGateway(CONFIG, transport=transport).withdraw(row)
    assert calls[0][0] == "GET"
    assert "subscription=sub_9" in calls[0][1]
    assert calls[1] == ("POST", "https://api.stripe.com/v1/refunds")
    assert calls[2] == ("DELETE", "https://api.stripe.com/v1/subscriptions/sub_9")


def test_stripe_cancel_sets_cancel_at_period_end(seeded: SQLAlchemy, app: Flask) -> None:
    del seeded
    recorder = Recorder({"id": "sub_9", "status": "active", "cancel_at_period_end": True})
    row = Subscription(customer_id="cus_9", subscription_id="sub_9", status="active")
    with app.test_request_context():
        StripeGateway(CONFIG, transport=recorder).set_cancel_at_period_end(row, True)
    method, url, fields, _headers = recorder.calls[0]
    assert (method, url) == ("POST", "https://api.stripe.com/v1/subscriptions/sub_9")
    assert fields == {"cancel_at_period_end": "true"}


def test_health_notices_where_calories_are_set_or_changed(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    for path in ("/nutricion", "/cuestionario/resultado"):
        html = client.get(path).get_data(as_text=True)
        assert "no sustituyen a un médico ni a un dietista-nutricionista" in html, path
    review = client.get("/revision").get_data(as_text=True)
    assert "no sustituye a un profesional sanitario" in review


def test_open_food_facts_is_credited(client: FlaskClient, seeded: SQLAlchemy) -> None:
    about = client.get("/acerca").get_data(as_text=True)
    assert "Open Food Facts" in about
    assert "Open Database License (ODbL)" in about
    assert "wger" in about
    assert 'href="/acerca"' in client.get("/").get_data(as_text=True)
    _with_routine(client)
    foods = client.get("/diario/alimentos").get_data(as_text=True)
    assert "Open Food Facts" in foods
    assert "ODbL" in foods


def test_barcode_entry_is_visible_where_scanning_is_not_possible(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    html = client.get("/diario/alimentos").get_data(as_text=True)
    assert 'class="field-label barcode-label"' in html
    assert "data-no-scan" in html
    assert "hace falta una conexión segura" in html
    assert "zxing-browser-0.2.1.min.js" in html
    assert 'inputmode="numeric"' in html


def test_the_zxing_fallback_is_served_locally(client: FlaskClient) -> None:
    """Plan B for iPhone: same origin (the CSP allows nothing else) and only on demand."""
    response = client.get("/static/vendor/zxing-browser-0.2.1.min.js")
    assert response.status_code == 200
    assert b"BrowserMultiFormatReader" in response.data
    assert client.get("/static/vendor/LICENSE-zxing-browser.txt").status_code == 200
    assert "zxing" not in client.get("/").get_data(as_text=True)  # no pesa en otras páginas
