"""The week's menu, its shopping list and logging a planned meal."""

from __future__ import annotations

from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.models import FoodEntry, IntakeLog
from tests.integration.test_workout_flow import _with_routine


def test_the_menu_shows_seven_days_of_dishes(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    html = client.get("/nutricion/menu").get_data(as_text=True)
    assert html.count('class="card menu-day"') == 7
    assert "Hoy" in html
    assert "Me lo he comido: apuntar" in html
    assert "Lista de la compra" in html
    assert " g</span>" in html


def test_another_menu_changes_the_dishes(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)

    def dishes(variant: int) -> str:
        html = client.get(f"/nutricion/menu?variante={variant}").get_data(as_text=True)
        return html.split('<div class="menu-days">', 1)[1].split('<p class="help">', 1)[0]

    first = dishes(0)
    assert dishes(1) != first
    assert dishes(0) == first


def test_logging_a_planned_meal_fills_the_diary(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    response = client.post("/nutricion/menu/apuntar", data={"comida": "1", "variante": "0"})
    assert response.status_code == 302
    rows = seeded.session.scalars(select(FoodEntry)).all()
    assert len(rows) >= 3
    assert seeded.session.scalar(select(IntakeLog)) is not None
    assert client.post("/nutricion/menu/apuntar", data={"comida": "99"}).status_code == 400


def test_the_shopping_list_groups_by_aisle_and_buys_raw(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    html = client.get("/nutricion/menu/compra").get_data(as_text=True)
    assert "Fruta y verdura" in html
    assert 'type="checkbox"' in html
    assert (
        "cocido" not in html.split("<main", 1)[1].split("</main>", 1)[0].lower() or "crudo" in html
    )


def test_menus_respect_a_vegan_diet(client: FlaskClient, seeded: SQLAlchemy) -> None:
    from tests.integration.test_onboarding import STEP_ANSWERS, _post_step, _signup

    _signup(client)
    for number in range(1, 8):
        overrides = {"diet_pattern": "vegan"} if number == 6 else {}
        _post_step(client, number, **overrides)
    client.post("/cuestionario/revisar")
    html = client.get("/nutricion/menu").get_data(as_text=True)
    for word in ("Pollo", "Huevo", "Yogur", "Salmón", "Jamón", "Leche"):
        assert word not in html, word
    del STEP_ANSWERS


def test_the_menu_is_pro(client: FlaskClient, seeded: SQLAlchemy, app: Flask) -> None:
    _with_routine(client)
    app.config["PAYWALL_ENABLED"] = True
    assert client.get("/nutricion/menu").headers["Location"].endswith("/precios")
    assert "Menú con platos y lista de la compra" in client.get("/nutricion").get_data(as_text=True)
