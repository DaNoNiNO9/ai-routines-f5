"""Synthetic weight and intake series for the adjustment-engine tests.

The body model is deliberately simple: weight changes by (intake - TDEE) / 7700
per day, the true TDEE drops a little as weight is lost (metabolic
adaptation) and the scale adds Gaussian noise on top of the true weight.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

from app.engine.adjustment.types import AdjustmentInputs, IntakePoint, WeightPoint
from app.engine.enums import Goal, Sex

KCAL_PER_KG = 7700
START = date(2026, 1, 5)


def simulate(
    start_weight: float,
    true_tdee: float,
    intake: float,
    days: int,
    *,
    start: date = START,
    noise_sd: float = 0.4,
    seed: int = 1,
    adaptation_per_kg: float = 25.0,
    adherence: float | None = 100.0,
    log_every_day: bool = True,
) -> tuple[list[WeightPoint], list[IntakePoint], float, float]:
    """Return logged weights, logged intakes, and the true TDEE and true weight at the end."""
    rng = random.Random(seed)
    weight_true = start_weight
    weights: list[WeightPoint] = []
    intakes: list[IntakePoint] = []
    tdee_now = true_tdee
    for offset in range(days):
        day = start + timedelta(days=offset)
        tdee_now = true_tdee - adaptation_per_kg * (start_weight - weight_true)
        if log_every_day or rng.random() < 0.8:
            weights.append(WeightPoint(day, round(weight_true + rng.gauss(0, noise_sd), 2)))
            intakes.append(IntakePoint(day, intake + rng.gauss(0, 60), adherence))
        weight_true += (intake - tdee_now) / KCAL_PER_KG
    return weights, intakes, tdee_now, weight_true


def make_adjustment_inputs(
    weights: list[WeightPoint], intakes: list[IntakePoint], **overrides: Any
) -> AdjustmentInputs:
    """Inputs for a review on the day after the last log."""
    last_day = max(point.day for point in weights) if weights else START
    values: dict[str, Any] = {
        "sex": Sex.MALE,
        "goal": Goal.FAT_LOSS,
        "mode": "deficit",
        "plan_calories": 2200,
        "plan_started_on": START,
        "expected_weekly_change_kg": -0.45,
        "bmr_kcal": 1800,
        "theoretical_tdee_kcal": 2700,
        "weights": tuple(weights),
        "intakes": tuple(intakes),
        "today": last_day,
        "steps_target": 8000,
    }
    values.update(overrides)
    return AdjustmentInputs(**values)
