"""End-to-end routine generation for many profiles, checking the §3.7 guarantees."""

from __future__ import annotations

import itertools
import json
from typing import Any

import pytest

from app.engine.enums import (
    Goal,
    InjuryArea,
    MovementPattern,
    MuscleGroup,
    Severity,
    TrainingExperience,
    TrainingLocation,
)
from app.engine.equipment_presets import EQUIPMENT_PRESETS
from app.engine.messages import render_all
from app.engine.routines.catalog import is_contraindicated
from app.engine.routines.generator import (
    PULL_PATTERNS,
    PUSH_PATTERNS,
    REQUIRED_PATTERNS,
    build_routine,
)
from app.engine.routines.types import InjuryInput, RoutineInputs, RoutinePlan
from tests.routine_factories import BY_SLUG, CATALOGUE, make_routine_inputs

GRID: list[dict[str, Any]] = [
    {
        "training_experience": experience,
        "training_days_per_week": days,
        "training_location": location,
    }
    for experience, days, location in itertools.product(
        list(TrainingExperience), (2, 3, 4, 5, 6), list(TrainingLocation)
    )
]
ALL_INJURIES = tuple(InjuryInput(area, Severity.SEVERE) for area in InjuryArea)


def _assert_common_invariants(inputs: RoutineInputs, plan: RoutinePlan) -> None:
    assert plan.status == "ok"
    assert len(plan.days) == min(inputs.training_days_per_week, 6)
    assert plan.split_type is not None
    assert plan.cardio is not None
    for day in plan.days:
        assert day.exercises, day.name
        slugs = [exercise.slug for exercise in day.exercises]
        assert len(slugs) == len(set(slugs)), "no exercise twice in a day"
        for exercise in day.exercises:
            info = BY_SLUG[exercise.slug]
            assert info.equipment <= inputs.equipment, exercise.slug
            assert not is_contraindicated(info, inputs.injuries), exercise.slug
            assert exercise.slug not in inputs.disliked_exercises
            assert 1 <= exercise.sets <= 12
            assert 1 <= exercise.rep_min <= exercise.rep_max <= 20
            assert 0 <= exercise.rir_end <= exercise.rir_start <= 6
            assert 15 <= exercise.rest_seconds <= 600
            assert exercise.load_increment_kg >= 0
        over_budget = day.estimated_minutes > inputs.session_minutes * 1.05
        too_long_noted = any(
            note.code == "routine.session_too_long" and note.params["day"] == day.name
            for note in plan.notes
        )
        assert not over_budget or too_long_noted, (day.name, day.estimated_minutes)
    if plan.push_sets:
        assert plan.pull_to_push_ratio >= 0.85 or any(
            note.code == "routine.push_pull_unbalanced" for note in plan.notes
        )
    json.dumps(plan.to_dict())
    render_all(plan.all_notes())


@pytest.mark.parametrize(
    "overrides",
    GRID,
    ids=lambda o: (
        f"{o['training_experience'].value}-{o['training_days_per_week']}d-{o['training_location'].value}"
    ),
)
def test_grid_of_profiles_produces_valid_routines(overrides: dict[str, Any]) -> None:
    inputs = make_routine_inputs(**overrides)
    plan = build_routine(inputs, CATALOGUE)
    _assert_common_invariants(inputs, plan)
    present = {exercise.pattern for day in plan.days for exercise in day.exercises}
    location = overrides["training_location"]
    days = overrides["training_days_per_week"]
    if location in (TrainingLocation.FULL_GYM, TrainingLocation.BASIC_GYM) and days >= 3:
        for pattern in REQUIRED_PATTERNS:
            assert pattern in present or any(
                note.code in ("routine.pattern_trimmed", "routine.pattern_not_scheduled")
                and note.params["pattern"] == pattern.value
                for note in plan.notes
            ), pattern
        low = [entry for entry in plan.volume if entry.status == "low"]
        assert len(low) <= 2, [(e.muscle.value, e.planned_sets, e.target_min) for e in low]
    if location is TrainingLocation.HOME_BODYWEIGHT:
        assert any(
            note.code == "routine.pattern_missing"
            and note.params["pattern"] == MovementPattern.VERTICAL_PULL.value
            for note in plan.notes
        )


def test_generation_is_deterministic() -> None:
    inputs = make_routine_inputs(training_days_per_week=5)
    assert build_routine(inputs, CATALOGUE).to_dict() == build_routine(inputs, CATALOGUE).to_dict()


def test_injuries_exclude_contraindicated_exercises_and_bias_pulling() -> None:
    inputs = make_routine_inputs(
        training_days_per_week=4,
        injuries=(
            InjuryInput(InjuryArea.SHOULDER, Severity.MODERATE),
            InjuryInput(InjuryArea.LOWER_BACK, Severity.MODERATE),
        ),
    )
    plan = build_routine(inputs, CATALOGUE)
    _assert_common_invariants(inputs, plan)
    slugs = {exercise.slug for day in plan.days for exercise in day.exercises}
    assert "barbell-squat" not in slugs
    assert "standing-military-press" not in slugs
    assert "barbell-deadlift" not in slugs
    assert any(note.code == "routine.pull_bias" for note in plan.notes)
    assert plan.pull_to_push_ratio >= 1.15


def test_all_injuries_severe_still_yields_something_or_explains() -> None:
    inputs = make_routine_inputs(injuries=ALL_INJURIES, training_days_per_week=3)
    plan = build_routine(inputs, CATALOGUE)
    if plan.is_blocked:
        assert plan.blocked_reasons[0].code == "routine.nothing_possible"
        return
    _assert_common_invariants(inputs, plan)
    blocked_notes = [
        note for note in plan.notes if note.code == "routine.pattern_blocked_by_injury"
    ]
    assert blocked_notes


def test_priority_muscles_receive_more_volume() -> None:
    plain = build_routine(make_routine_inputs(training_days_per_week=5), CATALOGUE)
    prioritised = build_routine(
        make_routine_inputs(training_days_per_week=5, priority_muscles=(MuscleGroup.GLUTES,)),
        CATALOGUE,
    )

    def glute_sets(plan: RoutinePlan) -> float:
        return next(e.planned_sets for e in plan.volume if e.muscle is MuscleGroup.GLUTES)

    assert glute_sets(prioritised) >= glute_sets(plain)
    assert next(e for e in prioritised.volume if e.muscle is MuscleGroup.GLUTES).is_priority
    assert any(note.code == "routine.priority_applied" for note in prioritised.notes)


def test_priority_without_a_template_slot_adds_an_exercise() -> None:
    inputs = make_routine_inputs(training_days_per_week=2, priority_muscles=(MuscleGroup.CALVES,))
    plan = build_routine(inputs, CATALOGUE)
    assert any(
        exercise.primary is MuscleGroup.CALVES for day in plan.days for exercise in day.exercises
    )
    assert any(note.code == "routine.priority_slot_added" for note in plan.notes)


def test_short_sessions_are_trimmed_and_long_ones_are_not() -> None:
    short = build_routine(
        make_routine_inputs(training_days_per_week=2, session_minutes=25), CATALOGUE
    )
    assert any(note.code == "routine.time_trimmed" for note in short.notes)
    assert all(day.estimated_minutes <= 25 * 1.05 for day in short.days) or any(
        note.code == "routine.session_too_long" for note in short.notes
    )
    assert any(note.code == "routine.volume_scaled_by_time" for note in short.notes)

    long = build_routine(
        make_routine_inputs(training_days_per_week=4, session_minutes=120), CATALOGUE
    )
    assert not any(note.code == "routine.session_too_long" for note in long.notes)
    assert not any(note.code == "routine.volume_scaled_by_time" for note in long.notes)


def test_preferred_and_disliked_exercises_are_honoured() -> None:
    inputs = make_routine_inputs(
        preferred_exercises=frozenset({"dumbbell-bench-press"}),
        disliked_exercises=frozenset({"barbell-squat", "barbell-bench-press-medium-grip"}),
    )
    plan = build_routine(inputs, CATALOGUE)
    slugs = {exercise.slug for day in plan.days for exercise in day.exercises}
    assert "dumbbell-bench-press" in slugs
    assert "barbell-squat" not in slugs
    assert "barbell-bench-press-medium-grip" not in slugs


def test_performance_goal_uses_heavy_ranges_on_main_lifts() -> None:
    plan = build_routine(make_routine_inputs(goal=Goal.PERFORMANCE), CATALOGUE)
    mains = [exercise for day in plan.days for exercise in day.exercises if exercise.role == "main"]
    assert mains
    assert all((exercise.rep_min, exercise.rep_max) == (3, 6) for exercise in mains)


def test_seven_days_are_capped_and_zero_days_are_blocked() -> None:
    capped = build_routine(make_routine_inputs(training_days_per_week=7), CATALOGUE)
    assert len(capped.days) == 6
    assert any(note.code == "routine.days_capped" for note in capped.notes)
    blocked = build_routine(make_routine_inputs(training_days_per_week=0), CATALOGUE)
    assert blocked.is_blocked
    assert blocked.blocked_reasons[0].code == "routine.no_days"
    assert blocked.all_notes()[0].code == "routine.no_days"


def test_empty_catalogue_is_blocked() -> None:
    plan = build_routine(make_routine_inputs(), [])
    assert plan.is_blocked
    assert plan.blocked_reasons[0].code == "routine.nothing_possible"


def test_beginner_at_home_gets_beginner_level_or_a_relaxation_note() -> None:
    inputs = make_routine_inputs(
        training_experience=TrainingExperience.NONE,
        training_location=TrainingLocation.HOME_EQUIPMENT,
        training_days_per_week=3,
    )
    plan = build_routine(inputs, CATALOGUE)
    for day in plan.days:
        for exercise in day.exercises:
            info = BY_SLUG[exercise.slug]
            relaxed = any(note.code == "routine.level_relaxed" for note in exercise.notes)
            assert info.level.value == "beginner" or relaxed, exercise.slug


def test_push_pull_counts_match_the_days() -> None:
    plan = build_routine(make_routine_inputs(training_days_per_week=6), CATALOGUE)
    push = sum(e.sets for d in plan.days for e in d.exercises if e.pattern in PUSH_PATTERNS)
    pull = sum(e.sets for d in plan.days for e in d.exercises if e.pattern in PULL_PATTERNS)
    assert (plan.push_sets, plan.pull_sets) == (push, pull)
    assert plan.pull_to_push_ratio == round(pull / push, 2)
    assert EQUIPMENT_PRESETS[TrainingLocation.FULL_GYM] >= {"barbell", "cable_machine"}
