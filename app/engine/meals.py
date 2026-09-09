"""Distribution of the daily macros across meals.

- Protein is split evenly; meals of at least 0.4 g/kg make the most of muscle
  protein synthesis (Schoenfeld & Aragon 2018, JISSN 15:10), so the engine
  warns when there are too many meals for the protein target.
- Carbohydrates are weighted towards the meals before and after training
  (1.5x) and fat away from them (0.6x), following the timing guidance of the
  ISSN position stand on nutrient timing (Kerksick et al. 2017).
- Grams are distributed with the largest-remainder method so the meals add up
  exactly to the daily totals.
"""

from __future__ import annotations

from app.engine.enums import MealTiming, TrainingTime
from app.engine.types import Macros, MealSlot, Note

PROTEIN_PER_MEAL_TARGET_PER_KG = 0.4
CARB_WORKOUT_WEIGHT = 1.5
FAT_WORKOUT_WEIGHT = 0.6

MEAL_NAMES: dict[int, list[str]] = {
    1: ["Comida"],
    2: ["Comida", "Cena"],
    3: ["Desayuno", "Comida", "Cena"],
    4: ["Desayuno", "Comida", "Merienda", "Cena"],
    5: ["Desayuno", "Media mañana", "Comida", "Merienda", "Cena"],
    6: ["Desayuno", "Media mañana", "Comida", "Merienda", "Cena", "Recena"],
    7: ["Desayuno", "Media mañana", "Comida", "Merienda", "Cena", "Recena", "Comida extra"],
    8: [
        "Desayuno",
        "Media mañana",
        "Comida",
        "Merienda",
        "Cena",
        "Recena",
        "Comida extra 1",
        "Comida extra 2",
    ],
}


def workout_meal_indices(meals: int, training_time: TrainingTime) -> tuple[int | None, int | None]:
    """Zero-based indices of the pre-workout and post-workout meals (``None`` if not applicable)."""
    if training_time is TrainingTime.NONE or meals < 1:
        return None, None
    if meals == 1:
        return None, 0
    if training_time is TrainingTime.MORNING:
        return 0, 1
    if training_time is TrainingTime.MIDDAY:
        pre = meals // 2 - 1
        return pre, pre + 1
    return meals - 2, meals - 1


def distribute_meals(
    macros: Macros, meals_per_day: int, training_time: TrainingTime, weight_kg: float
) -> tuple[tuple[MealSlot, ...], tuple[Note, ...]]:
    """Split the daily macros into ``meals_per_day`` slots."""
    count = max(1, min(8, meals_per_day))
    pre, post = workout_meal_indices(count, training_time)
    timings = [MealTiming.REGULAR] * count
    if pre is not None:
        timings[pre] = MealTiming.PRE_WORKOUT
    if post is not None:
        timings[post] = MealTiming.POST_WORKOUT

    carb_weights = [CARB_WORKOUT_WEIGHT if t is not MealTiming.REGULAR else 1.0 for t in timings]
    fat_weights = [FAT_WORKOUT_WEIGHT if t is not MealTiming.REGULAR else 1.0 for t in timings]
    protein = _split(macros.protein_g, [1.0] * count)
    carbs = _split(macros.carbs_g, carb_weights)
    fat = _split(macros.fat_g, fat_weights)

    slots = tuple(
        MealSlot(
            position=index + 1,
            name=MEAL_NAMES[count][index],
            timing=timings[index],
            calories=4 * protein[index] + 4 * carbs[index] + 9 * fat[index],
            protein_g=protein[index],
            carbs_g=carbs[index],
            fat_g=fat[index],
        )
        for index in range(count)
    )

    notes: list[Note] = []
    per_meal_target = PROTEIN_PER_MEAL_TARGET_PER_KG * weight_kg
    if macros.protein_g / count < per_meal_target:
        recommended = max(1, int(macros.protein_g // per_meal_target))
        notes.append(
            Note(
                "meals.protein_per_meal_low",
                level="warning",
                params={
                    "per_meal": round(macros.protein_g / count),
                    "recommended_meals": recommended,
                },
            )
        )
    return slots, tuple(notes)


def _split(total: int, weights: list[float]) -> list[int]:
    """Largest-remainder apportionment of ``total`` grams across ``weights``."""
    weight_sum = sum(weights)
    exact = [total * w / weight_sum for w in weights]
    floors = [int(value) for value in exact]
    remainder = total - sum(floors)
    order = sorted(range(len(weights)), key=lambda i: exact[i] - floors[i], reverse=True)
    for index in order[:remainder]:
        floors[index] += 1
    return floors
