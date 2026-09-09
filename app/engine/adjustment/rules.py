"""Review rules: compare what happened with what was expected and decide.

Every ``review_interval_days`` (14 by default) since the plan started or the
last adjustment:

- Not enough weigh-ins -> wait.
- Deficit: losing less than half of the expected rate -> check adherence
  first (no cut below 85 % adherence); otherwise cut calories by at most 5 %,
  or add 1000 steps a day when calories already sit on the safety floor.
  Losing faster than 1 % of body weight per week -> raise calories to the
  cap. Stalled for weeks -> refeed (4-7 weeks in) or a 2-week diet break
  (8+ weeks in).
- Surplus: gaining less than half of the expected -> +5 %; gaining more than
  0.5 % of body weight per week -> -5 %.
- Maintenance: drifting more than 0.25 kg/week -> +/-3 %.

Calories never go below ``safety.calorie_floor`` and a cut never pushes the
expected loss beyond the 1 % weekly cap.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.engine import safety
from app.engine.adjustment.energy_balance import KCAL_PER_KG, estimate_tdee, mean_adherence
from app.engine.adjustment.smoothing import estimate_trend
from app.engine.adjustment.types import (
    SPARSE_REVIEW_INTERVAL_DAYS,
    AdjustmentDecision,
    AdjustmentInputs,
    TdeeEstimate,
    TrendEstimate,
)
from app.engine.enums import AdjustmentReason
from app.engine.types import Note

MAX_CUT_FRACTION = 0.05
# Con pocos pesajes, por debajo de esto no se distingue el cambio real del agua.
SPARSE_NOISE_KG = 0.2
MAX_RAISE_FRACTION = 0.10
ADHERENCE_THRESHOLD = 85.0
SLOW_FRACTION = 0.5
STEP_INCREMENT = 1000
MAX_STEPS_TARGET = 12000
SURPLUS_FAST_FRACTION = 0.005
MAINTENANCE_DRIFT_KG = 0.25
MAINTENANCE_STEP = 0.03
STALL_THRESHOLD_KG = 0.1
REFEED_WEEKS = 4
DIET_BREAK_WEEKS = 8
ROUND_TO = 5
TDEE_HISTORY_DAYS = 42


@dataclass
class Review:
    """Everything a rule needs, gathered once per review."""

    inputs: AdjustmentInputs
    trend: TrendEstimate
    tdee: TdeeEstimate
    adherence: float | None
    notes: list[Note] = field(default_factory=list)

    @property
    def observed(self) -> float:
        """Observed weekly change (only read once the trend is known)."""
        assert self.trend.weekly_change_kg is not None
        return self.trend.weekly_change_kg

    @property
    def expected(self) -> float:
        """Expected weekly change from the plan."""
        return self.inputs.expected_weekly_change_kg

    @property
    def sparse(self) -> bool:
        """Whether the trend came from loose weigh-ins instead of a smoothed series."""
        return not self.trend.smoothed

    @property
    def step_limit(self) -> float:
        """Cap for one step; halved when the trend is built on few weigh-ins."""
        return MAX_CUT_FRACTION / 2 if self.sparse else MAX_CUT_FRACTION

    def next_review(self) -> date:
        """Date of the following review after acting today.

        Con pocos pesajes hay que mirar más lejos: en dos semanas el ruido
        del agua pesa más que el cambio real, en cuatro ya no.
        """
        days = SPARSE_REVIEW_INTERVAL_DAYS if self.sparse else self.inputs.review_interval_days
        return self.inputs.today + timedelta(days=max(days, self.inputs.review_interval_days))

    def decision(
        self,
        action: str,
        reason: AdjustmentReason,
        *,
        review_due: bool = True,
        next_review: date | None = None,
        new_calories: int | None = None,
        steps_delta: int = 0,
    ) -> AdjustmentDecision:
        """Build the final decision object."""
        calories = self.inputs.plan_calories if new_calories is None else new_calories
        when = next_review or self.next_review()
        self.notes.append(Note("adjust.next_review", params={"date": when.isoformat()}))
        return AdjustmentDecision(
            action=action,
            reason=reason,
            review_due=review_due,
            new_calories=calories,
            calorie_delta=calories - self.inputs.plan_calories,
            steps_delta=steps_delta,
            new_steps_target=self.inputs.steps_target + steps_delta,
            observed_weekly_change_kg=self.trend.weekly_change_kg,
            expected_weekly_change_kg=self.inputs.expected_weekly_change_kg,
            adherence_pct=self.adherence,
            trend=self.trend,
            tdee=self.tdee,
            next_review_on=when,
            notes=tuple(self.notes),
        )


def next_review_date(inputs: AdjustmentInputs) -> date:
    """The day the next review is due."""
    anchor = inputs.last_adjustment_on or inputs.plan_started_on
    return anchor + timedelta(days=inputs.review_interval_days)


def decide(inputs: AdjustmentInputs) -> AdjustmentDecision:
    """Run one review for ``inputs``."""
    due_on = next_review_date(inputs)
    window_start = inputs.last_adjustment_on or inputs.plan_started_on
    trend = estimate_trend(inputs.weights, window_start, inputs.today)
    # Expenditure is learnt from the longest recent history (across calorie changes:
    # mean intake versus total weight change), not just from this review window.
    history_start = max(
        inputs.plan_started_on, inputs.today - timedelta(days=TDEE_HISTORY_DAYS - 1)
    )
    history = estimate_trend(inputs.weights, history_start, inputs.today)
    tdee = estimate_tdee(inputs.theoretical_tdee_kcal, inputs.intakes, history)
    review = Review(inputs, trend, tdee, mean_adherence(inputs.intakes, window_start, inputs.today))

    if inputs.today < due_on:
        review.notes.append(Note("adjust.too_early", params={"next_review": due_on.isoformat()}))
        return review.decision(
            "wait", AdjustmentReason.SCHEDULED_REVIEW, review_due=False, next_review=due_on
        )

    if trend.weekly_change_kg is None:
        review.notes.append(
            Note(
                "adjust.insufficient_data",
                level="warning",
                params={"weight_days": trend.weight_days, "span_days": trend.span_days},
            )
        )
        return review.decision(
            "wait",
            AdjustmentReason.SCHEDULED_REVIEW,
            next_review=inputs.today + timedelta(days=7),
        )

    review.notes.append(
        Note(
            "adjust.trend_raw" if review.sparse else "adjust.trend",
            params={"observed": review.observed, "expected": review.expected},
        )
    )
    if review.sparse:
        review.notes.append(
            Note(
                "adjust.sparse_trend",
                params={"weight_days": trend.weight_days, "span_days": trend.span_days},
            )
        )
        if abs(review.observed - review.expected) < SPARSE_NOISE_KG:
            review.notes.append(Note("adjust.keep"))
            return review.decision("keep", AdjustmentReason.SCHEDULED_REVIEW)
    if tdee.observed_kcal is not None:
        review.notes.append(
            Note(
                "adjust.tdee_observed",
                params={
                    "observed": tdee.observed_kcal,
                    "theoretical": tdee.theoretical_kcal,
                    "blended": tdee.blended_kcal,
                    "days": tdee.data_days,
                },
            )
        )

    if inputs.mode == "deficit":
        return _deficit_rules(review)
    if inputs.mode == "surplus":
        return _surplus_rules(review)
    return _maintenance_rules(review)


def _deficit_rules(review: Review) -> AdjustmentDecision:
    inputs = review.inputs
    weight = inputs.current_weight_kg
    max_loss = safety.max_weekly_loss_kg(weight)
    floor = safety.calorie_floor(inputs.sex, inputs.bmr_kcal)
    loss = -review.observed
    expected_loss = -review.expected

    if loss > max_loss:
        needed = (loss - max_loss) * KCAL_PER_KG / 7
        delta = min(needed, inputs.plan_calories * MAX_RAISE_FRACTION)
        new_calories = _round_smaller_raise(inputs.plan_calories + delta)
        review.notes.append(
            Note(
                "adjust.loss_too_fast",
                level="warning",
                params={"observed": round(loss, 2), "max_weekly": round(max_loss, 2)},
            )
        )
        review.notes.append(
            _change_note("adjust.increase_calories", inputs.plan_calories, new_calories)
        )
        return review.decision(
            "increase_calories", AdjustmentReason.LOSS_TOO_FAST, new_calories=new_calories
        )

    stalled = loss < STALL_THRESHOLD_KG
    if stalled and inputs.weeks_in_deficit >= DIET_BREAK_WEEKS:
        maintenance = _round(review.tdee.blended_kcal)
        review.notes.append(
            Note(
                "adjust.diet_break",
                level="warning",
                params={"weeks": inputs.weeks_in_deficit, "calories": maintenance},
            )
        )
        return review.decision("diet_break", AdjustmentReason.DIET_BREAK, new_calories=maintenance)
    if stalled and inputs.weeks_in_deficit >= REFEED_WEEKS and inputs.stalled_reviews >= 1:
        maintenance = _round(review.tdee.blended_kcal)
        review.notes.append(
            Note(
                "adjust.refeed", params={"weeks": inputs.weeks_in_deficit, "calories": maintenance}
            )
        )
        return review.decision("refeed", AdjustmentReason.REFEED)

    if loss < expected_loss * SLOW_FRACTION:
        if review.adherence is not None and review.adherence < ADHERENCE_THRESHOLD:
            review.notes.append(
                Note(
                    "adjust.adherence_first",
                    level="warning",
                    params={"adherence": review.adherence},
                )
            )
            return review.decision("adherence", AdjustmentReason.LOSS_TOO_SLOW)
        needed = (expected_loss - loss) * KCAL_PER_KG / 7
        max_cut = inputs.plan_calories * review.step_limit
        delta = min(needed, max_cut)
        if delta < needed:
            review.notes.append(
                Note("adjust.capped_step", params={"pct": round(review.step_limit * 100)})
            )
        new_calories = _round_smaller_cut(inputs.plan_calories - delta)
        # Never below the floor, never faster than the weekly cap after the cut.
        min_for_cap = inputs.plan_calories - (max_loss - loss) * KCAL_PER_KG / 7
        lowest = max(floor, min_for_cap)
        if new_calories < lowest:
            new_calories = int(math.ceil(lowest / ROUND_TO) * ROUND_TO)
        if new_calories >= inputs.plan_calories:
            steps = min(STEP_INCREMENT, MAX_STEPS_TARGET - inputs.steps_target)
            review.notes.append(Note("adjust.floor_reached", params={"floor": round(floor)}))
            if steps <= 0:
                review.notes.append(Note("adjust.keep"))
                return review.decision("keep", AdjustmentReason.LOSS_TOO_SLOW)
            review.notes.append(Note("adjust.add_steps", params={"steps": steps}))
            return review.decision("add_steps", AdjustmentReason.LOSS_TOO_SLOW, steps_delta=steps)
        review.notes.append(
            _change_note("adjust.reduce_calories", inputs.plan_calories, new_calories)
        )
        return review.decision(
            "reduce_calories", AdjustmentReason.LOSS_TOO_SLOW, new_calories=new_calories
        )

    review.notes.append(Note("adjust.keep"))
    return review.decision("keep", AdjustmentReason.SCHEDULED_REVIEW)


def _reduce_or_steps(review: Review, wanted: int, reason: AdjustmentReason) -> AdjustmentDecision:
    """Bajada de calorías que nunca cruza el suelo de seguridad.

    Si el suelo (o un plan que ya está por debajo de él) no deja sitio para
    bajar, la palanca son los pasos: subir el número y llamarlo "bajada" era
    mentir en el aviso y en el histórico.
    """
    inputs = review.inputs
    floor = safety.calorie_floor(inputs.sex, inputs.bmr_kcal)
    lowest = int(math.ceil(floor / ROUND_TO) * ROUND_TO)
    new_calories = max(wanted, lowest)
    if new_calories >= inputs.plan_calories:
        review.notes.append(Note("adjust.floor_reached", params={"floor": round(floor)}))
        steps = min(STEP_INCREMENT, MAX_STEPS_TARGET - inputs.steps_target)
        if steps <= 0:
            review.notes.append(Note("adjust.keep"))
            return review.decision("keep", reason)
        review.notes.append(Note("adjust.add_steps", params={"steps": steps}))
        return review.decision("add_steps", reason, steps_delta=steps)
    review.notes.append(_change_note("adjust.reduce_calories", inputs.plan_calories, new_calories))
    return review.decision("reduce_calories", reason, new_calories=new_calories)


def _surplus_rules(review: Review) -> AdjustmentDecision:
    inputs = review.inputs
    weight = inputs.current_weight_kg
    if review.observed > weight * SURPLUS_FAST_FRACTION and review.observed > review.expected:
        wanted = _round_smaller_cut(inputs.plan_calories * (1 - review.step_limit))
        return _reduce_or_steps(review, wanted, AdjustmentReason.GAIN_TOO_FAST)
    if review.observed < review.expected * SLOW_FRACTION:
        if review.adherence is not None and review.adherence < ADHERENCE_THRESHOLD:
            review.notes.append(
                Note(
                    "adjust.adherence_first",
                    level="warning",
                    params={"adherence": review.adherence},
                )
            )
            return review.decision("adherence", AdjustmentReason.GAIN_TOO_SLOW)
        new_calories = _round_smaller_raise(inputs.plan_calories * (1 + review.step_limit))
        review.notes.append(
            _change_note("adjust.increase_calories", inputs.plan_calories, new_calories)
        )
        return review.decision(
            "increase_calories", AdjustmentReason.GAIN_TOO_SLOW, new_calories=new_calories
        )
    review.notes.append(Note("adjust.keep"))
    return review.decision("keep", AdjustmentReason.SCHEDULED_REVIEW)


def _maintenance_rules(review: Review) -> AdjustmentDecision:
    inputs = review.inputs
    if review.observed < -MAINTENANCE_DRIFT_KG:
        new_calories = _round_smaller_raise(inputs.plan_calories * (1 + MAINTENANCE_STEP))
        review.notes.append(
            _change_note("adjust.increase_calories", inputs.plan_calories, new_calories)
        )
        return review.decision(
            "increase_calories", AdjustmentReason.LOSS_TOO_FAST, new_calories=new_calories
        )
    if review.observed > MAINTENANCE_DRIFT_KG:
        wanted = _round_smaller_cut(inputs.plan_calories * (1 - MAINTENANCE_STEP))
        return _reduce_or_steps(review, wanted, AdjustmentReason.GAIN_TOO_FAST)
    review.notes.append(Note("adjust.keep"))
    return review.decision("keep", AdjustmentReason.SCHEDULED_REVIEW)


def _round(value: float) -> int:
    """Nearest multiple of ``ROUND_TO`` (for targets, not for capped steps)."""
    return int(round(value / ROUND_TO) * ROUND_TO)


def _round_smaller_cut(value: float) -> int:
    """Round a lowered intake up, so the cut never exceeds its cap."""
    return int(math.ceil(value / ROUND_TO) * ROUND_TO)


def _round_smaller_raise(value: float) -> int:
    """Round a raised intake down, so the increase never exceeds its cap."""
    return int(math.floor(value / ROUND_TO) * ROUND_TO)


def _change_note(code: str, old: int, new: int) -> Note:
    delta = new - old
    return Note(
        code,
        params={
            "delta": abs(delta),
            "pct": round(abs(delta) / old * 100, 1),
            "old": old,
            "new": new,
        },
    )
