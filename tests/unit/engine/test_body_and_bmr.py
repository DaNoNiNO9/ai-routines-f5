"""Body composition (Navy, BMI, lean mass) and the three BMR formulas."""

from __future__ import annotations

import pytest

from app.engine.bmr import estimate_bmr, harris_benedict, katch_mcardle, mifflin_st_jeor
from app.engine.body_composition import (
    assess_body_composition,
    bmi,
    lean_body_mass,
    navy_body_fat,
)
from app.engine.enums import BmrMethod, BodyFatMethod, Confidence, Sex
from app.engine.types import InputError, NutritionInputs
from tests.engine_factories import INPUT_DEFAULTS, make_female_inputs, make_inputs


def test_navy_formula_men_reference_value() -> None:
    # 495 / (1.0324 - 0.19077*log10(45) + 0.15456*log10(180)) - 450 = 14.5
    assert navy_body_fat(Sex.MALE, 180, neck_cm=40, waist_cm=85) == pytest.approx(14.5, abs=0.15)


def test_navy_formula_women_reference_value() -> None:
    # 495 / (1.29579 - 0.35004*log10(137) + 0.22100*log10(165)) - 450 = 26.9
    assert navy_body_fat(Sex.FEMALE, 165, neck_cm=33, waist_cm=74, hip_cm=96) == pytest.approx(
        26.9, abs=0.2
    )


def test_navy_rejects_impossible_or_out_of_range_measurements() -> None:
    assert navy_body_fat(Sex.MALE, 180, neck_cm=50, waist_cm=45) is None
    assert navy_body_fat(Sex.FEMALE, 165, neck_cm=33, waist_cm=74, hip_cm=None) is None
    assert navy_body_fat(Sex.FEMALE, 165, neck_cm=150, waist_cm=40, hip_cm=50) is None
    # Extremely small girth pushes the estimate below 2 %: reported as unknown.
    assert navy_body_fat(Sex.MALE, 200, neck_cm=44, waist_cm=45) is None


def test_bmi_and_lean_mass() -> None:
    assert bmi(80, 180) == pytest.approx(24.69, abs=0.01)
    assert lean_body_mass(80, 20) == pytest.approx(64.0)


def test_declared_body_fat_wins_over_circumferences() -> None:
    body = assess_body_composition(
        make_inputs(body_fat_pct=18.0, body_fat_method=BodyFatMethod.DEXA)
    )
    assert body.body_fat_pct == 18.0
    assert body.body_fat_source is BodyFatMethod.DEXA
    assert body.confidence is Confidence.HIGH
    assert body.lean_mass_kg == pytest.approx(85 * 0.82, abs=0.1)


def test_navy_estimate_used_when_only_circumferences() -> None:
    body = assess_body_composition(make_inputs())
    assert body.body_fat_source is BodyFatMethod.NAVY
    assert body.confidence is Confidence.MEDIUM
    assert body.body_fat_pct is not None
    assert [note.code for note in body.notes] == ["body_fat.navy"]


def test_no_data_means_low_confidence_and_no_lean_mass() -> None:
    body = assess_body_composition(make_inputs(neck_cm=None, waist_cm=None))
    assert body.body_fat_pct is None
    assert body.lean_mass_kg is None
    assert body.confidence is Confidence.LOW
    assert body.notes[0].code == "body_fat.unknown"


def test_invalid_circumferences_are_reported() -> None:
    body = assess_body_composition(make_inputs(neck_cm=60, waist_cm=50))
    assert body.body_fat_pct is None
    assert body.notes[0].code == "body_fat.navy_invalid"


def test_declared_percentage_without_method_counts_as_visual() -> None:
    inputs = make_inputs(body_fat_pct=20.0)
    assert inputs.body_fat_method is BodyFatMethod.VISUAL
    assert assess_body_composition(inputs).confidence is Confidence.LOW


@pytest.mark.parametrize(
    ("field", "value"),
    [("age", 5), ("height_cm", 90), ("weight_kg", 400), ("stress_level", 0), ("meals_per_day", 9)],
)
def test_inputs_reject_out_of_range_values(field: str, value: float) -> None:
    with pytest.raises(InputError, match=field):
        NutritionInputs(**{**INPUT_DEFAULTS, field: value})


def test_mifflin_st_jeor_reference_values() -> None:
    assert mifflin_st_jeor(Sex.MALE, 80, 180, 30) == pytest.approx(1780)
    assert mifflin_st_jeor(Sex.FEMALE, 60, 165, 28) == pytest.approx(1330.25)


def test_harris_benedict_reference_values() -> None:
    assert harris_benedict(Sex.MALE, 80, 180, 30) == pytest.approx(1853.6, abs=0.1)
    assert harris_benedict(Sex.FEMALE, 60, 165, 28) == pytest.approx(1392.3, abs=0.1)


def test_katch_mcardle_reference_value() -> None:
    assert katch_mcardle(65) == pytest.approx(1774)


def test_bmr_selects_katch_mcardle_when_body_fat_is_known() -> None:
    inputs = make_inputs(body_fat_pct=15.0, body_fat_method=BodyFatMethod.CALIPERS)
    body = assess_body_composition(inputs)
    estimate = estimate_bmr(inputs, body)
    assert estimate.method is BmrMethod.KATCH_MCARDLE
    assert set(estimate.estimates) == set(BmrMethod)
    assert estimate.low_kcal <= estimate.selected_kcal <= estimate.high_kcal
    assert estimate.selected_kcal == pytest.approx(370 + 21.6 * 85 * 0.85, abs=1)


def test_bmr_falls_back_to_mifflin_without_body_fat() -> None:
    inputs = make_female_inputs(neck_cm=None, waist_cm=None, hip_cm=None)
    estimate = estimate_bmr(inputs, assess_body_composition(inputs))
    assert estimate.method is BmrMethod.MIFFLIN_ST_JEOR
    assert BmrMethod.KATCH_MCARDLE not in estimate.estimates
    assert estimate.selected_kcal == 1330
    assert estimate.notes[0].code == "bmr.mifflin"
