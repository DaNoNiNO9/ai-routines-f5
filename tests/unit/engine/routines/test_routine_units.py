"""Splits, volume targets, catalogue filters, selection scoring, prescription and cardio."""

from __future__ import annotations

import pytest

from app.engine.enums import (
    Goal,
    InjuryArea,
    MovementPattern,
    MuscleGroup,
    Severity,
    Sex,
    SplitType,
    TechnicalLevel,
    TrainingExperience,
    TrainingLocation,
)
from app.engine.routines import prescription as rx
from app.engine.routines import volume as vol
from app.engine.routines.cardio import cardio_prescription, hiit_allowed, steps_target
from app.engine.routines.catalog import (
    allowed_level,
    has_shoulder_history,
    is_contraindicated,
    usable_exercises,
)
from app.engine.routines.selection import STAPLES, matches_slot, pick, relaxed_ceiling
from app.engine.routines.splits import (
    ISOLATION,
    MAIN,
    TEMPLATES,
    Slot,
    day_templates,
    select_split,
)
from app.engine.routines.types import InjuryInput
from app.engine.types import InputError
from tests.routine_factories import BY_SLUG, CATALOGUE, make_routine_inputs


@pytest.mark.parametrize(
    ("days", "experience", "expected"),
    [
        (2, TrainingExperience.NONE, SplitType.FULL_BODY),
        (3, TrainingExperience.MONTHS_6_TO_24, SplitType.FULL_BODY),
        (3, TrainingExperience.YEARS_2_TO_5, SplitType.PUSH_PULL_LEGS),
        (4, TrainingExperience.NONE, SplitType.UPPER_LOWER),
        (5, TrainingExperience.YEARS_2_TO_5, SplitType.UPPER_LOWER_PPL),
        (5, TrainingExperience.OVER_5_YEARS, SplitType.ARNOLD),
        (6, TrainingExperience.NONE, SplitType.PPL_TWICE),
        (1, TrainingExperience.NONE, SplitType.FULL_BODY),
    ],
)
def test_split_selection(days: int, experience: TrainingExperience, expected: SplitType) -> None:
    assert select_split(days, experience) == expected


def test_day_templates_are_trimmed_or_cycled_and_have_a_main_slot() -> None:
    assert len(day_templates(SplitType.FULL_BODY, 2)) == 2
    assert len(day_templates(SplitType.FULL_BODY, 5)) == 5
    for split, templates in TEMPLATES.items():
        for template in templates:
            assert any(slot.role == MAIN for slot in template.slots), (split, template.name)
            assert template.focus


def test_volume_tiers_and_targets_without_priorities() -> None:
    assert vol.experience_tier(TrainingExperience.NONE) == "beginner"
    assert vol.experience_tier(TrainingExperience.YEARS_2_TO_5) == "intermediate"
    assert vol.experience_tier(TrainingExperience.OVER_5_YEARS) == "advanced"
    targets = vol.volume_targets(TrainingExperience.MONTHS_6_TO_24, ())
    assert all(target == (12, 18) for target in targets.values())


def test_priority_muscles_get_more_volume_and_the_rest_compensate() -> None:
    targets = vol.volume_targets(TrainingExperience.OVER_5_YEARS, (MuscleGroup.GLUTES,))
    assert targets[MuscleGroup.GLUTES] == (20, 28)
    assert targets[MuscleGroup.CHEST][0] < 16
    total_low = sum(low for low, _ in targets.values())
    assert abs(total_low - 16 * len(vol.MAJOR_MUSCLES)) <= len(vol.MAJOR_MUSCLES)


def test_set_credit_counts_primary_fully_and_secondary_half() -> None:
    bench = BY_SLUG["barbell-bench-press-medium-grip"]
    credit = vol.set_credit(bench, 4)
    assert credit[MuscleGroup.CHEST] == 4
    assert credit[MuscleGroup.TRICEPS] == 2
    table = vol.volume_table([(bench, 4)], vol.volume_targets(TrainingExperience.NONE, ()), ())
    chest = next(entry for entry in table if entry.muscle is MuscleGroup.CHEST)
    assert chest.status == "low"
    assert chest.planned_sets == 4


def test_catalogue_filters_equipment_injuries_level_and_dislikes() -> None:
    bench = BY_SLUG["barbell-bench-press-medium-grip"]
    inputs = make_routine_inputs(
        training_location=TrainingLocation.HOME_BODYWEIGHT,
        injuries=(InjuryInput(InjuryArea.SHOULDER, Severity.MODERATE),),
        disliked_exercises=frozenset({"pushups"}),
        training_experience=TrainingExperience.NONE,
    )
    pool = usable_exercises(CATALOGUE, inputs, allowed_level(inputs.training_experience))
    slugs = {exercise.slug for exercise in pool}
    assert bench.slug not in slugs  # needs a barbell
    assert "pushups" not in slugs  # disliked
    assert "plyo-push-up" not in slugs  # advanced level
    assert all(exercise.equipment <= inputs.equipment for exercise in pool)
    assert all(not is_contraindicated(exercise, inputs.injuries) for exercise in pool)


def test_contraindication_uses_the_minimum_severity() -> None:
    bench = BY_SLUG["barbell-bench-press-medium-grip"]  # shoulder moderate
    assert is_contraindicated(bench, [InjuryInput(InjuryArea.SHOULDER, Severity.MILD)]) is False
    assert is_contraindicated(bench, [InjuryInput(InjuryArea.SHOULDER, Severity.MODERATE)]) is True
    assert is_contraindicated(bench, [InjuryInput(InjuryArea.KNEE, Severity.SEVERE)]) is False
    assert has_shoulder_history([InjuryInput(InjuryArea.SHOULDER, Severity.MILD)]) is True
    assert has_shoulder_history([]) is False


def test_allowed_level_and_relaxation() -> None:
    assert allowed_level(TrainingExperience.NONE) is TechnicalLevel.BEGINNER
    assert allowed_level(TrainingExperience.OVER_5_YEARS) is TechnicalLevel.ADVANCED
    assert relaxed_ceiling(TechnicalLevel.BEGINNER) is TechnicalLevel.INTERMEDIATE
    assert relaxed_ceiling(TechnicalLevel.ADVANCED) is None


def test_selection_is_deterministic_and_prefers_staples_and_preferred() -> None:
    inputs = make_routine_inputs()
    pool = usable_exercises(CATALOGUE, inputs, allowed_level(inputs.training_experience))
    slot = Slot(MovementPattern.HORIZONTAL_PUSH, MAIN, MuscleGroup.CHEST)
    first = pick(pool, slot, inputs, {})
    second = pick(pool, slot, inputs, {})
    assert first is not None
    assert first is second
    assert first.slug in STAPLES
    assert "barbell" in first.equipment

    preferring = make_routine_inputs(preferred_exercises=frozenset({"dumbbell-floor-press"}))
    assert pick(pool, slot, preferring, {}).slug == "dumbbell-floor-press"
    reused = pick(pool, slot, inputs, {first.slug: 1})
    assert reused is not None
    assert reused.slug != first.slug


def test_isolation_slots_require_the_target_muscle() -> None:
    curl = BY_SLUG["barbell-curl"]
    assert matches_slot(curl, Slot(MovementPattern.ISOLATION, ISOLATION, MuscleGroup.BICEPS))
    assert not matches_slot(curl, Slot(MovementPattern.ISOLATION, ISOLATION, MuscleGroup.TRICEPS))
    assert not matches_slot(curl, Slot(MovementPattern.HORIZONTAL_PULL, MAIN))


def test_staples_exist_in_the_catalogue() -> None:
    missing = sorted(slug for slug in STAPLES if slug not in BY_SLUG)
    assert missing == []


def test_rep_ranges_rir_rest_tempo_and_increments() -> None:
    assert rx.rep_range(MAIN, Goal.FAT_LOSS, "beginner", MovementPattern.KNEE_DOMINANT) == (6, 10)
    assert rx.rep_range(MAIN, Goal.PERFORMANCE, "intermediate", MovementPattern.KNEE_DOMINANT) == (
        3,
        6,
    )
    assert rx.rep_range(MAIN, Goal.PERFORMANCE, "beginner", MovementPattern.KNEE_DOMINANT) == (
        6,
        10,
    )
    assert rx.rep_range(ISOLATION, Goal.MUSCLE_GAIN, "advanced", MovementPattern.ISOLATION) == (
        12,
        20,
    )
    assert rx.rep_range(ISOLATION, Goal.MUSCLE_GAIN, "advanced", MovementPattern.CORE) == (10, 15)
    assert rx.rir_bounds(MAIN) == (3, 1)
    assert rx.rir_bounds(ISOLATION) == (3, 0)
    assert rx.weekly_rir(4) == (3, 2, 1, 1)
    assert rx.weekly_rir(6) == (3, 3, 2, 2, 1, 1)
    assert rx.weekly_rir(8) == (3, 3, 2, 2, 1, 1, 1, 1)
    assert rx.mesocycle_and_deload("beginner", None) == (6, 8)
    assert rx.mesocycle_and_deload("advanced", 5) == (4, 4)
    assert rx.mesocycle_and_deload("intermediate", 4) == (4, 4)

    squat = BY_SLUG["barbell-squat"]
    bench = BY_SLUG["barbell-bench-press-medium-grip"]
    dumbbell = BY_SLUG["dumbbell-bench-press"]
    pushups = BY_SLUG["pushups"]
    machine = BY_SLUG["leg-press"]
    assert rx.load_increment_kg(squat, Sex.MALE) == 5.0
    assert rx.load_increment_kg(squat, Sex.FEMALE) == 2.5
    assert rx.load_increment_kg(bench, Sex.MALE) == 2.5
    assert rx.load_increment_kg(dumbbell, Sex.FEMALE) == 1.0
    assert rx.load_increment_kg(pushups, Sex.MALE) == 0.0
    assert rx.load_increment_kg(machine, Sex.MALE) == 5.0
    assert rx.rest_seconds(pushups, MAIN) < rx.rest_seconds(bench, MAIN)
    assert rx.tempo_for(bench, ISOLATION) == "3-1-1-0"
    assert rx.estimate_minutes([(bench, MAIN, 4, 10)]) > rx.estimate_minutes([(bench, MAIN, 2, 10)])


def test_cardio_steps_and_sessions_follow_the_uncovered_deficit() -> None:
    assert steps_target(4000, Goal.FAT_LOSS) == 8000
    assert steps_target(9000, Goal.FAT_LOSS) == 11000
    assert steps_target(15000, Goal.FAT_LOSS) == 12000
    assert steps_target(None, Goal.MAINTENANCE) == 7000

    nothing = cardio_prescription(make_routine_inputs(goal=Goal.MAINTENANCE))
    assert nothing.liss_sessions == 2
    assert nothing.hiit_sessions == 0
    assert nothing.notes[0].code == "cardio.not_punishment"

    heavy = cardio_prescription(
        make_routine_inputs(extra_deficit_kcal_per_day=250, daily_steps=7000)
    )
    assert heavy.daily_steps_target == 9000
    assert 1 <= heavy.liss_sessions <= 3
    assert heavy.weekly_kcal_estimate > 0

    impossible = cardio_prescription(make_routine_inputs(extra_deficit_kcal_per_day=900))
    assert impossible.liss_sessions == 3
    assert impossible.hiit_sessions == 1
    assert any(note.code == "cardio.deficit_not_covered" for note in impossible.notes)


def test_hiit_gated_by_experience_and_lower_body_injuries() -> None:
    assert hiit_allowed(make_routine_inputs()) is True
    assert hiit_allowed(make_routine_inputs(training_experience=TrainingExperience.NONE)) is False
    knee = make_routine_inputs(injuries=(InjuryInput(InjuryArea.KNEE, Severity.MODERATE),))
    assert hiit_allowed(knee) is False
    mild = make_routine_inputs(injuries=(InjuryInput(InjuryArea.KNEE, Severity.MILD),))
    assert hiit_allowed(mild) is True


def test_routine_inputs_validation() -> None:
    with pytest.raises(InputError, match="training_days_per_week"):
        make_routine_inputs(training_days_per_week=8)
    with pytest.raises(InputError, match="two priority"):
        make_routine_inputs(priority_muscles=(MuscleGroup.CHEST, MuscleGroup.BACK, MuscleGroup.ABS))
    with pytest.raises(InputError, match="extra_deficit"):
        make_routine_inputs(extra_deficit_kcal_per_day=-1)


def test_the_cardio_says_what_to_do_it_on() -> None:
    """Decir "dos sesiones LISS" y callarse deja a la persona adivinando."""
    con_maquina = make_routine_inputs(
        training_location=TrainingLocation.FULL_GYM, extra_deficit_kcal_per_day=250
    )
    codigos = [note.code for note in cardio_prescription(con_maquina).notes]
    assert "cardio.liss_machine" in codigos

    sin_maquina = make_routine_inputs(
        training_location=TrainingLocation.HOME_EQUIPMENT, extra_deficit_kcal_per_day=250
    )
    codigos = [note.code for note in cardio_prescription(sin_maquina).notes]
    assert "cardio.liss_outdoor" in codigos

    con_rodilla = make_routine_inputs(
        training_location=TrainingLocation.FULL_GYM,
        extra_deficit_kcal_per_day=250,
        injuries=(InjuryInput(area=InjuryArea.KNEE, severity=Severity.MODERATE),),
    )
    prescripcion = cardio_prescription(con_rodilla)
    codigos = [note.code for note in prescripcion.notes]
    assert "cardio.liss_low_impact" in codigos
    assert prescripcion.hiit_sessions == 0  # nada de impacto con la rodilla así
