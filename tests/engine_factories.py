"""Builders for engine inputs with sensible defaults."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.engine.enums import (
    Goal,
    JobActivity,
    Sex,
    TrainingExperience,
    TrainingTime,
)
from app.engine.types import NutritionInputs

TODAY = date(2026, 9, 9)

INPUT_DEFAULTS: dict[str, Any] = {
    "sex": Sex.MALE,
    "age": 30,
    "height_cm": 180.0,
    "weight_kg": 85.0,
    "goal": Goal.FAT_LOSS,
    "training_days_per_week": 4,
    "session_minutes": 60,
    "training_experience": TrainingExperience.MONTHS_6_TO_24,
    "job_activity": JobActivity.SEDENTARY,
    "sleep_hours": 7.5,
    "stress_level": 2,
    "meals_per_day": 4,
    "neck_cm": 40.0,
    "waist_cm": 90.0,
    "daily_steps": 7000,
    "training_time": TrainingTime.EVENING,
    "today": TODAY,
}


def make_inputs(**overrides: Any) -> NutritionInputs:
    """A valid male fat-loss profile unless overridden."""
    return NutritionInputs(**{**INPUT_DEFAULTS, **overrides})


def make_female_inputs(**overrides: Any) -> NutritionInputs:
    """A valid female profile (165 cm, 60 kg, Navy circumferences)."""
    values: dict[str, Any] = {
        **INPUT_DEFAULTS,
        "sex": Sex.FEMALE,
        "age": 28,
        "height_cm": 165.0,
        "weight_kg": 60.0,
        "neck_cm": 33.0,
        "waist_cm": 74.0,
        "hip_cm": 96.0,
    }
    values.update(overrides)
    return NutritionInputs(**values)
