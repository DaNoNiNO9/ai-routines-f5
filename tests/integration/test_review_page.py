"""The review page: what the engine proposes and what applying it changes."""

from __future__ import annotations

from datetime import timedelta

from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.engine.enums import PlanStatus
from app.models import Plan, User, WeightLog
from app.services import tracking
from tests.integration.test_onboarding import _fill_all, _signup


def _user(database: SQLAlchemy) -> User:
    user = database.session.scalar(select(User))
    assert user is not None
    return user


def _plan(database: SQLAlchemy) -> Plan:
    plan = database.session.scalar(
        select(Plan).where(Plan.status == PlanStatus.ACTIVE).order_by(Plan.version.desc())
    )
    assert plan is not None
    return plan


def _with_plan(client: FlaskClient, seeded: SQLAlchemy, days_ago: int = 15) -> tuple[User, Plan]:
    """A finished questionnaire whose plan started ``days_ago`` days ago."""
    _signup(client)
    _fill_all(client)
    client.post("/cuestionario/revisar")
    user = _user(seeded)
    plan = _plan(seeded)
    plan.starts_on = user.today() - timedelta(days=days_ago)
    seeded.session.commit()
    return user, plan


def _log_daily_weights(seeded: SQLAlchemy, user: User, plan: Plan, total_change_kg: float) -> None:
    days = (user.today() - plan.starts_on).days
    start = plan.details["body"]["weight_kg"]
    for offset in range(days + 1):
        weight = start + total_change_kg * offset / days
        tracking.upsert_weight(user, plan.starts_on + timedelta(days=offset), round(weight, 2))
    seeded.session.commit()


def test_the_review_page_needs_a_plan_and_data(client: FlaskClient, seeded: SQLAlchemy) -> None:
    assert client.get("/revision").status_code == 302  # anonymous

    _signup(client)
    assert client.get("/revision").headers["Location"].endswith("/cuestionario")

    _fill_all(client)
    client.post("/cuestionario/revisar")
    # The questionnaire logs today's weight, so there is already one weigh-in.
    page = client.get("/revision").get_data(as_text=True)
    assert "Plan vigente" in page
    assert "Aplicar la revisión" not in page

    seeded.session.query(WeightLog).delete()
    seeded.session.commit()
    empty = client.get("/revision").get_data(as_text=True)
    assert "Sin pesajes" in empty
    assert "Ir al diario" in empty


def test_before_the_due_date_it_only_explains_when(client: FlaskClient, seeded: SQLAlchemy) -> None:
    user, plan = _with_plan(client, seeded, days_ago=5)
    _log_daily_weights(seeded, user, plan, -0.2)

    page = client.get("/revision").get_data(as_text=True)
    assert "próxima revisión" in page
    assert "Aplicar la revisión" not in page
    assert "Sigue apuntando tu peso" in page

    blocked = client.post("/revision/aplicar", follow_redirects=True)
    assert "Todavía no toca" in blocked.get_data(as_text=True)
    assert len(seeded.session.scalars(select(Plan)).all()) == 1


def test_applying_a_review_creates_the_next_plan_version(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    user, plan = _with_plan(client, seeded)
    _log_daily_weights(seeded, user, plan, -0.15)  # much slower than planned
    before = plan.calorie_target

    page = client.get("/revision").get_data(as_text=True)
    assert "Toca revisar" in page
    assert "Bajar calorías" in page
    assert "Aplicar la revisión" in page
    assert f"{before}" in page
    assert len(seeded.session.scalars(select(Plan)).all()) == 1  # nothing written yet

    applied = client.post("/revision/aplicar")
    assert applied.status_code == 302
    assert applied.headers["Location"].endswith("/nutricion")
    seeded.session.expire_all()

    versions = seeded.session.scalars(select(Plan).order_by(Plan.version)).all()
    assert [item.version for item in versions] == [1, 2]
    assert versions[0].status is PlanStatus.SUPERSEDED
    assert versions[1].status is PlanStatus.ACTIVE
    assert versions[1].calorie_target < before

    nutrition = client.get("/nutricion").get_data(as_text=True)
    assert "Plan actualizado a la versión 2" in nutrition
    assert f"{versions[1].calorie_target}" in nutrition

    # The record travels with the plan the decision produced, and the clock restarts.
    after = client.get("/revision").get_data(as_text=True)
    assert "Revisiones de este plan" in after
    assert "Bajar calorías" in after
    assert "Ninguna todavía" not in after
    assert "Aplicar la revisión" not in after


def test_a_review_without_changes_is_recorded_all_the_same(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    user, plan = _with_plan(client, seeded)
    expected_weekly = plan.details["target"]["expected_weekly_change_kg"]
    _log_daily_weights(seeded, user, plan, expected_weekly * 15 / 7)

    page = client.get("/revision").get_data(as_text=True)
    assert "Mantener el plan" in page

    applied = client.post("/revision/aplicar", follow_redirects=True)
    text = applied.get_data(as_text=True)
    assert "Revisión registrada" in text
    assert "Mantener el plan" in text
    assert len(seeded.session.scalars(select(Plan)).all()) == 1
    assert "Revisiones de este plan" in text
    assert "Ninguna todavía" not in text


def test_the_review_shows_the_observed_expenditure_and_adherence(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    user, plan = _with_plan(client, seeded)
    _log_daily_weights(seeded, user, plan, -0.15)
    for offset in range((user.today() - plan.starts_on).days + 1):
        tracking.upsert_intake(
            user, plan.starts_on + timedelta(days=offset), plan.calorie_target, adherence_pct=95
        )
    seeded.session.commit()

    page = client.get("/revision").get_data(as_text=True)
    assert "Lo que gastas de verdad" in page
    assert "Cuánto has seguido el plan" in page
    assert "95" in page
    assert "Días con comida apuntada" in page
