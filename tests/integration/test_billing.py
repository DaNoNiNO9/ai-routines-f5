"""Pro subscription with the simulated gateway: prices, checkout, trial, portal and paywall."""

from __future__ import annotations

import re

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.models import BillingEvent, Subscription, User
from tests.integration.test_workout_flow import _with_routine


@pytest.fixture
def paywall(app: Flask) -> Flask:
    app.config["PAYWALL_ENABLED"] = True
    return app


def _checkout(client: FlaskClient, plan: str = "yearly") -> str:
    response = client.post("/suscripcion/empezar", data={"plan": plan})
    assert response.status_code == 303
    location = response.headers["Location"]
    assert "/suscripcion/simulada/pago/" in location
    return location


def _subscribe(client: FlaskClient, plan: str = "yearly") -> None:
    paid = client.post(_checkout(client, plan), data={"outcome": "pay"})
    assert paid.status_code == 302
    assert paid.headers["Location"].endswith("/suscripcion/hecho")


def _row(seeded: SQLAlchemy) -> Subscription:
    row = seeded.session.scalar(select(Subscription))
    assert row is not None
    seeded.session.refresh(row)
    return row


def test_prices_are_public_and_honest(client: FlaskClient, paywall: Flask) -> None:
    html = client.get("/precios").get_data(as_text=True)
    assert "7,99" in html
    assert "49,99" in html
    assert "7 días gratis" in html
    assert "Ahorras un 48 %" in html
    assert "Modo de pruebas" in html  # pasarela simulada: se dice
    assert "Crear cuenta y probar" in html  # sin sesión


def test_without_pro_the_arrival_card_is_a_teaser(
    client: FlaskClient, seeded: SQLAlchemy, paywall: Flask
) -> None:
    _with_routine(client)
    html = client.get("/panel").get_data(as_text=True)
    assert "pro-teaser" in html
    assert "Probar Pro gratis" in html
    assert "A este ritmo llegas" not in html
    assert "Si sigues el plan, llegas" not in html


def test_the_simulated_checkout_starts_the_trial(
    client: FlaskClient, seeded: SQLAlchemy, paywall: Flask
) -> None:
    _with_routine(client)
    page = client.get(_checkout(client)).get_data(as_text=True)
    assert "no se pide tarjeta ni se cobra nada" in page
    _subscribe(client)
    row = _row(seeded)
    assert row.status == "trialing"
    assert row.plan == "yearly"
    assert row.customer_id.startswith("cus_fake_")
    assert row.trial_ends_at is not None
    done = client.get("/suscripcion/hecho").get_data(as_text=True)
    assert "¡Ya tienes Alza Pro!" in done
    html = client.get("/panel").get_data(as_text=True)
    assert "pro-teaser" not in html
    assert "Si sigues el plan, llegas" in html
    assert "Prueba gratis" in client.get("/suscripcion").get_data(as_text=True)
    # Dos eventos aplicados, como los mandaría Stripe.
    assert len(seeded.session.scalars(select(BillingEvent)).all()) == 2


def test_a_declined_card_charges_nothing(
    client: FlaskClient, seeded: SQLAlchemy, paywall: Flask
) -> None:
    _with_routine(client)
    response = client.post(_checkout(client), data={"outcome": "decline"}, follow_redirects=True)
    assert "rechazada" in response.get_data(as_text=True)
    assert seeded.session.scalar(select(Subscription)) is None


def test_the_portal_cancels_resumes_switches_and_ends(
    client: FlaskClient, seeded: SQLAlchemy, paywall: Flask
) -> None:
    _with_routine(client)
    _subscribe(client, "monthly")
    portal = client.post("/suscripcion/gestionar")
    assert portal.headers["Location"].endswith("/suscripcion/simulada/portal")
    client.post("/suscripcion/simulada/portal", data={"action": "cancel"})
    assert _row(seeded).cancel_at_period_end is True
    assert "no se te cobrará nada" in client.get("/suscripcion").get_data(as_text=True)
    client.post("/suscripcion/simulada/portal", data={"action": "resume"})
    assert _row(seeded).cancel_at_period_end is False
    client.post("/suscripcion/simulada/portal", data={"action": "switch", "plan": "yearly"})
    assert _row(seeded).plan == "yearly"
    client.post("/suscripcion/simulada/portal", data={"action": "fail"})
    assert _row(seeded).status == "past_due"
    assert _row(seeded).is_active  # Stripe reintenta: se mantiene el acceso
    client.post("/suscripcion/simulada/portal", data={"action": "end"})
    assert _row(seeded).status == "canceled"
    html = client.get("/panel").get_data(as_text=True)
    assert "pro-teaser" in html


def test_no_second_trial(client: FlaskClient, seeded: SQLAlchemy, paywall: Flask) -> None:
    _with_routine(client)
    _subscribe(client)
    client.post("/suscripcion/gestionar")
    client.post("/suscripcion/simulada/portal", data={"action": "end"})
    page = client.get(_checkout(client)).get_data(as_text=True)
    assert "gratis" not in page.split("price-amount", 1)[1].split("</form>", 1)[0]
    assert "Volver a Pro" in client.get("/precios").get_data(as_text=True)


def test_a_forged_or_foreign_checkout_link_gives_nothing(
    client: FlaskClient, seeded: SQLAlchemy, paywall: Flask
) -> None:
    _with_routine(client)
    location = _checkout(client)
    forged = re.sub(r"pago/([^/]+)$", r"pago/\g<1>x", location)
    client.post(forged, data={"outcome": "pay"})
    assert seeded.session.scalar(select(Subscription)) is None
    # Otra persona no puede usar el enlace de pago de esta.
    client.post("/salir")
    other = seeded.session.scalar(select(User))
    assert other is not None
    from tests.integration.test_auth import _register

    _register(client, "otra@example.com")
    assert client.post(location, data={"outcome": "pay"}).status_code == 403


def test_the_simulated_pages_do_not_exist_with_real_stripe(
    client: FlaskClient, seeded: SQLAlchemy, paywall: Flask
) -> None:
    _with_routine(client)
    paywall.config["BILLING_BACKEND"] = "stripe"
    assert client.get("/suscripcion/simulada/portal").status_code == 404
    assert client.get("/suscripcion/simulada/pago/x").status_code == 404


def test_with_the_paywall_off_everyone_has_everything(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    html = client.get("/panel").get_data(as_text=True)
    assert "pro-teaser" not in html


def test_deleting_the_account_cancels_first(
    client: FlaskClient, seeded: SQLAlchemy, paywall: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import billing
    from app.services.billing.fake import FakeGateway

    _with_routine(client)
    _subscribe(client)
    cancelled: list[str] = []
    monkeypatch.setattr(FakeGateway, "cancel_now", lambda self, row: cancelled.append(row.status))
    from tests.integration.test_auth import PASSWORD

    client.post("/cuenta/borrar", data={"current_password": PASSWORD, "confirmation": "BORRAR"})
    assert cancelled == ["trialing"]
    assert seeded.session.scalar(select(User)) is None

    del billing
