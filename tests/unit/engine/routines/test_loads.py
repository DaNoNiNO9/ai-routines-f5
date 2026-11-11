"""Starting loads and the adjustment between sets."""

from __future__ import annotations

import pytest

from app.engine.enums import (
    Force,
    Mechanic,
    MovementPattern,
    MuscleGroup,
    Sex,
    TechnicalLevel,
    TrainingExperience,
)
from app.engine.routines.loads import loads_weight, next_set_load, round_load, starting_load
from app.engine.routines.types import ExerciseInfo


def _exercise(
    equipment: set[str],
    pattern: MovementPattern = MovementPattern.HORIZONTAL_PUSH,
    *,
    mechanic: Mechanic = Mechanic.COMPOUND,
    unilateral: bool = False,
    bodyweight: bool = False,
) -> ExerciseInfo:
    return ExerciseInfo(
        slug="x",
        name="x",
        primary=MuscleGroup.CHEST,
        secondary=(),
        pattern=pattern,
        mechanic=mechanic,
        force=Force.PUSH,
        level=TechnicalLevel.BEGINNER,
        equipment=frozenset(equipment),
        is_unilateral=unilateral,
        is_bodyweight=bodyweight,
    )


BENCH = _exercise({"barbell", "flat_bench"})
MALE, FEMALE = Sex.MALE, Sex.FEMALE
INTERMEDIATE = TrainingExperience.YEARS_2_TO_5


def test_bench_press_for_an_intermediate_man_is_a_sensible_working_load() -> None:
    # 84 kg x 0.75 x 1.35 x 0.65 = 55.3 -> 55 kg on a 20 kg bar with 2.5 kg steps
    assert starting_load(BENCH, MALE, 84, INTERMEDIATE) == 55.0


def test_starting_loads_grow_with_experience_and_never_go_under_the_bar() -> None:
    loads = [starting_load(BENCH, MALE, 84, level) for level in TrainingExperience]
    assert loads == sorted(loads)
    assert starting_load(BENCH, FEMALE, 50, TrainingExperience.NONE) == 20.0


def test_women_start_lighter_more_so_on_the_upper_body() -> None:
    squat = _exercise({"barbell", "squat_rack"}, MovementPattern.KNEE_DOMINANT)
    for exercise, factor in ((BENCH, 0.6), (squat, 0.7)):
        male = starting_load(exercise, MALE, 80, INTERMEDIATE)
        female = starting_load(exercise, FEMALE, 80, INTERMEDIATE)
        assert male is not None
        assert female is not None
        assert female == pytest.approx(male * factor, abs=2.5)


def test_dumbbells_are_per_hand_and_unilateral_work_halves_again() -> None:
    press = _exercise({"dumbbells", "flat_bench"})
    one_arm = _exercise({"dumbbells"}, MovementPattern.HORIZONTAL_PULL, unilateral=True)
    assert starting_load(press, MALE, 84, INTERMEDIATE) == 22.0  # 55.3 x 0.4 -> 2 kg steps
    row = starting_load(one_arm, MALE, 84, INTERMEDIATE)
    assert row is not None
    assert row <= 10


def test_bodyweight_and_band_exercises_take_no_load() -> None:
    push_up = _exercise({"body_only"}, bodyweight=True)
    bands = _exercise({"resistance_bands"})
    assert not loads_weight(push_up)
    assert starting_load(push_up, MALE, 84, INTERMEDIATE) is None
    assert starting_load(bands, MALE, 84, INTERMEDIATE) is None


def test_isolation_uses_the_isolation_ratio_whatever_the_pattern() -> None:
    curl = _exercise({"cable_machine"}, MovementPattern.ISOLATION, mechanic=Mechanic.ISOLATION)
    assert starting_load(curl, MALE, 80, TrainingExperience.MONTHS_6_TO_24) == 12.5


@pytest.mark.parametrize(
    ("equipment", "kg", "expected"),
    [
        ({"barbell"}, 57.4, 55.0),
        ({"barbell"}, 12.0, 20.0),
        ({"ez_bar"}, 8.0, 10.0),
        ({"dumbbells"}, 13.9, 12.0),
        ({"kettlebell"}, 15.0, 12.0),
        ({"cable_machine"}, 0.4, 2.5),
    ],
)
def test_loads_round_down_to_what_the_equipment_holds(
    equipment: set[str], kg: float, expected: float
) -> None:
    assert round_load(_exercise(equipment), kg) == expected


def test_a_set_with_reps_to_spare_raises_the_next_one() -> None:
    # 60 x 8 leaving 4 -> e1RM 84; target 8 reps at RIR 2 -> 84 / 1.333 = 63 -> 62.5
    assert next_set_load(BENCH, 60, 8, 4, target_reps=8, target_rir=2) == 62.5
    # Far too light (wants 50 kg): the jump is capped at +15 %, 46 -> 45.
    assert next_set_load(BENCH, 40, 12, 8, target_reps=8, target_rir=2) == 45


def test_a_set_to_failure_lowers_the_next_one_within_the_cap() -> None:
    lowered = next_set_load(BENCH, 60, 5, 0, target_reps=8, target_rir=2)
    assert 45 <= lowered < 60


def test_a_set_on_target_keeps_the_load() -> None:
    assert next_set_load(BENCH, 60, 8, 2, target_reps=8, target_rir=2) == 60
    # A one-rep miss is noise: rounding must not drop a plate for it.
    assert next_set_load(BENCH, 60, 7, 2, target_reps=8, target_rir=2) == 60


def test_without_a_reported_reserve_nothing_changes() -> None:
    assert next_set_load(BENCH, 60, 3, None, target_reps=8, target_rir=2) == 60
