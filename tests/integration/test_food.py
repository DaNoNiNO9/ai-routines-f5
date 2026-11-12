"""Logging food: basic table, Open Food Facts (simulated), barcodes, usual foods and totals."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.models import FoodEntry, IntakeLog, User
from tests.integration.test_workout_flow import _with_routine

BASIC = Path(__file__).resolve().parents[2] / "app" / "seeds" / "basic_foods.json"

YOGURT = {
    "code": "8480010180060",
    "product_name_es": "Yogur griego",
    "brands": ["Eroski"],
    "nutriments": {
        "energy-kcal_100g": 148,
        "proteins_100g": 2.4,
        "carbohydrates_100g": 17,
        "fat_100g": 7.8,
    },
    "serving_quantity": 125,
}
ONLY_KJ = {
    "code": "111",
    "product_name": "Pan de centeno",
    "brands": "Panadería",
    "nutriments": {
        "energy-kj_100g": 1046,
        "proteins_100g": 8,
        "carbohydrates_100g": 45,
        "fat_100g": 1.5,
    },
}
INCOMPLETE = {"code": "222", "product_name": "Sin hidratos", "nutriments": {"energy-kcal_100g": 98}}


class FakeOFF:
    """Answers like search.openfoodfacts.org and the product API."""

    def __init__(self, down: bool = False) -> None:
        self.down = down
        self.urls: list[str] = []

    def __call__(self, url: str) -> dict[str, Any]:
        from app.services.food import FoodError

        self.urls.append(url)
        if self.down:
            raise FoodError("off_unreachable")
        if "/api/v2/product/8480010180060" in url:
            return {"status": 1, "product": YOGURT}
        if "/api/v2/product/" in url:
            return {"status": 0, "status_verbose": "product not found"}
        return {"hits": [YOGURT, ONLY_KJ, INCOMPLETE]}


@pytest.fixture
def off(app: Flask) -> FakeOFF:
    from app.services import food

    food._cache.clear()
    fake = FakeOFF()
    app.config.update(OFF_ENABLED=True, OFF_FETCHER=fake)
    return fake


def _user(seeded: SQLAlchemy) -> User:
    user = seeded.session.scalar(select(User))
    assert user is not None
    return user


def test_the_basic_table_adds_up() -> None:
    """kcal ≈ 4·P + 4·C + 9·F (vegetables count fibre as carbohydrate; alcohol is apart)."""
    rows = json.loads(BASIC.read_text(encoding="utf-8"))
    assert len(rows) >= 60
    assert len({row["key"] for row in rows}) == len(rows)
    for row in rows:
        if row["key"] in {"cerveza", "vino-tinto"}:
            continue
        estimate = 4 * row["p"] + 4 * row["c"] + 9 * row["f"]
        assert abs(estimate - row["kcal"]) <= max(0.15 * row["kcal"], 8), row["key"]
        assert 0 < row["portion"] <= 400, row["key"]


def test_search_finds_basics_and_spanish_products(
    client: FlaskClient, seeded: SQLAlchemy, off: FakeOFF
) -> None:
    _with_routine(client)
    html = client.get("/diario/alimentos?q=yogur").get_data(as_text=True)
    assert "Yogur griego natural" in html  # tabla básica
    assert "valor medio" in html
    assert "Yogur griego" in html
    assert "Eroski" in html
    assert "Pan de centeno" in html  # solo kJ: convertido
    assert "250 kcal" in html  # 1046 kJ / 4,184
    assert "Sin hidratos" not in html  # incompleto: fuera
    assert "countries_tags%3A%22en%3Aspain%22" in off.urls[0]


def test_accents_do_not_matter(client: FlaskClient, seeded: SQLAlchemy, off: FakeOFF) -> None:
    _with_routine(client)
    assert "Plátano" in client.get("/diario/alimentos?q=platano").get_data(as_text=True)


def test_adding_foods_works_out_the_day(
    client: FlaskClient, seeded: SQLAlchemy, off: FakeOFF
) -> None:
    _with_routine(client)
    today = _user(seeded).today().isoformat()
    client.post(
        "/diario/alimentos",
        data={"source": "basic", "code": "arroz-blanco-cocido", "grams": "200", "fecha": today},
    )
    response = client.post(
        "/diario/alimentos",
        data={"source": "off", "code": "8480010180060", "grams": "125", "fecha": today},
    )
    assert response.status_code == 302
    intake = seeded.session.scalar(select(IntakeLog))
    assert intake is not None
    assert intake.calories == round(130 * 2 + 148 * 1.25)
    assert intake.protein_g == pytest.approx(2.7 * 2 + 2.4 * 1.25, abs=0.1)
    html = client.get("/diario").get_data(as_text=True)
    assert "Arroz blanco cocido" in html
    assert 'class="macro-bars"' in html


def test_values_come_from_the_source_not_the_browser(
    client: FlaskClient, seeded: SQLAlchemy, off: FakeOFF
) -> None:
    _with_routine(client)
    client.post(
        "/diario/alimentos",
        data={"source": "basic", "code": "aceite-oliva", "grams": "10", "kcal": "1"},
    )
    entry = seeded.session.scalar(select(FoodEntry))
    assert entry is not None
    assert entry.kcal_100g == 884
    bad = client.post(
        "/diario/alimentos", data={"source": "basic", "code": "no-existe", "grams": "10"}
    )
    assert bad.status_code == 302
    assert len(seeded.session.scalars(select(FoodEntry)).all()) == 1


def test_grams_must_be_sensible(client: FlaskClient, seeded: SQLAlchemy, off: FakeOFF) -> None:
    _with_routine(client)
    for grams in ("0", "-5", "9000", "mucho"):
        client.post("/diario/alimentos", data={"source": "basic", "code": "huevo", "grams": grams})
    assert seeded.session.scalar(select(FoodEntry)) is None
    client.post("/diario/alimentos", data={"source": "basic", "code": "huevo", "grams": "55,5"})
    entry = seeded.session.scalar(select(FoodEntry))
    assert entry is not None
    assert entry.grams == 55.5


def test_barcodes(client: FlaskClient, seeded: SQLAlchemy, off: FakeOFF) -> None:
    _with_routine(client)
    found = client.get("/diario/alimentos?codigo=8480010180060").get_data(as_text=True)
    assert "Yogur griego" in found
    assert 'value="125"' in found  # la ración del envase
    missing = client.get("/diario/alimentos?codigo=1234567890123").get_data(as_text=True)
    assert "No encontramos ese código" in missing
    bad = client.get("/diario/alimentos?codigo=12").get_data(as_text=True)
    assert "no parece válido" in bad


def test_open_food_facts_down_still_shows_the_basics(
    client: FlaskClient, seeded: SQLAlchemy, off: FakeOFF
) -> None:
    _with_routine(client)
    off.down = True
    html = client.get("/diario/alimentos?q=pollo").get_data(as_text=True)
    assert "Pechuga de pollo" in html
    assert "Open Food Facts no responde" in html


def test_usual_foods_copy_yesterday_and_delete(
    client: FlaskClient, seeded: SQLAlchemy, off: FakeOFF
) -> None:
    _with_routine(client)
    user = _user(seeded)
    yesterday = (user.today() - timedelta(days=1)).isoformat()
    for _ in range(2):
        client.post(
            "/diario/alimentos",
            data={"source": "basic", "code": "copos-de-avena", "grams": "60", "fecha": yesterday},
        )
    usual = client.get("/diario/alimentos").get_data(as_text=True)
    assert "Tus habituales" in usual
    assert "Copos de avena" in usual
    assert "Copiar lo de ayer" in client.get("/diario").get_data(as_text=True)
    client.post("/diario/alimentos/copiar", data={"fecha": user.today().isoformat()})
    today_rows = seeded.session.scalars(
        select(FoodEntry).where(FoodEntry.logged_on == user.today())
    ).all()
    assert len(today_rows) == 2
    for row in today_rows:
        client.post(f"/diario/alimentos/{row.id}/borrar")
    assert (
        seeded.session.scalar(select(IntakeLog).where(IntakeLog.logged_on == user.today())) is None
    )


def test_adherence_keeps_the_food_totals(
    client: FlaskClient, seeded: SQLAlchemy, off: FakeOFF
) -> None:
    _with_routine(client)
    today = _user(seeded).today().isoformat()
    client.post("/diario/alimentos", data={"source": "basic", "code": "platano", "grams": "100"})
    client.post(
        "/diario/ingesta",
        data={"day": today, "calories": "5000", "protein_g": "1", "adherence_pct": "90"},
    )
    intake = seeded.session.scalar(select(IntakeLog))
    assert intake is not None
    assert intake.calories == 89  # sale de los alimentos, no del formulario
    assert intake.adherence_pct == 90


def test_nobody_deletes_someone_elses_food(
    client: FlaskClient, seeded: SQLAlchemy, off: FakeOFF
) -> None:
    _with_routine(client)
    client.post("/diario/alimentos", data={"source": "basic", "code": "manzana", "grams": "150"})
    entry = seeded.session.scalar(select(FoodEntry))
    assert entry is not None
    client.post("/salir")
    from tests.integration.test_auth import _register

    _register(client, "otra@example.com")
    client.post(f"/diario/alimentos/{entry.id}/borrar")
    assert seeded.session.scalar(select(FoodEntry)) is not None


def test_food_search_is_pro(client: FlaskClient, seeded: SQLAlchemy, app: Flask) -> None:
    _with_routine(client)
    app.config["PAYWALL_ENABLED"] = True
    assert client.get("/diario/alimentos").headers["Location"].endswith("/precios")
    html = client.get("/diario").get_data(as_text=True)
    assert "Con Alza Pro buscas el alimento" in html
    assert 'name="calories"' in html  # el total a mano sigue siendo gratis
