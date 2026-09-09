"""Macronutrients, carb floor, hydration, meal distribution and carb cycling."""

from __future__ import annotations

import pytest

from app.engine.body_composition import assess_body_composition
from app.engine.enums import (
    Aggressiveness,
    BodyFatMethod,
    Goal,
    MealTiming,
    Sex,
    TrainingExperience,
    TrainingTime,
)
from app.engine.macros import (
    carb_cycle,
    carb_floor_g,
    compute_macros,
    fat_target_g,
    hydration,
    protein_target,
)
from app.engine.meals import distribute_meals, workout_meal_indices
from app.engine.types import Macros
from tests.engine_factories import make_inputs


def _macros(**values: int) -> Macros:
    defaults = {
        "calories": 2000,
        "protein_g": 160,
        "fat_g": 60,
        "carbs_g": 200,
        "fiber_g": 28,
        "protein_per_kg": 2.0,
        "protein_basis": "bodyweight",
        "fat_fraction": 0.27,
        "carb_floor_g": 120,
        "calories_added_for_carb_floor": 0,
    }
    return Macros(**{**defaults, **values})


def test_protein_by_goal_experience_and_aggressiveness() -> None:
    inputs = make_inputs(weight_kg=80)
    body = assess_body_composition(inputs)
    grams, per_kg, basis = protein_target(inputs, body, "deficit")
    assert (per_kg, basis) == (2.0, "bodyweight")
    assert grams == pytest.approx(160)

    advanced = make_inputs(
        weight_kg=80,
        training_experience=TrainingExperience.YEARS_2_TO_5,
        aggressiveness=Aggressiveness.AGGRESSIVE,
    )
    _, per_kg, _ = protein_target(advanced, body, "deficit")
    assert per_kg == 2.2  # 2.0 + 0.2 + 0.2 capped at 2.2

    keep = make_inputs(weight_kg=80, goal=Goal.MAINTENANCE)
    assert protein_target(keep, body, "maintenance")[1] == 1.6


def test_protein_uses_lean_mass_when_body_fat_is_high_and_reliable() -> None:
    inputs = make_inputs(
        sex=Sex.FEMALE,
        weight_kg=90,
        height_cm=165,
        body_fat_pct=40,
        body_fat_method=BodyFatMethod.SCALE,
    )
    body = assess_body_composition(inputs)
    grams, per_kg, basis = protein_target(inputs, body, "deficit")
    assert basis == "lean"
    assert grams == pytest.approx(54 * 2.6, abs=0.5)
    assert per_kg == pytest.approx(1.56, abs=0.01)


def test_lean_basis_never_drops_below_point_eight_per_kg() -> None:
    inputs = make_inputs(
        weight_kg=300, height_cm=180, body_fat_pct=68, body_fat_method=BodyFatMethod.DEXA
    )
    body = assess_body_composition(inputs)
    grams, per_kg, basis = protein_target(inputs, body, "deficit")
    assert basis == "lean"
    assert per_kg >= 0.8
    assert grams >= 240


def test_fat_target_bounded_by_20_and_35_percent() -> None:
    assert fat_target_g(2000, 80) == pytest.approx(64)
    assert fat_target_g(3600, 80) == pytest.approx(0.20 * 3600 / 9)
    assert fat_target_g(1300, 80) == pytest.approx(0.35 * 1300 / 9)


def test_carb_floor_by_training_frequency() -> None:
    assert carb_floor_g(80, 4) == 120
    assert carb_floor_g(50, 2) == 100
    assert carb_floor_g(90, 5) == 180


def test_macros_add_up_to_calories() -> None:
    inputs = make_inputs()
    body = assess_body_composition(inputs)
    macros = compute_macros(inputs, body, 2000, "deficit")
    energy = 4 * macros.protein_g + 4 * macros.carbs_g + 9 * macros.fat_g
    assert abs(energy - macros.calories) <= 12
    assert macros.calories == 2000
    assert macros.fiber_g == 28
    assert macros.carbs_g >= macros.carb_floor_g
    assert 0.2 <= macros.fat_fraction <= 0.35


def test_carb_floor_reduces_the_deficit_instead_of_zeroing_carbs() -> None:
    inputs = make_inputs(
        weight_kg=100, height_cm=180, training_days_per_week=5, neck_cm=42, waist_cm=100
    )
    body = assess_body_composition(inputs)
    macros = compute_macros(inputs, body, 1500, "deficit")
    assert macros.carb_floor_g == 200
    assert macros.carbs_g >= 200
    assert macros.calories > 1500
    assert macros.calories_added_for_carb_floor > 0
    assert macros.fat_g == pytest.approx(60, abs=1)  # lowered to the 0.6 g/kg minimum
    codes = [note.code for note in macros.notes]
    assert "macros.fat_lowered_for_carbs" in codes
    assert "macros.deficit_reduced_for_carbs" in codes


def test_carb_floor_note_names_calories_raised_outside_a_deficit() -> None:
    inputs = make_inputs(
        weight_kg=100, height_cm=180, training_days_per_week=5, goal=Goal.MAINTENANCE
    )
    body = assess_body_composition(inputs)
    macros = compute_macros(inputs, body, 1500, "maintenance")
    assert any(note.code == "macros.calories_raised_for_carbs" for note in macros.notes)


def test_hydration_baseline_and_training_extra() -> None:
    plain = hydration(70, 60)
    assert (plain.base_ml, plain.per_session_ml, plain.training_day_ml) == (2450, 500, 2950)
    assert hydration(70, 90).per_session_ml == 750
    assert hydration(70, 0).per_session_ml == 0


@pytest.mark.parametrize(
    ("meals", "time", "expected"),
    [
        (4, TrainingTime.MIDDAY, (1, 2)),
        (1, TrainingTime.MORNING, (None, 0)),
        (2, TrainingTime.EVENING, (0, 1)),
        (5, TrainingTime.NONE, (None, None)),
        (3, TrainingTime.MORNING, (0, 1)),
        (6, TrainingTime.EVENING, (4, 5)),
    ],
)
def test_workout_meal_indices(
    meals: int, time: TrainingTime, expected: tuple[int | None, int | None]
) -> None:
    assert workout_meal_indices(meals, time) == expected


def test_meals_sum_exactly_and_favour_carbs_around_training() -> None:
    slots, notes = distribute_meals(_macros(), 4, TrainingTime.EVENING, 80)
    assert [slot.name for slot in slots] == ["Desayuno", "Comida", "Merienda", "Cena"]
    assert [slot.timing for slot in slots] == [
        MealTiming.REGULAR,
        MealTiming.REGULAR,
        MealTiming.PRE_WORKOUT,
        MealTiming.POST_WORKOUT,
    ]
    assert [slot.carbs_g for slot in slots] == [40, 40, 60, 60]
    assert [slot.fat_g for slot in slots] == [19, 19, 11, 11]
    assert sum(slot.protein_g for slot in slots) == 160
    assert sum(slot.calories for slot in slots) == sum(
        4 * s.protein_g + 4 * s.carbs_g + 9 * s.fat_g for s in slots
    )
    assert notes == ()


def test_too_many_meals_for_the_protein_triggers_a_note() -> None:
    slots, notes = distribute_meals(_macros(protein_g=100), 6, TrainingTime.NONE, 80)
    assert len(slots) == 6
    assert notes[0].code == "meals.protein_per_meal_low"
    assert notes[0].params["recommended_meals"] == 3


def test_carb_cycle_keeps_the_weekly_average() -> None:
    cycle = carb_cycle(_macros(), training_days=4)
    assert cycle is not None
    assert cycle.high_day.carbs_g == 250
    assert cycle.low_day.carbs_g == 133
    assert cycle.weekly_average_carbs_g == pytest.approx(200, abs=0.5)
    assert cycle.high_day.protein_g == cycle.low_day.protein_g == 160
    assert cycle.high_day.calories > cycle.low_day.calories


def test_carb_cycle_low_day_never_under_the_floor() -> None:
    cycle = carb_cycle(_macros(carbs_g=140, carb_floor_g=130), training_days=5)
    assert cycle is not None
    assert cycle.low_day.carbs_g == 130
    assert cycle.high_day.carbs_g == 144
    assert any(note.code == "cycle.low_day_at_floor" for note in cycle.notes)


def test_carb_cycle_needs_both_training_and_rest_days() -> None:
    assert carb_cycle(_macros(), training_days=7) is None
    assert carb_cycle(_macros(), training_days=0) is None
