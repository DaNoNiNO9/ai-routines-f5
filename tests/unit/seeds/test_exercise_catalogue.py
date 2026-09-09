"""Static checks on the generated exercise catalogue (no database needed)."""

from __future__ import annotations

import re

import pytest

from app.engine.enums import (
    Force,
    InjuryArea,
    Mechanic,
    MovementPattern,
    MuscleGroup,
    Severity,
    TechnicalLevel,
    TrainingLocation,
)
from app.engine.equipment_presets import EQUIPMENT_PRESETS
from app.seeds.loaders import EQUIPMENT_FILE, EXERCISES_FILE, load_json_list
from config import BASE_DIR

EXERCISES = load_json_list(EXERCISES_FILE)
BY_SLUG = {exercise["slug"]: exercise for exercise in EXERCISES}
EQUIPMENT_CODES = {row["code"] for row in load_json_list(EQUIPMENT_FILE)}
STATIC_DIR = BASE_DIR / "app" / "static"
MIN_EXERCISES = 150
MIN_PER_MUSCLE = 2
SLUG_PATTERN = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
LOADED_EQUIPMENT = {
    "barbell",
    "ez_bar",
    "trap_bar",
    "dumbbells",
    "kettlebell",
    "medicine_ball",
    "cable_machine",
    "lat_pulldown",
    "seated_row_machine",
    "smith_machine",
    "leg_press",
    "hack_squat",
    "leg_extension",
    "leg_curl",
    "chest_press_machine",
    "shoulder_press_machine",
    "pec_deck",
    "calf_raise_machine",
    "hip_thrust_machine",
    "hip_abductor_adductor_machine",
    "arm_curl_machine",
    "resistance_bands",
}


def test_catalogue_has_at_least_150_exercises() -> None:
    assert len(EXERCISES) >= MIN_EXERCISES


def test_slugs_are_unique_and_well_formed() -> None:
    assert len(BY_SLUG) == len(EXERCISES)
    for slug in BY_SLUG:
        assert SLUG_PATTERN.fullmatch(slug), slug


def test_every_entry_uses_the_domain_vocabulary() -> None:
    for exercise in EXERCISES:
        slug = exercise["slug"]
        assert exercise["name_es"], slug
        assert exercise["name_en"], slug
        MuscleGroup(exercise["primary_muscle"])
        MovementPattern(exercise["movement_pattern"])
        Mechanic(exercise["mechanic"])
        Force(exercise["force"])
        TechnicalLevel(exercise["technical_level"])
        for muscle in exercise["secondary_muscles"]:
            MuscleGroup(muscle)
        assert exercise["primary_muscle"] not in exercise["secondary_muscles"], slug
        assert isinstance(exercise["is_unilateral"], bool), slug
        assert "instructions_en" in exercise, slug
    without_instructions = [e["slug"] for e in EXERCISES if not e["instructions_en"]]
    assert len(without_instructions) <= len(EXERCISES) * 0.03, without_instructions


def test_equipment_codes_exist_and_bodyweight_flag_is_consistent() -> None:
    for exercise in EXERCISES:
        codes = set(exercise["equipment"])
        assert codes, exercise["slug"]
        assert codes <= EQUIPMENT_CODES, (exercise["slug"], codes - EQUIPMENT_CODES)
        expected_bodyweight = not (codes & LOADED_EQUIPMENT)
        assert exercise["is_bodyweight"] is expected_bodyweight, exercise["slug"]


def test_alternatives_point_to_other_exercises_with_same_pattern_and_muscle() -> None:
    with_alternatives = 0
    for exercise in EXERCISES:
        priorities = [alt["priority"] for alt in exercise["alternatives"]]
        assert priorities == sorted(set(priorities)), exercise["slug"]
        for alt in exercise["alternatives"]:
            target = BY_SLUG[alt["slug"]]
            assert target is not exercise
            assert target["movement_pattern"] == exercise["movement_pattern"]
            assert target["primary_muscle"] == exercise["primary_muscle"]
            assert alt["reason"]
        with_alternatives += bool(exercise["alternatives"])
    assert with_alternatives / len(EXERCISES) > 0.9


def test_contraindications_are_well_formed() -> None:
    for exercise in EXERCISES:
        seen: set[str] = set()
        for item in exercise["contraindications"]:
            InjuryArea(item["area"])
            Severity(item["min_severity"])
            assert item["area"] not in seen, (exercise["slug"], item["area"])
            seen.add(item["area"])


def test_images_are_local_and_video_links_point_to_youtube() -> None:
    for exercise in EXERCISES:
        assert len(exercise["images"]) == 2, exercise["slug"]
        assert exercise["image_path"] == exercise["images"][0]
        for relative in exercise["images"]:
            assert (STATIC_DIR / relative).is_file(), relative
        assert exercise["video_url"].startswith("https://www.youtube.com/results?search_query=")


@pytest.mark.parametrize("location", list(TrainingLocation))
def test_every_movement_pattern_is_covered_per_location(location: TrainingLocation) -> None:
    preset = EQUIPMENT_PRESETS[location]
    required = set(MovementPattern)
    minimum = 2
    if location is TrainingLocation.HOME_BODYWEIGHT:
        required.discard(MovementPattern.VERTICAL_PULL)  # needs at least a pull-up bar
        minimum = 1
    for pattern in required:
        available = [
            exercise["slug"]
            for exercise in EXERCISES
            if exercise["movement_pattern"] == pattern and set(exercise["equipment"]) <= preset
        ]
        assert len(available) >= minimum, (location, pattern, available)


def test_every_pattern_has_a_beginner_option_at_home() -> None:
    preset = EQUIPMENT_PRESETS[TrainingLocation.HOME_EQUIPMENT]
    for pattern in MovementPattern:
        beginner = [
            exercise["slug"]
            for exercise in EXERCISES
            if exercise["movement_pattern"] == pattern
            and exercise["technical_level"] == TechnicalLevel.BEGINNER
            and set(exercise["equipment"]) <= preset
        ]
        assert beginner, pattern


def test_every_muscle_group_has_primary_exercises() -> None:
    for muscle in MuscleGroup:
        count = sum(1 for exercise in EXERCISES if exercise["primary_muscle"] == muscle)
        assert count >= MIN_PER_MUSCLE, muscle


def test_images_are_reasonably_small() -> None:
    sizes = [
        (STATIC_DIR / relative).stat().st_size
        for exercise in EXERCISES
        for relative in exercise["images"]
    ]
    assert max(sizes) < 120_000
    assert sum(sizes) < 15_000_000
