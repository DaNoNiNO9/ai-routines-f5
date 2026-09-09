"""Smoothing, energy balance, review rules and convergence of the adjustment engine."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from app.engine import safety
from app.engine.adjustment import rules
from app.engine.adjustment.energy_balance import estimate_tdee, mean_adherence, observed_tdee
from app.engine.adjustment.smoothing import estimate_trend, moving_average, slope_per_day
from app.engine.adjustment.types import AdjustmentInputs, IntakePoint, WeightPoint
from app.engine.enums import AdjustmentReason, Confidence, Goal, Sex
from app.engine.messages import render_all
from app.engine.types import InputError
from tests.adjustment_sim import START, make_adjustment_inputs, simulate


def _days(count: int) -> list[date]:
    return [START + timedelta(days=offset) for offset in range(count)]


def test_moving_average_filters_daily_noise() -> None:
    weights, _, _, _ = simulate(80, 2500, 2500, 21, noise_sd=0.6, seed=3)
    smoothed = moving_average(weights)
    assert len(smoothed) == 19  # the first two days lack a 3-point window
    assert all(abs(value - 80) < 0.45 for _, value in smoothed[6:])
    sparse = [WeightPoint(START, 80), WeightPoint(START + timedelta(days=1), 80.2)]
    assert moving_average(sparse) == []


def test_slope_is_exact_on_linear_series_and_none_when_undefined() -> None:
    series = [(day, 80 - 0.1 * index) for index, day in enumerate(_days(10))]
    assert slope_per_day(series) == pytest.approx(-0.1)
    assert slope_per_day(series[:1]) is None
    assert slope_per_day([(START, 80.0), (START, 81.0)]) is None


def test_trend_recovers_a_half_kilo_per_week_loss_through_noise() -> None:
    weights, _, _, _ = simulate(85, 2700, 2150, 28, noise_sd=0.5, seed=7)
    trend = estimate_trend(weights, START, START + timedelta(days=27))
    assert trend.weekly_change_kg is not None
    assert trend.weekly_change_kg == pytest.approx(-0.5, abs=0.15)
    assert trend.confidence is Confidence.HIGH
    assert trend.weight_days == 28
    assert trend.start_average_kg is not None
    assert trend.end_average_kg is not None
    assert trend.end_average_kg < trend.start_average_kg


def test_trend_needs_enough_data() -> None:
    weights = [WeightPoint(day, 80.0) for day in _days(5)]
    trend = estimate_trend(weights, START, START + timedelta(days=13))
    assert trend.weekly_change_kg is None
    assert trend.confidence is Confidence.LOW
    sparse, _, _, _ = simulate(80, 2500, 2500, 14, log_every_day=False, seed=2)
    trend = estimate_trend(sparse, START, START + timedelta(days=13))
    assert trend.confidence in (Confidence.MEDIUM, Confidence.HIGH, Confidence.LOW)


def test_observed_tdee_from_energy_balance() -> None:
    # Eating 2000 while losing 0.5 kg/week means spending 2000 + 550 kcal/day.
    assert observed_tdee(2000, -0.5) == pytest.approx(2550)


def test_tdee_estimate_blends_with_data_and_clamps_outliers() -> None:
    weights, intakes, true_tdee, _ = simulate(85, 2450, 2150, 28, seed=11)
    trend = estimate_trend(weights, START, START + timedelta(days=27))
    estimate = estimate_tdee(2700, intakes, trend)
    assert estimate.observed_kcal is not None
    assert estimate.observed_kcal == pytest.approx(true_tdee, rel=0.06)
    assert estimate.weight == 1.0
    assert estimate.blended_kcal == estimate.observed_kcal
    assert estimate.confidence is Confidence.HIGH

    short = estimate_trend(weights, START, START + timedelta(days=13))
    partial = estimate_tdee(2700, intakes, short)
    assert partial.weight == pytest.approx(0.5)
    assert partial.observed_kcal is not None
    assert (
        min(partial.observed_kcal, 2700) <= partial.blended_kcal <= max(partial.observed_kcal, 2700)
    )

    wild = [IntakePoint(point.day, 800) for point in intakes]  # implausible logs
    clamped = estimate_tdee(2700, wild, trend)
    assert clamped.observed_kcal == pytest.approx(2700 * 0.75)


def test_tdee_estimate_needs_intake_coverage() -> None:
    weights, intakes, _, _ = simulate(85, 2450, 2150, 28, seed=5)
    trend = estimate_trend(weights, START, START + timedelta(days=27))
    thin = estimate_tdee(2700, intakes[:10], trend)
    assert thin.observed_kcal is None
    assert thin.blended_kcal == 2700
    assert thin.confidence is Confidence.LOW
    assert mean_adherence(intakes, START, START + timedelta(days=27)) == 100.0
    assert mean_adherence([], START, START) is None


def test_review_waits_before_the_due_date_and_without_data() -> None:
    weights, intakes, _, _ = simulate(85, 2450, 2150, 7, seed=1)
    early = rules.decide(make_adjustment_inputs(weights, intakes))
    assert early.action == "wait"
    assert early.review_due is False
    assert early.next_review_on == START + timedelta(days=14)

    few = [WeightPoint(day, 85.0) for day in _days(4)]
    late = rules.decide(make_adjustment_inputs(few, [], today=START + timedelta(days=14)))
    assert late.action == "wait"
    assert late.review_due is True
    assert late.notes[0].code == "adjust.insufficient_data"


def test_on_track_keeps_the_plan() -> None:
    weights, intakes, _, _ = simulate(85, 2650, 2200, 15, seed=4)
    decision = rules.decide(make_adjustment_inputs(weights, intakes))
    assert decision.action == "keep"
    assert decision.calorie_delta == 0
    assert decision.changes_plan is False
    json.dumps(decision.to_dict())
    render_all(decision.notes)


def test_slow_loss_cuts_at_most_five_percent_and_respects_the_floor() -> None:
    weights, intakes, _, _ = simulate(85, 2300, 2200, 21, seed=8, noise_sd=0.15)
    decision = rules.decide(make_adjustment_inputs(weights, intakes))
    assert decision.action == "reduce_calories"
    assert decision.reason is AdjustmentReason.LOSS_TOO_SLOW
    assert -decision.calorie_delta <= 2200 * 0.05 + 1
    assert decision.new_calories >= safety.calorie_floor(Sex.MALE, 1800)
    assert any(note.code == "adjust.reduce_calories" for note in decision.notes)

    at_floor = make_adjustment_inputs(weights, intakes, plan_calories=1800, bmr_kcal=1800)
    floored = rules.decide(at_floor)
    assert floored.action == "add_steps"
    assert floored.steps_delta == 1000
    assert floored.new_calories == 1800

    maxed = make_adjustment_inputs(
        weights, intakes, plan_calories=1800, bmr_kcal=1800, steps_target=12000
    )
    assert rules.decide(maxed).action == "keep"


def test_low_adherence_blocks_the_cut() -> None:
    weights, intakes, _, _ = simulate(85, 2300, 2200, 21, seed=8, noise_sd=0.15, adherence=70)
    decision = rules.decide(make_adjustment_inputs(weights, intakes))
    assert decision.action == "adherence"
    assert decision.calorie_delta == 0
    assert decision.adherence_pct == 70


def test_fast_loss_raises_calories() -> None:
    weights, intakes, _, _ = simulate(85, 3300, 2200, 15, seed=9, noise_sd=0.2)
    decision = rules.decide(make_adjustment_inputs(weights, intakes))
    assert decision.action == "increase_calories"
    assert decision.reason is AdjustmentReason.LOSS_TOO_FAST
    assert 0 < decision.calorie_delta <= 2200 * 0.10 + 1


def test_stalls_trigger_refeed_then_diet_break() -> None:
    weights, intakes, _, _ = simulate(85, 2200, 2200, 21, seed=6, noise_sd=0.1)
    refeed = rules.decide(
        make_adjustment_inputs(weights, intakes, weeks_in_deficit=6, stalled_reviews=1)
    )
    assert refeed.action == "refeed"
    assert refeed.calorie_delta == 0
    diet_break = rules.decide(make_adjustment_inputs(weights, intakes, weeks_in_deficit=9))
    assert diet_break.action == "diet_break"
    assert diet_break.new_calories >= 2200
    first_stall = rules.decide(make_adjustment_inputs(weights, intakes, weeks_in_deficit=6))
    assert first_stall.action in ("reduce_calories", "add_steps")


def test_surplus_rules() -> None:
    slow, slow_intakes, _, _ = simulate(70, 2900, 2950, 21, seed=12, noise_sd=0.15)
    up = rules.decide(
        make_adjustment_inputs(
            slow,
            slow_intakes,
            mode="surplus",
            goal=Goal.MUSCLE_GAIN,
            plan_calories=2950,
            expected_weekly_change_kg=0.25,
        )
    )
    assert up.action == "increase_calories"
    assert up.calorie_delta == pytest.approx(2950 * 0.05, abs=5)

    fast, fast_intakes, _, _ = simulate(70, 2400, 3400, 21, seed=13, noise_sd=0.15)
    down = rules.decide(
        make_adjustment_inputs(
            fast,
            fast_intakes,
            mode="surplus",
            goal=Goal.MUSCLE_GAIN,
            plan_calories=3400,
            expected_weekly_change_kg=0.25,
        )
    )
    assert down.action == "reduce_calories"
    assert down.reason is AdjustmentReason.GAIN_TOO_FAST


def test_maintenance_rules() -> None:
    losing, intakes, _, _ = simulate(70, 2800, 2400, 21, seed=14, noise_sd=0.15)
    up = rules.decide(
        make_adjustment_inputs(
            losing,
            intakes,
            mode="maintenance",
            goal=Goal.MAINTENANCE,
            plan_calories=2400,
            expected_weekly_change_kg=0.0,
        )
    )
    assert up.action == "increase_calories"
    assert up.calorie_delta == pytest.approx(2400 * 0.03, abs=5)
    gaining, intakes, _, _ = simulate(70, 2000, 2400, 21, seed=15, noise_sd=0.15)
    down = rules.decide(
        make_adjustment_inputs(
            gaining,
            intakes,
            mode="maintenance",
            goal=Goal.MAINTENANCE,
            plan_calories=2400,
            expected_weekly_change_kg=0.0,
        )
    )
    assert down.action == "reduce_calories"
    steady, intakes, _, _ = simulate(70, 2400, 2400, 21, seed=16, noise_sd=0.15)
    assert (
        rules.decide(
            make_adjustment_inputs(
                steady,
                intakes,
                mode="maintenance",
                goal=Goal.MAINTENANCE,
                plan_calories=2400,
                expected_weekly_change_kg=0.0,
            )
        ).action
        == "keep"
    )


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_reviews_converge_on_the_true_expenditure_without_crossing_limits(seed: int) -> None:
    """A plan built on an overestimated TDEE is corrected review by review."""
    true_tdee = 2350.0
    theoretical = 2700.0
    calories = 2250
    start_weight = 85.0
    weights: list[WeightPoint] = []
    intakes: list[IntakePoint] = []
    weight_now = start_weight
    tdee_now = true_tdee
    last_adjustment: date | None = None
    weeks_in_deficit = 0
    day = START
    floor = safety.calorie_floor(Sex.MALE, 1800)
    for review_index in range(6):
        block_weights, block_intakes, tdee_now, weight_now = simulate(
            weight_now, tdee_now, calories, 14, start=day, seed=seed * 100 + review_index
        )
        weights.extend(block_weights)
        intakes.extend(block_intakes)
        day = day + timedelta(days=14)
        weeks_in_deficit += 2
        decision = rules.decide(
            AdjustmentInputs(
                sex=Sex.MALE,
                goal=Goal.FAT_LOSS,
                mode="deficit",
                plan_calories=calories,
                plan_started_on=START,
                expected_weekly_change_kg=-0.45,
                bmr_kcal=1800,
                theoretical_tdee_kcal=theoretical,
                weights=tuple(weights),
                intakes=tuple(intakes),
                today=day,
                weeks_in_deficit=weeks_in_deficit,
                last_adjustment_on=last_adjustment,
            )
        )
        assert decision.review_due
        assert decision.new_calories >= floor
        if decision.action == "reduce_calories":
            assert -decision.calorie_delta <= calories * 0.05 + 1
        if decision.action in ("reduce_calories", "increase_calories"):
            calories = decision.new_calories
            last_adjustment = day
        assert decision.tdee is not None
    assert decision.tdee.observed_kcal is not None
    assert decision.tdee.blended_kcal == pytest.approx(tdee_now, rel=0.08)
    assert calories < 2250
    assert decision.trend is not None
    assert decision.trend.weekly_change_kg is not None
    assert -decision.trend.weekly_change_kg <= safety.max_weekly_loss_kg(weight_now) + 0.05


def test_tdee_confidence_drops_with_sparse_weights() -> None:
    weights, intakes, _, _ = simulate(85, 2450, 2150, 20, seed=21, log_every_day=False)
    trend = estimate_trend(weights, START, START + timedelta(days=19))
    estimate = estimate_tdee(2700, intakes, trend)
    if estimate.observed_kcal is not None:
        assert estimate.confidence in (Confidence.LOW, Confidence.MEDIUM)
        assert estimate.weight <= 20 / 28
    few = [WeightPoint(START + timedelta(days=i * 2), 85 - 0.05 * i) for i in range(9)]
    low = estimate_trend(few, START, START + timedelta(days=16))
    assert low.weekly_change_kg is not None
    assert low.confidence is Confidence.MEDIUM
    partial = estimate_tdee(2700, intakes, low)
    assert partial.weight <= 0.61
    ten_days, ten_intakes, _, _ = simulate(85, 2450, 2150, 10, seed=22, noise_sd=0.1)
    short = estimate_trend(ten_days, START, START + timedelta(days=9))
    assert short.weekly_change_kg is not None
    weak = estimate_tdee(2700, ten_intakes, short)
    assert weak.observed_kcal is not None
    assert weak.confidence is Confidence.LOW
    assert weak.weight == pytest.approx(10 / 28, abs=0.01)


def test_inputs_validation() -> None:
    weights, intakes, _, _ = simulate(85, 2450, 2150, 15)
    with pytest.raises(InputError, match="mode"):
        make_adjustment_inputs(weights, intakes, mode="bulk")
    with pytest.raises(InputError, match="review_interval_days"):
        make_adjustment_inputs(weights, intakes, review_interval_days=3)
    with pytest.raises(InputError, match="out of range"):
        make_adjustment_inputs([WeightPoint(START, 10)], [])
    with pytest.raises(InputError, match="steps_target"):
        make_adjustment_inputs(weights, intakes, steps_target=50000)
    with pytest.raises(InputError, match="negative"):
        make_adjustment_inputs(weights, intakes, weeks_in_deficit=-1)
    with pytest.raises(InputError, match="intake"):
        make_adjustment_inputs(weights, [IntakePoint(START, 50000)])
    with pytest.raises(InputError, match="plan_calories"):
        make_adjustment_inputs(weights, intakes, plan_calories=100)
    with pytest.raises(InputError, match="at least one weight"):
        make_adjustment_inputs([], []).current_weight_kg  # noqa: B018 - property raises
