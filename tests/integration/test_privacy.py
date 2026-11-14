"""RGPD: explicit, separate and withdrawable consent; no health data leaves the app."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, select

from app.models import (
    ErasureRecord,
    Plan,
    Profile,
    Routine,
    Subscription,
    User,
    WeightLog,
    WorkoutSession,
)
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
    assert "limpiar=1" in response.headers["Location"]
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


# --- Copias de seguridad: lo borrado se vuelve a borrar al restaurar ---------


def _restore_user(database: SQLAlchemy, user_id: int, *, created: datetime) -> User:
    """Stand-in for a restored backup: the account comes back as it was."""
    user = User(
        id=user_id,
        email=f"restaurada{user_id}@example.com",
        display_name="Restaurada",
        password_hash="x",
        created_at=created,
        health_consent_at=created,
        health_consent_version="2026-11-12",
    )
    database.session.add(user)
    database.session.add(WeightLog(user_id=user_id, logged_on=created.date(), weight_kg=80))
    database.session.commit()
    return user


def test_erasures_leave_only_a_number_kind_and_date(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    user_id = _user(seeded).id
    client.post("/cuenta/consentimiento/retirar", data={"current_password": PASSWORD})
    client.post("/cuenta/borrar", data={"current_password": PASSWORD, "confirmation": "BORRAR"})
    rows = seeded.session.scalars(select(ErasureRecord).order_by(ErasureRecord.id)).all()
    assert [(r.user_id, r.kind) for r in rows] == [(user_id, "health"), (user_id, "account")]
    assert set(ErasureRecord.__table__.columns.keys()) == {"id", "user_id", "kind", "erased_at"}


def test_a_restored_backup_is_erased_again(seeded: SQLAlchemy, app: Flask) -> None:
    before = datetime.now(UTC) - timedelta(days=3)
    gone = _restore_user(seeded, 501, created=before)
    withdrawn = _restore_user(seeded, 502, created=before)
    privacy.record_erasure(gone.id, "account")
    privacy.record_erasure(withdrawn.id, "health")
    seeded.session.commit()

    result = privacy.reapply_erasures(app.config["ERASURE_LOG_DAYS"])

    assert (result.accounts, result.health) == (1, 1)
    seeded.session.expire_all()
    assert seeded.session.get(User, 501) is None
    still = seeded.session.get(User, 502)
    assert still is not None
    assert still.health_consent_at is None
    assert _health_rows(seeded, 502) == 0
    # Una segunda pasada no hace nada más.
    again = privacy.reapply_erasures(app.config["ERASURE_LOG_DAYS"])
    assert (again.accounts, again.health) == (0, 0)


def test_what_happened_after_the_erasure_is_respected(seeded: SQLAlchemy, app: Flask) -> None:
    privacy.record_erasure(601, "account")
    privacy.record_erasure(602, "health")
    seeded.session.commit()
    later = datetime.now(UTC) + timedelta(minutes=1)
    _restore_user(seeded, 601, created=later)  # otra cuenta que reutiliza el número
    _restore_user(seeded, 602, created=later)  # volvió a dar el consentimiento después
    result = privacy.reapply_erasures(app.config["ERASURE_LOG_DAYS"])
    assert (result.accounts, result.health) == (0, 0)
    assert _health_rows(seeded, 602) == 1


def test_old_erasures_are_forgotten(seeded: SQLAlchemy, app: Flask) -> None:
    keep = app.config["ERASURE_LOG_DAYS"]
    seeded.session.add(
        ErasureRecord(
            user_id=7, kind="account", erased_at=datetime.now(UTC) - timedelta(days=keep + 1)
        )
    )
    privacy.record_erasure(8, "account")
    seeded.session.commit()
    assert privacy.purge_erasure_log(keep) == 1
    assert [r.user_id for r in seeded.session.scalars(select(ErasureRecord))] == [8]


def test_the_commands_exist(app: Flask, seeded: SQLAlchemy) -> None:
    runner = app.test_cli_runner()
    assert "accounts deleted again: 0" in runner.invoke(args=["privacy", "reapply-erasures"]).output
    assert "old records purged: 0" in runner.invoke(args=["privacy", "purge-erasures"]).output
