"""RGPD: explicit, separate and withdrawable consent; no health data leaves the app."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, select

from app.models import Plan, Profile, Routine, Subscription, User, WeightLog, WorkoutSession
from app.services import privacy
from app.services.billing.stripe_gateway import StripeGateway
from tests.integration.test_auth import PASSWORD, _register
from tests.integration.test_food import FakeOFF, off  # noqa: F401
from tests.integration.test_stripe_gateway import CONFIG, Recorder, stripe_app  # noqa: F401
from tests.integration.test_workout_flow import _with_routine

TEMPLATES = Path(__file__).resolve().parents[2] / "app" / "templates"


def _user(database: SQLAlchemy) -> User:
    user = database.session.scalar(select(User))
    assert user is not None
    return user


def _health_rows(database: SQLAlchemy, user_id: int) -> int:
    total = 0
    for model in (*privacy.HEALTH_TABLES, WorkoutSession, Routine, Plan, Profile):
        total += (
            database.session.scalar(
                select(func.count()).select_from(model).where(model.user_id == user_id)
            )
            or 0
        )
    return total


def test_registration_needs_the_separate_health_consent(
    client: FlaskClient, database: SQLAlchemy
) -> None:
    response = _register(client, health_consent="")
    assert response.status_code == 200
    assert "Sin este consentimiento no podemos calcular tu plan." in response.get_data(as_text=True)
    assert database.session.scalar(select(func.count()).select_from(User)) == 0


def test_registration_records_when_and_which_version(
    client: FlaskClient, database: SQLAlchemy
) -> None:
    _register(client)
    user = _user(database)
    assert user.health_consent_at is not None
    assert user.health_consent_version == privacy.CONSENT_VERSION


def test_the_consent_box_is_apart_from_the_terms(client: FlaskClient) -> None:
    html = client.get("/registro").get_data(as_text=True)
    assert 'name="consent"' in html
    assert 'name="health_consent"' in html
    assert not re.search(r'name="health_consent"[^>]*checked', html)  # nunca premarcada


def test_without_consent_no_health_screen_opens(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    user = _user(seeded)
    user.health_consent_at = None
    seeded.session.commit()
    for path in ("/panel", "/diario", "/nutricion", "/cuestionario/paso/1", "/revision"):
        response = client.get(path)
        assert response.status_code == 302, path
        assert response.headers["Location"].endswith("/consentimiento"), path
    for path in ("/cuenta", "/cuenta/datos.zip", "/privacidad", "/precios", "/consentimiento"):
        assert client.get(path).status_code == 200, path


def test_giving_consent_later_opens_the_app(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    user = _user(seeded)
    user.health_consent_at = None
    seeded.session.commit()
    refused = client.post("/consentimiento", data={})
    assert "Marca la casilla" in refused.get_data(as_text=True)
    assert _user(seeded).health_consent_at is None
    client.post("/consentimiento", data={"health_consent": "y"})
    assert _user(seeded).has_health_consent
    assert client.get("/panel").status_code == 200


def test_withdrawing_deletes_every_health_row_and_keeps_the_account(
    client: FlaskClient, seeded: SQLAlchemy, app: Flask
) -> None:
    app.config["PAYWALL_ENABLED"] = True
    _with_routine(client)
    user = _user(seeded)
    client.post("/diario/peso", data={"day": user.today().isoformat(), "weight_kg": "80"})
    seeded.session.add(Subscription(user_id=user.id, plan="monthly", status="active"))
    seeded.session.commit()
    user_id = user.id
    assert _health_rows(seeded, user_id) > 0
    assert seeded.session.scalar(select(func.count()).select_from(WeightLog)) == 1

    wrong = client.post("/cuenta/consentimiento/retirar", data={"current_password": "nope"})
    assert "La contraseña no es correcta." in wrong.get_data(as_text=True)
    assert _user(seeded).has_health_consent

    response = client.post("/cuenta/consentimiento/retirar", data={"current_password": PASSWORD})
    assert response.status_code == 302
    assert response.headers["Clear-Site-Data"] == '"cache", "storage"'
    seeded.session.expire_all()
    user = _user(seeded)
    assert user.health_consent_at is None
    assert not user.equipment
    assert _health_rows(seeded, user_id) == 0
    assert seeded.session.scalar(select(Subscription).where(Subscription.user_id == user_id))
    assert client.get("/cuenta").status_code == 200


def test_no_third_party_scripts_or_analytics_in_any_template() -> None:
    for template in TEMPLATES.rglob("*.html"):
        text = template.read_text(encoding="utf-8")
        assert not re.search(r"<script[^>]+src=[\"']https?://", text), template
        for tracker in ("googletagmanager", "google-analytics", "gtag(", "plausible", "hotjar"):
            assert tracker not in text, (template, tracker)


def test_csp_only_allows_our_own_scripts(client: FlaskClient) -> None:
    csp = client.get("/").headers["Content-Security-Policy"]
    script = next(part for part in csp.split(";") if part.strip().startswith("script-src"))
    assert "http" not in script


def test_stripe_never_receives_health_data(
    client: FlaskClient,
    seeded: SQLAlchemy,
    stripe_app: Flask,  # noqa: F811
) -> None:
    _with_routine(client)
    user = _user(seeded)
    recorder = Recorder({"id": "cs_1", "url": "https://checkout.stripe.com/c/pay/cs_1"})
    with stripe_app.test_request_context():
        StripeGateway(CONFIG, transport=recorder).checkout_url(
            user, "monthly", "https://alza.fit/ok", "https://alza.fit/precios", 7
        )
    fields = recorder.calls[0][2]
    sent = " ".join(f"{k}={v}" for k, v in fields.items()).lower()
    for word in ("weight", "peso", "height", "sex", "birth", "diet", "injur", "kcal", "goal"):
        assert word not in sent, word
    assert set(fields.values()) & {user.email, str(user.id)}


def test_open_food_facts_only_gets_the_search_text(
    client: FlaskClient,
    seeded: SQLAlchemy,
    off: FakeOFF,  # noqa: F811
) -> None:
    _with_routine(client)
    user = _user(seeded)
    client.get("/diario/alimentos?q=yogur")
    client.get("/diario/alimentos?codigo=8480010180060")
    assert off.urls
    for url in off.urls:
        assert user.email not in url
        assert "ana" not in url.lower()
        assert f"user={user.id}" not in url
        assert f"user_id={user.id}" not in url


def test_logs_do_not_keep_what_you_search(
    client: FlaskClient, seeded: SQLAlchemy, caplog: pytest.LogCaptureFixture
) -> None:
    _with_routine(client)
    with caplog.at_level("INFO"):
        client.get("/diario/alimentos?q=kebab")
    assert "kebab" not in caplog.text
