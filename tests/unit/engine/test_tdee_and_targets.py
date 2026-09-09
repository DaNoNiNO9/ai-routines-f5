"""Energy expenditure by components and the calorie target rules."""

from __future__ import annotations

from datetime import date

import pytest

from app.engine.bmr import estimate_bmr
from app.engine.body_composition import assess_body_composition
from app.engine.enums import (
    ActivityIntensity,
    Aggressiveness,
    BodyFatMethod,
    Confidence,
    Goal,
    JobActivity,
    Sex,
    TrainingExperience,
)
from app.engine.targets import (
    calorie_target,
    deficit_fraction,
    recomposition_eligible,
    surplus_fraction,
    target_date_feasibility,
    weekly_change_kg,
)
from app.engine.tdee import (
    activity_kcal,
    classic_activity_factor,
    eat_kcal_per_day,
    estimate_expenditure,
    expenditure_at_intake,
    expenditure_confidence,
    lifestyle_modifier,
    solve_intake,
    steps_from_job,
    walking_kcal,
)
from app.engine.types import NutritionInputs
from tests.engine_factories import TODAY, make_inputs


def _stages(inputs: NutritionInputs):
    body = assess_body_composition(inputs)
    bmr = estimate_bmr(inputs, body)
    expenditure = estimate_expenditure(inputs, body, bmr)
    return body, bmr, expenditure


def test_walking_energy_from_steps() -> None:
    # 10000 steps * 0.75 m = 7.5 km * 0.5 kcal/kg/km * 70 kg
    assert walking_kcal(10000, 70) == pytest.approx(262.5)


def test_steps_estimated_from_job() -> None:
    assert steps_from_job(JobActivity.SEDENTARY) == 4000
    assert steps_from_job(JobActivity.HEAVY_PHYSICAL) == 12000


def test_activity_energy_uses_net_mets() -> None:
    assert activity_kcal(4.0, 80, 60) == pytest.approx(240)
    inputs = make_inputs(
        weight_kg=80,
        training_days_per_week=4,
        session_minutes=60,
        other_activity_sessions_per_week=2,
        other_activity_minutes=30,
        other_activity_intensity=ActivityIntensity.MODERATE,
    )
    # gym: 4 * 240 = 960 ; other: 2 * (5 * 80 * 0.5) = 400 ; per day = 1360 / 7
    assert eat_kcal_per_day(inputs, 80) == pytest.approx(1360 / 7)


def test_lifestyle_modifier_is_small_and_conservative() -> None:
    assert lifestyle_modifier(8, 2) == 1.0
    assert lifestyle_modifier(6.5, 2) == pytest.approx(0.985)
    assert lifestyle_modifier(5, 5) == pytest.approx(0.95)


def test_tef_is_solved_on_the_intake() -> None:
    assert solve_intake(2000, 1.0) == pytest.approx(2000 / 0.9, abs=1)
    deficit_intake = solve_intake(2000, 0.8)
    assert deficit_intake == pytest.approx(1600 / 0.92, abs=1)
    spent = expenditure_at_intake(2000, deficit_intake)
    assert deficit_intake == pytest.approx(0.8 * spent, abs=1)


def test_classic_activity_factors() -> None:
    assert classic_activity_factor(0, JobActivity.SEDENTARY) == 1.2
    assert classic_activity_factor(4, JobActivity.SEDENTARY) == 1.55
    assert classic_activity_factor(6, JobActivity.HEAVY_PHYSICAL) == 1.9


def test_expenditure_components_add_up() -> None:
    _body, bmr, expenditure = _stages(make_inputs())
    assert expenditure.steps_used == 7000
    assert expenditure.steps_estimated is False
    assert expenditure.base_kcal == pytest.approx(
        bmr.selected_kcal + expenditure.neat_kcal + expenditure.eat_kcal, abs=2
    )
    assert expenditure.maintenance_kcal == pytest.approx(expenditure.base_kcal / 0.9, abs=2)
    assert expenditure.tef_at_maintenance_kcal == pytest.approx(
        expenditure.maintenance_kcal - expenditure.base_kcal, abs=2
    )
    assert abs(expenditure.divergence_pct) <= 15
    assert expenditure.notes == ()


def test_unknown_steps_are_estimated_and_lower_confidence() -> None:
    body, _, expenditure = _stages(make_inputs(daily_steps=None))
    assert expenditure.steps_estimated is True
    assert expenditure.steps_used == 4000
    assert expenditure.notes[0].code == "tdee.steps_estimated"
    assert expenditure_confidence(expenditure, body) is Confidence.MEDIUM


def test_divergence_warning_when_inputs_are_inconsistent() -> None:
    # 25 000 steps with no gym sessions: the classic table (1.2 x BMR) cannot see the walking.
    inputs = make_inputs(daily_steps=25000, training_days_per_week=0, session_minutes=0)
    body, _, expenditure = _stages(inputs)
    assert expenditure.divergence_pct > 15
    assert any(note.code == "tdee.divergence" for note in expenditure.notes)
    assert expenditure_confidence(expenditure, body) is Confidence.LOW


@pytest.mark.parametrize(
    ("sex", "body_fat", "aggressiveness", "expected"),
    [
        (Sex.MALE, 12, Aggressiveness.MODERATE, 0.10),
        (Sex.MALE, 30, Aggressiveness.MODERATE, 0.25),
        (Sex.MALE, 21, Aggressiveness.MODERATE, 0.175),
        (Sex.FEMALE, 20, Aggressiveness.AGGRESSIVE, 0.15),
        (Sex.MALE, 12, Aggressiveness.CONSERVATIVE, 0.10),
        (Sex.MALE, 40, Aggressiveness.AGGRESSIVE, 0.25),
        (Sex.FEMALE, None, Aggressiveness.MODERATE, 0.15),
    ],
)
def test_deficit_scales_with_body_fat_within_10_25(
    sex: Sex, body_fat: float | None, aggressiveness: Aggressiveness, expected: float
) -> None:
    assert deficit_fraction(sex, body_fat, aggressiveness) == pytest.approx(expected, abs=0.001)


def test_surplus_by_experience_within_5_15() -> None:
    assert surplus_fraction(TrainingExperience.NONE, Aggressiveness.MODERATE) == 0.05
    assert surplus_fraction(TrainingExperience.NONE, Aggressiveness.CONSERVATIVE) == 0.05
    assert surplus_fraction(TrainingExperience.OVER_5_YEARS, Aggressiveness.AGGRESSIVE) == 0.125


def test_recomposition_eligibility() -> None:
    assert recomposition_eligible(Sex.MALE, TrainingExperience.NONE, 15) is True
    assert recomposition_eligible(Sex.MALE, TrainingExperience.OVER_5_YEARS, 15) is False
    assert recomposition_eligible(Sex.MALE, TrainingExperience.OVER_5_YEARS, 26) is True
    assert recomposition_eligible(Sex.FEMALE, TrainingExperience.YEARS_2_TO_5, None) is False


def test_weekly_change_uses_7700_kcal_per_kg() -> None:
    assert weekly_change_kg(-500) == pytest.approx(-0.4545, abs=0.001)


def test_fat_loss_target_is_below_maintenance_and_within_safety() -> None:
    inputs = make_inputs()
    body, bmr, expenditure = _stages(inputs)
    target = calorie_target(inputs, body, bmr, expenditure)
    assert target.mode == "deficit"
    assert 0.10 <= target.fraction <= 0.25
    assert target.target_kcal < target.maintenance_kcal
    assert target.target_kcal % 5 == 0
    assert target.daily_balance_kcal < 0
    assert -target.expected_weekly_change_kg <= 0.01 * body.weight_kg + 0.01
    assert target.notes[0].code == "target.deficit"


def test_surplus_and_maintenance_modes() -> None:
    gain = make_inputs(goal=Goal.MUSCLE_GAIN, training_experience=TrainingExperience.NONE)
    body, bmr, expenditure = _stages(gain)
    target = calorie_target(gain, body, bmr, expenditure)
    assert target.mode == "surplus"
    assert target.fraction == 0.05
    assert target.target_kcal > target.maintenance_kcal

    keep = make_inputs(goal=Goal.MAINTENANCE)
    target = calorie_target(keep, body, bmr, expenditure)
    assert target.mode == "maintenance"
    assert abs(target.daily_balance_kcal) <= 5


def test_recomposition_not_eligible_becomes_maintenance_with_warning() -> None:
    inputs = make_inputs(
        goal=Goal.RECOMPOSITION, training_experience=TrainingExperience.OVER_5_YEARS
    )
    body, bmr, expenditure = _stages(inputs)
    target = calorie_target(inputs, body, bmr, expenditure)
    assert target.mode == "maintenance"
    assert any(note.code == "target.recomposition_not_ideal" for note in target.notes)


def test_small_person_is_raised_to_the_calorie_floor() -> None:
    inputs = make_inputs(
        sex=Sex.FEMALE,
        weight_kg=40,
        height_cm=145,
        age=25,
        body_fat_pct=18,
        body_fat_method=BodyFatMethod.DEXA,
        neck_cm=None,
        waist_cm=None,
        daily_steps=1500,
        training_days_per_week=0,
        session_minutes=0,
        aggressiveness=Aggressiveness.AGGRESSIVE,
    )
    body, bmr, expenditure = _stages(inputs)
    target = calorie_target(inputs, body, bmr, expenditure)
    assert target.target_kcal >= 1200
    assert any(note.code == "target.raised_to_floor" for note in target.notes)


def test_max_loss_cap_applies_to_light_people_with_large_deficits() -> None:
    inputs = make_inputs(
        weight_kg=60,
        height_cm=175,
        neck_cm=36,
        waist_cm=95,
        job_activity=JobActivity.HEAVY_PHYSICAL,
        daily_steps=15000,
        training_days_per_week=6,
        session_minutes=90,
        aggressiveness=Aggressiveness.AGGRESSIVE,
    )
    body, bmr, expenditure = _stages(inputs)
    target = calorie_target(inputs, body, bmr, expenditure)
    assert -target.expected_weekly_change_kg <= 0.6 + 0.01
    assert any(note.code == "target.capped_by_max_loss" for note in target.notes)


def test_target_date_feasibility_notes() -> None:
    inputs = make_inputs(target_weight_kg=80, target_date=date(2026, 10, 1))
    body, bmr, expenditure = _stages(inputs)
    target = calorie_target(inputs, body, bmr, expenditure)
    note = target_date_feasibility(inputs, target)
    assert note is not None
    assert note.code == "target.date_unrealistic"
    assert note.params["weeks_needed"] > note.params["weeks_available"]

    relaxed = make_inputs(target_weight_kg=80, target_date=date(2027, 6, 1))
    assert target_date_feasibility(relaxed, target).code == "target.date_realistic"
    past = make_inputs(target_weight_kg=80, target_date=date(2026, 1, 1))
    assert target_date_feasibility(past, target).code == "target.date_in_past"
    wrong_way = make_inputs(target_weight_kg=95, target_date=date(2027, 6, 1))
    assert target_date_feasibility(wrong_way, target).code == "target.date_direction_mismatch"
    assert target_date_feasibility(make_inputs(), target) is None
    assert inputs.today == TODAY


def test_target_rounds_up_when_rounding_would_cross_the_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.engine import targets

    inputs = make_inputs(aggressiveness=Aggressiveness.AGGRESSIVE)
    body, bmr, expenditure = _stages(inputs)
    monkeypatch.setattr(targets.safety, "calorie_floor", lambda _sex, _bmr: 2501.0)
    target = targets.calorie_target(inputs, body, bmr, expenditure)
    assert target.target_kcal == 2505
    assert any(note.code == "target.raised_to_floor" for note in target.notes)
