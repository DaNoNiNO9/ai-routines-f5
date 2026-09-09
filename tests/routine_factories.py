"""Builders for routine-generator inputs and the shared catalogue."""

from __future__ import annotations

from typing import Any

from app.engine.enums import Goal, Sex, TrainingExperience, TrainingLocation
from app.engine.equipment_presets import EQUIPMENT_PRESETS
from app.engine.routines.catalog import exercise_from_dict
from app.engine.routines.types import ExerciseInfo, RoutineInputs
from app.seeds.loaders import EXERCISES_FILE, load_json_list

CATALOGUE: list[ExerciseInfo] = [exercise_from_dict(row) for row in load_json_list(EXERCISES_FILE)]
BY_SLUG: dict[str, ExerciseInfo] = {exercise.slug: exercise for exercise in CATALOGUE}

ROUTINE_DEFAULTS: dict[str, Any] = {
    "sex": Sex.MALE,
    "goal": Goal.FAT_LOSS,
    "training_experience": TrainingExperience.MONTHS_6_TO_24,
    "training_days_per_week": 4,
    "session_minutes": 60,
    "training_location": TrainingLocation.FULL_GYM,
    "equipment": EQUIPMENT_PRESETS[TrainingLocation.FULL_GYM],
    "weight_kg": 85.0,
    "daily_steps": 7000,
}


def make_routine_inputs(**overrides: Any) -> RoutineInputs:
    """A full-gym intermediate profile unless overridden; ``training_location`` sets the preset."""
    values = {**ROUTINE_DEFAULTS, **overrides}
    if "training_location" in overrides and "equipment" not in overrides:
        values["equipment"] = EQUIPMENT_PRESETS[overrides["training_location"]]
    return RoutineInputs(**values)
