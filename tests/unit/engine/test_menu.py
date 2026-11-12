"""The menu engine: dishes that add up, limits, diets and a stable week."""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

import pytest

from app.engine.enums import DietPattern
from app.engine.menu import (
    DISHES,
    EGG_GRAMS,
    EXCLUDED,
    FoodValues,
    Target,
    _limits,
    allowed,
    kind_of,
    plate,
    shopping_list,
    week,
)

BASIC = Path(__file__).resolve().parents[3] / "app" / "seeds" / "basic_foods.json"
FOODS = {
    row["key"]: FoodValues(row["kcal"], row["p"], row["c"], row["f"])
    for row in json.loads(BASIC.read_text(encoding="utf-8"))
}
SMALL = [
    Target(1, "Desayuno", 25, 40, 12),
    Target(2, "Comida", 35, 55, 14),
    Target(3, "Merienda", 18, 25, 8),
    Target(4, "Cena", 35, 45, 13),
]
MEDIUM = [
    Target(1, "Desayuno", 35, 60, 17),
    Target(2, "Comida", 45, 75, 18),
    Target(3, "Merienda", 25, 35, 10),
    Target(4, "Cena", 45, 60, 17),
]
LARGE = [
    Target(1, "Desayuno", 45, 90, 25),
    Target(2, "Comida", 55, 110, 25),
    Target(3, "Merienda", 35, 60, 15),
    Target(4, "Cena", 55, 90, 22),
]


def _kcal(target: Target) -> float:
    return 4 * target.protein + 4 * target.carbs + 9 * target.fat


def test_every_dish_uses_foods_of_the_table() -> None:
    for dish in DISHES:
        for food in (dish.protein, dish.carbs, dish.fat, *(name for name, _ in dish.fixed)):
            assert food in FOODS, (dish.key, food)
    assert len({dish.key for dish in DISHES}) == len(DISHES)


@pytest.mark.parametrize("targets", [SMALL, MEDIUM, LARGE], ids=["small", "medium", "large"])
def test_every_dish_lands_near_its_meal(targets: list[Target]) -> None:
    for dish in DISHES:
        target = next(item for item in targets if kind_of(item.name) == dish.kind)
        served = plate(dish, target, FOODS)
        assert abs(served.kcal - _kcal(target)) / _kcal(target) <= 0.15, dish.key


def test_portions_respect_the_limits_and_eggs_are_whole() -> None:
    for targets in (SMALL, MEDIUM, LARGE):
        for dish in DISHES:
            target = next(item for item in targets if kind_of(item.name) == dish.kind)
            for portion in plate(dish, target, FOODS).portions:
                if portion.food in {name for name, _ in dish.fixed}:
                    continue
                low, high = _limits(portion.food)
                assert low - 2.5 <= portion.grams <= high + 2.5, (dish.key, portion)
                if portion.food == "huevo":
                    assert portion.grams % EGG_GRAMS == 0
                else:
                    assert portion.grams % 5 == 0


@pytest.mark.parametrize("diet", list(DietPattern))
def test_each_diet_gets_only_what_it_eats(diet: DietPattern) -> None:
    menu = week(MEDIUM, diet, FOODS, seed=3)
    for plates in menu:
        for served in plates:
            assert allowed(served.dish, diet)
            assert not {portion.food for portion in served.portions} & EXCLUDED[diet]


def test_vegan_means_no_animal_food_at_all() -> None:
    for plates in week(MEDIUM, DietPattern.VEGAN, FOODS, seed=5):
        for served in plates:
            foods = {portion.food for portion in served.portions}
            assert not foods & {"huevo", "leche-semidesnatada", "yogur-proteinas", "proteina-whey"}


def test_the_same_seed_gives_the_same_week_and_another_seed_varies() -> None:
    first = week(MEDIUM, DietPattern.OMNIVORE, FOODS, seed=11)
    again = week(MEDIUM, DietPattern.OMNIVORE, FOODS, seed=11)
    other = week(MEDIUM, DietPattern.OMNIVORE, FOODS, seed=12)
    keys = lambda menu: [[served.dish.key for served in day] for day in menu]  # noqa: E731
    assert keys(first) == keys(again)
    assert keys(first) != keys(other)


def test_no_day_repeats_the_main_dish_of_the_day_before() -> None:
    menu = week(MEDIUM, DietPattern.OMNIVORE, FOODS, seed=7)
    lunches = [day[1].dish.key for day in menu]
    assert all(a != b for a, b in pairwise(lunches))


def test_meal_names_pick_the_kind_of_dish() -> None:
    assert kind_of("Desayuno") == "breakfast"
    assert kind_of("Comida") == "main"
    assert kind_of("Cena") == "main"
    assert kind_of("Merienda") == "snack"
    assert kind_of("Media mañana") == "snack"
    assert kind_of("Recena") == "snack"


def test_the_shopping_list_adds_the_week_up() -> None:
    menu = week(MEDIUM, DietPattern.OMNIVORE, FOODS, seed=2)
    totals = shopping_list(menu)
    expected = sum(portion.grams for day in menu for served in day for portion in served.portions)
    assert sum(totals.values()) == pytest.approx(expected)


def test_soy_breakfasts_are_only_for_vegans() -> None:
    soy = {"avena-soja", "soja-avena"}
    for diet in DietPattern:
        keys = {dish.key for dish in DISHES if allowed(dish, diet)}
        assert bool(keys & soy) == (diet is DietPattern.VEGAN), diet
