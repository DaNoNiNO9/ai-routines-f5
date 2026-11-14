"""The week's menu for a plan, its shopping list, and logging a planned meal in one tap."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.engine import menu as engine
from app.engine.enums import DietPattern
from app.models import Plan, Profile, User
from app.services import food as food_service

DAYS = 7
EGG_KEY = "huevo"

# Sección del súper de cada alimento de la tabla (lo que no está, «Otros»).
AISLES: dict[str, tuple[str, ...]] = {
    "meat_fish": (
        "pechuga-pollo-plancha",
        "pavo-pechuga",
        "ternera-magra",
        "lomo-cerdo",
        "jamon-serrano",
        "jamon-cocido",
        "salmon",
        "merluza",
        "atun-lata-natural",
        "gambas",
        "tofu",
        "tempeh",
        "seitan",
    ),
    "dairy_eggs": (
        "huevo",
        "clara-huevo",
        "leche-semidesnatada",
        "yogur-proteinas",
        "queso-fresco-batido",
        "bebida-soja",
        "proteina-whey",
    ),
    "grains": (
        "pan-integral",
        "pan-blanco",
        "copos-de-avena",
        "arroz-blanco-cocido",
        "arroz-integral-cocido",
        "pasta-cocida",
        "quinoa-cocida",
        "lentejas-cocidas",
        "garbanzos-cocidos",
        "patata-cocida",
        "boniato-asado",
    ),
    "fruit_veg": (
        "tomate",
        "lechuga",
        "brocoli",
        "judias-verdes",
        "espinacas",
        "pimiento",
        "calabacin",
        "champinones",
        "zanahoria",
        "platano",
        "naranja",
        "fresas",
        "arandanos",
        "aguacate",
    ),
    "pantry": ("aceite-oliva", "nueces", "almendras", "crema-cacahuete"),
}
AISLE_ORDER = ("fruit_veg", "meat_fish", "dairy_eggs", "grains", "pantry", "other")
# Lo cocido se compra en crudo: factor de cocido a crudo (aprox.).
RAW_FACTOR = {
    "arroz-blanco-cocido": ("arroz-blanco-crudo", 1 / 2.8),
    "arroz-integral-cocido": ("arroz-blanco-crudo", 1 / 2.6),
    "pasta-cocida": ("pasta-cruda", 1 / 2.2),
}


@dataclass(frozen=True)
class ServedDay:
    """One day of the menu."""

    day: date
    plates: list[engine.Plate]


def _foods() -> dict[str, engine.FoodValues]:
    return {
        row["key"]: engine.FoodValues(row["kcal"], row["p"], row["c"], row["f"])
        for row in food_service._basic_rows()
    }


def name_of(key: str) -> str:
    """The food's name in the reader's language."""
    found = food_service.basic_food(key)
    return found.name if found else key


def targets(plan: Plan) -> list[engine.Target]:
    """The plan's meals as targets for the engine."""
    return [
        engine.Target(meal.position, meal.name, meal.protein_g, meal.carbs_g, meal.fat_g)
        for meal in sorted(plan.meals, key=lambda meal: meal.position)
    ]


def seed_for(user: User, variant: int) -> int:
    """Same person and variant, same menu: the «log it» button relies on it."""
    return user.id * 1000 + max(0, variant)


def week_for(
    user: User, plan: Plan, profile: Profile, today: date, variant: int
) -> list[ServedDay]:
    """Seven days from today."""
    diet = DietPattern(profile.diet_pattern or DietPattern.OMNIVORE)
    menu = engine.week(targets(plan), diet, _foods(), seed_for(user, variant), DAYS)
    return [ServedDay(today + timedelta(days=index), plates) for index, plates in enumerate(menu)]


def log_plate(user: User, day: date, plate: engine.Plate) -> int:
    """Put every food of a planned meal in the diary; how many were added.

    A food already logged that day with the same grams is not added again: a
    double tap on «apuntar» would otherwise double the meal.
    """
    already = {(row.name, round(row.grams, 1)) for row in food_service.entries(user, day)}
    added = 0
    for portion in plate.portions:
        found = food_service.basic_food(portion.food)
        if found is not None and portion.grams > 0:
            if (found.name, round(float(portion.grams), 1)) in already:
                continue
            food_service.add(user, day, found, portion.grams)
            added += 1
    return added


@dataclass(frozen=True)
class ShoppingItem:
    """One line of the shopping list."""

    key: str
    name: str
    grams: float
    units: int | None  # huevos


def shopping(days: list[ServedDay]) -> list[tuple[str, list[ShoppingItem]]]:
    """The week's foods by supermarket aisle, cooked weights turned into raw ones."""
    totals = engine.shopping_list([served.plates for served in days])
    merged: dict[str, float] = {}
    for key, grams in totals.items():
        raw_key, factor = RAW_FACTOR.get(key, (key, 1.0))
        merged[raw_key] = merged.get(raw_key, 0) + grams * factor
    by_aisle: dict[str, list[ShoppingItem]] = {}
    for key, grams in merged.items():
        aisle = next(
            (
                name
                for name, keys in AISLES.items()
                if key in keys or RAW_FACTOR_SOURCE.get(key) in keys
            ),
            "other",
        )
        units = round(grams / engine.EGG_GRAMS) if key == EGG_KEY else None
        rounded = grams if grams < 50 else 10 * round(grams / 10)
        by_aisle.setdefault(aisle, []).append(ShoppingItem(key, name_of(key), rounded, units))
    return [
        (aisle, sorted(by_aisle[aisle], key=lambda item: item.name))
        for aisle in AISLE_ORDER
        if aisle in by_aisle
    ]


RAW_FACTOR_SOURCE = {raw: cooked for cooked, (raw, _factor) in RAW_FACTOR.items()}


def summary(plate: engine.Plate) -> dict[str, Any]:
    """Display data for one plate."""
    return {
        "items": [(name_of(p.food), p.grams, p.food == EGG_KEY) for p in plate.portions],
        "kcal": plate.kcal,
        "protein": plate.protein,
        "carbs": plate.carbs,
        "fat": plate.fat,
        "target_kcal": 4 * plate.target.protein + 4 * plate.target.carbs + 9 * plate.target.fat,
    }
