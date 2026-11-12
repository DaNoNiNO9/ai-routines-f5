"""A week of real meals that add up to the plan's macros.

Each dish has one main source of protein, one of carbohydrate and one of fat,
plus vegetables or fruit in a fixed amount. The grams of the three main foods
come from solving the meal's three equations (protein, carbohydrate and fat)
with sensible limits (nobody eats 600 g of rice or 40 g of oil), rounded to 5 g
(eggs, to whole units). When the limits do not let a dish hit the target, the
solver keeps the closest portion it can and the difference is shown, never hidden.

Pure functions: the foods come in as a table (``FoodValues`` per key) and the
choice of dishes depends only on the seed, so the same week and variant always
give the same menu (the «log it» button relies on that).
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.engine.enums import DietPattern


@dataclass(frozen=True)
class FoodValues:
    """Values per 100 g."""

    kcal: float
    protein: float
    carbs: float
    fat: float


@dataclass(frozen=True)
class Target:
    """What one meal of the plan has to bring."""

    position: int
    name: str
    protein: float
    carbs: float
    fat: float


@dataclass(frozen=True)
class Dish:
    """A recipe: three foods whose grams are solved, and fixed extras."""

    key: str
    name_es: str
    name_en: str
    kind: str  # breakfast | main | snack
    protein: str
    carbs: str
    fat: str
    fixed: tuple[tuple[str, float], ...] = ()
    only: tuple[DietPattern, ...] = ()  # vacío: cualquier dieta que lo admita


@dataclass(frozen=True)
class Portion:
    """One food of a served dish."""

    food: str
    grams: float


@dataclass(frozen=True)
class Plate:
    """A dish served for one meal, with what it actually brings."""

    target: Target
    dish: Dish
    portions: tuple[Portion, ...]
    kcal: float
    protein: float
    carbs: float
    fat: float


# Food families each diet leaves out.
FAMILIES: dict[str, frozenset[str]] = {
    "meat": frozenset(
        {
            "pechuga-pollo-plancha",
            "pavo-pechuga",
            "ternera-magra",
            "lomo-cerdo",
            "jamon-serrano",
            "jamon-cocido",
            "muslo-pollo-asado",
            "carne-picada-mixta",
        }
    ),
    "pork": frozenset({"lomo-cerdo", "jamon-serrano", "jamon-cocido"}),
    "fish": frozenset(
        {"salmon", "merluza", "atun-lata-natural", "atun-lata-aceite", "sardinas-lata"}
    ),
    "shellfish": frozenset({"gambas"}),
    "dairy": frozenset(
        {
            "leche-semidesnatada",
            "leche-entera",
            "leche-desnatada",
            "yogur-natural",
            "yogur-griego",
            "yogur-proteinas",
            "queso-fresco-batido",
            "queso-fresco",
            "queso-curado",
            "mantequilla",
            "proteina-whey",
        }
    ),
    "egg": frozenset({"huevo", "clara-huevo"}),
    "honey": frozenset({"miel"}),
}
EXCLUDED: dict[DietPattern, frozenset[str]] = {
    DietPattern.OMNIVORE: frozenset(),
    DietPattern.VEGETARIAN: FAMILIES["meat"] | FAMILIES["fish"] | FAMILIES["shellfish"],
    DietPattern.VEGAN: FAMILIES["meat"]
    | FAMILIES["fish"]
    | FAMILIES["shellfish"]
    | FAMILIES["dairy"]
    | FAMILIES["egg"]
    | FAMILIES["honey"],
    DietPattern.PESCETARIAN: FAMILIES["meat"],
    DietPattern.HALAL: FAMILIES["pork"],
    DietPattern.KOSHER: FAMILIES["pork"] | FAMILIES["shellfish"],
}

# Grams each main food can take in one meal (default 20-350 g).
LIMITS: dict[str, tuple[float, float]] = {
    "aceite-oliva": (0, 25),
    "mantequilla": (0, 20),
    "nueces": (0, 40),
    "almendras": (0, 40),
    "crema-cacahuete": (0, 35),
    "aguacate": (0, 150),
    "huevo": (55, 220),  # de 1 a 4 huevos
    "pan-integral": (30, 160),
    "pan-blanco": (30, 160),
    "copos-de-avena": (20, 120),
    "jamon-serrano": (20, 100),
    "jamon-cocido": (20, 150),
    "proteina-whey": (10, 50),
    "yogur-proteinas": (100, 500),
    "queso-fresco-batido": (100, 500),
    "bebida-soja": (150, 500),
    "platano": (60, 240),
    "clara-huevo": (0, 350),
    "patata-cocida": (100, 600),
    "boniato-asado": (100, 500),
    "arroz-blanco-cocido": (60, 450),
    "arroz-integral-cocido": (60, 450),
    "pasta-cocida": (60, 450),
    "quinoa-cocida": (60, 400),
    "lentejas-cocidas": (100, 400),
    "garbanzos-cocidos": (100, 400),
}
EGG_GRAMS = 55.0

DISHES: tuple[Dish, ...] = (
    # Desayunos
    Dish(
        "tostadas-huevo",
        "Tostadas con huevo y aguacate",
        "Toast with egg and avocado",
        "breakfast",
        "huevo",
        "pan-integral",
        "aguacate",
        (("tomate", 80),),
    ),
    Dish(
        "avena-yogur",
        "Avena con yogur, nueces y arándanos",
        "Oats with yogurt, walnuts and blueberries",
        "breakfast",
        "yogur-proteinas",
        "copos-de-avena",
        "nueces",
        (("arandanos", 80),),
    ),
    Dish(
        "tostada-jamon",
        "Tostada con tomate, jamón y aceite",
        "Toast with tomato, ham and olive oil",
        "breakfast",
        "jamon-serrano",
        "pan-blanco",
        "aceite-oliva",
        (("tomate", 60), ("naranja", 180)),
    ),
    Dish(
        "tofu-revuelto",
        "Tofu revuelto con tostadas",
        "Scrambled tofu on toast",
        "breakfast",
        "tofu",
        "pan-integral",
        "aguacate",
        (("tomate", 80),),
    ),
    Dish(
        "avena-soja",
        "Avena con bebida de soja y crema de cacahuete",
        "Oats with soy drink and peanut butter",
        "breakfast",
        "bebida-soja",
        "copos-de-avena",
        "crema-cacahuete",
        (("platano", 100),),
        (DietPattern.VEGAN,),
    ),
    Dish(
        "batido-queso",
        "Queso batido con avena y fresas",
        "Quark with oats and strawberries",
        "breakfast",
        "queso-fresco-batido",
        "copos-de-avena",
        "almendras",
        (("fresas", 120),),
    ),
    # Comidas y cenas
    Dish(
        "pollo-arroz",
        "Pollo con arroz y brócoli",
        "Chicken with rice and broccoli",
        "main",
        "pechuga-pollo-plancha",
        "arroz-blanco-cocido",
        "aceite-oliva",
        (("brocoli", 150),),
    ),
    Dish(
        "salmon-patata",
        "Salmón con patata y judías verdes",
        "Salmon with potato and green beans",
        "main",
        "salmon",
        "patata-cocida",
        "aceite-oliva",
        (("judias-verdes", 150),),
    ),
    Dish(
        "ternera-pasta",
        "Pasta con ternera y tomate",
        "Pasta with beef and tomato",
        "main",
        "ternera-magra",
        "pasta-cocida",
        "aceite-oliva",
        (("tomate", 120),),
    ),
    Dish(
        "merluza-boniato",
        "Merluza con boniato y espinacas",
        "Hake with sweet potato and spinach",
        "main",
        "merluza",
        "boniato-asado",
        "aceite-oliva",
        (("espinacas", 150),),
    ),
    Dish(
        "pavo-patata",
        "Pavo con patata y champiñones",
        "Turkey with potato and mushrooms",
        "main",
        "pavo-pechuga",
        "patata-cocida",
        "aceite-oliva",
        (("champinones", 150),),
    ),
    Dish(
        "atun-pasta",
        "Pasta con atún y tomate",
        "Pasta with tuna and tomato",
        "main",
        "atun-lata-natural",
        "pasta-cocida",
        "aceite-oliva",
        (("tomate", 120),),
    ),
    Dish(
        "lomo-patata",
        "Lomo con patatas y pimientos",
        "Pork loin with potatoes and peppers",
        "main",
        "lomo-cerdo",
        "patata-cocida",
        "aceite-oliva",
        (("pimiento", 120),),
    ),
    Dish(
        "tortilla-ensalada",
        "Tortilla de huevo y claras con pan y ensalada",
        "Egg and egg-white omelette with bread and salad",
        "main",
        "clara-huevo",
        "pan-integral",
        "aceite-oliva",
        (("huevo", 110), ("lechuga", 80), ("tomate", 100)),
    ),
    Dish(
        "lentejas-seitan",
        "Lentejas estofadas con seitán",
        "Stewed lentils with seitan",
        "main",
        "seitan",
        "lentejas-cocidas",
        "aceite-oliva",
        (("pimiento", 80), ("zanahoria", 60)),
    ),
    Dish(
        "tofu-quinoa",
        "Tofu salteado con quinoa y calabacín",
        "Stir-fried tofu with quinoa and courgette",
        "main",
        "tofu",
        "quinoa-cocida",
        "aceite-oliva",
        (("calabacin", 150),),
    ),
    Dish(
        "garbanzos-huevo",
        "Garbanzos con espinacas y huevo",
        "Chickpeas with spinach and egg",
        "main",
        "huevo",
        "garbanzos-cocidos",
        "aceite-oliva",
        (("espinacas", 150),),
    ),
    Dish(
        "garbanzos-tofu",
        "Garbanzos salteados con tofu",
        "Chickpeas stir-fried with tofu",
        "main",
        "tofu",
        "garbanzos-cocidos",
        "aceite-oliva",
        (("espinacas", 150),),
    ),
    Dish(
        "seitan-arroz",
        "Seitán con arroz integral y pimiento",
        "Seitan with brown rice and pepper",
        "main",
        "seitan",
        "arroz-integral-cocido",
        "aceite-oliva",
        (("pimiento", 100),),
    ),
    Dish(
        "gambas-arroz",
        "Arroz con gambas",
        "Rice with prawns",
        "main",
        "gambas",
        "arroz-blanco-cocido",
        "aceite-oliva",
        (("pimiento", 80),),
    ),
    # Tentempiés
    Dish(
        "yogur-platano",
        "Yogur proteico con plátano y almendras",
        "Protein yogurt with banana and almonds",
        "snack",
        "yogur-proteinas",
        "platano",
        "almendras",
    ),
    Dish(
        "tostada-pavo",
        "Tostada integral con jamón cocido",
        "Wholemeal toast with cooked ham",
        "snack",
        "jamon-cocido",
        "pan-integral",
        "aceite-oliva",
        (("tomate", 60),),
    ),
    Dish(
        "batido-proteina",
        "Batido de proteína con plátano y cacahuete",
        "Protein shake with banana and peanut butter",
        "snack",
        "proteina-whey",
        "platano",
        "crema-cacahuete",
        (("leche-semidesnatada", 250),),
    ),
    Dish(
        "soja-avena",
        "Bebida de soja con avena y nueces",
        "Soy drink with oats and walnuts",
        "snack",
        "bebida-soja",
        "copos-de-avena",
        "nueces",
        (),
        (DietPattern.VEGAN,),
    ),
    Dish(
        "tempeh-pan",
        "Bocadillo de tempeh",
        "Tempeh sandwich",
        "snack",
        "tempeh",
        "pan-integral",
        "aguacate",
        (("lechuga", 30),),
    ),
)


def kind_of(meal_name: str) -> str:
    """Which family of dishes fits a meal of the plan (names are stored in Spanish)."""
    name = meal_name.lower()
    if "desayuno" in name:
        return "breakfast"
    if name.startswith(("comida", "cena", "almuerzo")):
        return "main"
    return "snack"


def allowed(dish: Dish, diet: DietPattern) -> bool:
    """Whether a dish suits a diet."""
    if dish.only and diet not in dish.only:
        return False
    foods = {dish.protein, dish.carbs, dish.fat, *(food for food, _ in dish.fixed)}
    return not foods & EXCLUDED[diet]


def _limits(food: str) -> tuple[float, float]:
    return LIMITS.get(food, (20.0, 350.0))


def _solve(rows: list[list[float]], target: list[float]) -> list[float] | None:
    """Least squares for up to three unknowns (normal equations, Gaussian elimination)."""
    size = len(rows[0])
    normal = [[sum(row[i] * row[j] for row in rows) for j in range(size)] for i in range(size)]
    right = [
        sum(row[i] * value for row, value in zip(rows, target, strict=True)) for i in range(size)
    ]
    for col in range(size):
        pivot = max(range(col, size), key=lambda r: abs(normal[r][col]))
        if abs(normal[pivot][col]) < 1e-12:
            return None
        normal[col], normal[pivot] = normal[pivot], normal[col]
        right[col], right[pivot] = right[pivot], right[col]
        for r in range(size):
            if r != col:
                factor = normal[r][col] / normal[col][col]
                normal[r] = [a - factor * b for a, b in zip(normal[r], normal[col], strict=True)]
                right[r] -= factor * right[col]
    return [right[i] / normal[i][i] for i in range(size)]


def portions_for(
    dish: Dish, target: Target, foods: Mapping[str, FoodValues]
) -> tuple[Portion, ...]:
    """Grams of each food so the dish brings the meal's protein, carbs and fat."""
    fixed = [Portion(food, grams) for food, grams in dish.fixed]
    left = [target.protein, target.carbs, target.fat]
    for item in fixed:
        values = foods[item.food]
        left[0] -= values.protein * item.grams / 100
        left[1] -= values.carbs * item.grams / 100
        left[2] -= values.fat * item.grams / 100
    variable = [dish.protein, dish.carbs, dish.fat]
    columns = {
        food: [foods[food].protein / 100, foods[food].carbs / 100, foods[food].fat / 100]
        for food in variable
    }
    pinned: dict[str, float] = {}
    for _ in range(len(variable)):
        free = [food for food in variable if food not in pinned]
        if not free:
            break
        goal = list(left)
        for food, grams in pinned.items():
            goal = [g - c * grams for g, c in zip(goal, columns[food], strict=True)]
        rows = [[columns[food][macro] for food in free] for macro in range(3)]
        solved = _solve(rows, goal)
        if solved is None:
            for food in free:
                pinned[food] = _limits(food)[0]
            break
        worst = None
        for food, grams in zip(free, solved, strict=True):
            low, high = _limits(food)
            if grams < low or grams > high:
                excess = (low - grams) if grams < low else (grams - high)
                if worst is None or excess > worst[1]:
                    worst = (food, excess, low if grams < low else high)
        if worst is None:
            pinned.update(dict(zip(free, solved, strict=True)))
            break
        pinned[worst[0]] = worst[2]
    served = []
    for food in variable:
        grams = pinned.get(food, _limits(food)[0])
        if food == "huevo":
            grams = max(1, round(grams / EGG_GRAMS)) * EGG_GRAMS
        else:
            grams = 5 * round(grams / 5)
        if grams > 0:
            served.append(Portion(food, float(grams)))
    return (*served, *fixed)


def plate(dish: Dish, target: Target, foods: Mapping[str, FoodValues]) -> Plate:
    """Serve a dish for a meal and add up what it brings."""
    portions = portions_for(dish, target, foods)

    def total(attribute: str) -> float:
        return sum(getattr(foods[p.food], attribute) * p.grams / 100 for p in portions)

    return Plate(
        target=target,
        dish=dish,
        portions=portions,
        kcal=total("kcal"),
        protein=total("protein"),
        carbs=total("carbs"),
        fat=total("fat"),
    )


def week(
    targets: Sequence[Target],
    diet: DietPattern,
    foods: Mapping[str, FoodValues],
    seed: int,
    days: int = 7,
) -> list[list[Plate]]:
    """``days`` days of plates; dishes rotate so no day repeats the one before."""
    rng = random.Random(seed)
    by_kind: dict[str, list[Dish]] = {}
    for kind in ("breakfast", "main", "snack"):
        options = [dish for dish in DISHES if dish.kind == kind and allowed(dish, diet)]
        rng.shuffle(options)
        by_kind[kind] = options
    menu = []
    used: dict[str, int] = {}
    for _day in range(days):
        plates = []
        for target in targets:
            kind = kind_of(target.name)
            options = by_kind[kind] or by_kind["main"]
            index = used.get(kind, 0)
            used[kind] = index + 1
            plates.append(plate(options[index % len(options)], target, foods))
        menu.append(plates)
    return menu


def shopping_list(menu: Sequence[Sequence[Plate]]) -> dict[str, float]:
    """Total grams of each food over the menu."""
    totals: dict[str, float] = {}
    for plates in menu:
        for served in plates:
            for portion in served.portions:
                totals[portion.food] = totals.get(portion.food, 0) + portion.grams
    return totals
