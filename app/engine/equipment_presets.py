"""Default equipment per training location.

The questionnaire pre-selects these codes when the user picks a location and
lets them adjust the list. The routine generator and the catalogue coverage
tests use the same presets, so a change here is reflected everywhere.
"""

from __future__ import annotations

from app.engine.enums import TrainingLocation

BODYWEIGHT_ONLY: frozenset[str] = frozenset({"body_only"})

HOME_EQUIPMENT: frozenset[str] = BODYWEIGHT_ONLY | {
    "dumbbells",
    "kettlebell",
    "resistance_bands",
    "pull_up_bar",
    "flat_bench",
}

BASIC_GYM: frozenset[str] = HOME_EQUIPMENT | {
    "barbell",
    "ez_bar",
    "incline_bench",
    "squat_rack",
    "dip_station",
    "cable_machine",
    "lat_pulldown",
    "seated_row_machine",
    "leg_press",
    "leg_extension",
    "leg_curl",
    "smith_machine",
    "plyo_box",
}

FULL_GYM: frozenset[str] = BASIC_GYM | {
    "trap_bar",
    "medicine_ball",
    "back_extension_bench",
    "ab_wheel",
    "stability_ball",
    "suspension_trainer",
    "hack_squat",
    "chest_press_machine",
    "shoulder_press_machine",
    "pec_deck",
    "calf_raise_machine",
    "hip_thrust_machine",
    "hip_abductor_adductor_machine",
    "arm_curl_machine",
    "cardio_machine",
}

EQUIPMENT_PRESETS: dict[TrainingLocation, frozenset[str]] = {
    TrainingLocation.FULL_GYM: FULL_GYM,
    TrainingLocation.BASIC_GYM: BASIC_GYM,
    TrainingLocation.HOME_EQUIPMENT: HOME_EQUIPMENT,
    TrainingLocation.HOME_BODYWEIGHT: BODYWEIGHT_ONLY,
}


def preset_for(location: TrainingLocation | str) -> frozenset[str]:
    """Equipment codes assumed for ``location``."""
    return EQUIPMENT_PRESETS[TrainingLocation(location)]
