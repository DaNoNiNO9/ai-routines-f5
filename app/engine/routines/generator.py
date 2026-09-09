"""Routine generator orchestrator.

    inputs + catalogue -> split and day templates -> one exercise per slot
    (hard filters, deterministic scoring) -> volume targets scaled to the time
    available -> sets adjusted to the targets (priorities) -> push/pull balance
    -> trimmed to the session time -> pattern coverage check -> prescription
    (reps, RIR, rest, tempo, increments) -> mesocycle and deload -> cardio

Pure function: no Flask, no database. Returns a complete ``RoutinePlan`` or a
blocked one with the reasons.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.engine.enums import MovementPattern, MuscleGroup, SplitType
from app.engine.routines import prescription as rx
from app.engine.routines import volume as vol
from app.engine.routines.cardio import cardio_prescription
from app.engine.routines.catalog import (
    allowed_level,
    equipment_available,
    has_shoulder_history,
    usable_exercises,
)
from app.engine.routines.selection import pick, relaxed_ceiling
from app.engine.routines.splits import (
    ACCESSORY,
    ISOLATION,
    MAIN,
    SECONDARY,
    DayTemplate,
    Slot,
    day_templates,
    select_split,
)
from app.engine.routines.types import (
    ExerciseInfo,
    ExercisePrescription,
    RoutineDayPlan,
    RoutineInputs,
    RoutinePlan,
)
from app.engine.types import Note

MAX_DAYS = 6
PUSH_PATTERNS = {MovementPattern.HORIZONTAL_PUSH, MovementPattern.VERTICAL_PUSH}
PULL_PATTERNS = {MovementPattern.HORIZONTAL_PULL, MovementPattern.VERTICAL_PULL}
REQUIRED_PATTERNS = (
    MovementPattern.HORIZONTAL_PUSH,
    MovementPattern.VERTICAL_PUSH,
    MovementPattern.HORIZONTAL_PULL,
    MovementPattern.VERTICAL_PULL,
    MovementPattern.KNEE_DOMINANT,
    MovementPattern.HIP_DOMINANT,
    MovementPattern.CORE,
)
PATTERN_SUGGESTION: dict[MovementPattern, str] = {
    MovementPattern.VERTICAL_PULL: "una barra de dominadas o bandas",
    MovementPattern.HORIZONTAL_PULL: "mancuernas, bandas o un TRX",
    MovementPattern.VERTICAL_PUSH: "mancuernas o bandas",
    MovementPattern.HORIZONTAL_PUSH: "mancuernas o bandas",
    MovementPattern.KNEE_DOMINANT: "mancuernas o una kettlebell",
    MovementPattern.HIP_DOMINANT: "mancuernas, kettlebell o bandas",
    MovementPattern.CORE: "una esterilla",
}
PULL_RATIO_TARGET = 1.0
PULL_RATIO_WITH_SHOULDER_HISTORY = 1.3
RATIO_TOLERANCE = 0.1
TIME_TOLERANCE = 1.05
MIN_ITEMS_PER_DAY = 3
VOLUME_PASSES = 4
AVERAGE_SET_MINUTES = 2.5
MIN_SCALED_LOW = 3
ROLE_TRIM_ORDER = (ISOLATION, ACCESSORY, SECONDARY, MAIN)


@dataclass
class Draft:
    """A slot filled with an exercise and a set count, still adjustable."""

    slot: Slot
    exercise: ExerciseInfo
    sets: int
    notes: list[Note] = field(default_factory=list)


@dataclass
class DraftDay:
    """A day under construction."""

    template: DayTemplate
    items: list[Draft]
    notes: list[Note] = field(default_factory=list)
    trimmed: bool = False


def build_routine(inputs: RoutineInputs, exercises: list[ExerciseInfo]) -> RoutinePlan:
    """Generate the routine for ``inputs`` from the given catalogue."""
    notes: list[Note] = []
    if inputs.training_days_per_week == 0:
        return _blocked((Note("routine.no_days", level="error"),))
    days = min(inputs.training_days_per_week, MAX_DAYS)
    if inputs.training_days_per_week > MAX_DAYS:
        notes.append(Note("routine.days_capped"))

    tier = vol.experience_tier(inputs.training_experience)
    ceiling = allowed_level(inputs.training_experience)
    pool = usable_exercises(exercises, inputs, ceiling)
    relaxed = relaxed_ceiling(ceiling)
    relaxed_pool = usable_exercises(exercises, inputs, relaxed) if relaxed else pool
    if not pool and not relaxed_pool:
        return _blocked((Note("routine.nothing_possible", level="error"),))

    split = select_split(days, inputs.training_experience)
    templates = day_templates(split, days)
    notes.append(Note("routine.split", params={"split": split.value, "days": days}))

    used: dict[str, int] = {}
    draft_days = [_fill_day(template, pool, relaxed_pool, inputs, used) for template in templates]
    if not any(day.items for day in draft_days):
        return _blocked((Note("routine.nothing_possible", level="error"),))

    targets = vol.volume_targets(inputs.training_experience, inputs.priority_muscles)
    targets = _scale_targets_to_time(targets, days, inputs.session_minutes, notes)
    if inputs.priority_muscles:
        _ensure_priority_slots(draft_days, inputs, pool, used, notes)
        notes.append(
            Note(
                "routine.priority_applied",
                params={"muscles": ", ".join(m.value for m in inputs.priority_muscles)},
            )
        )
    _adjust_volume(draft_days, targets)
    _balance_push_pull(draft_days, inputs, pool, used, notes, allow_additions=True)
    _fit_time(draft_days, inputs, tier, notes)
    _balance_push_pull(draft_days, inputs, pool, used, notes, allow_additions=False)
    _check_coverage(draft_days, pool, exercises, inputs, notes)

    weeks, deload = rx.mesocycle_and_deload(tier, inputs.reported_fatigue)
    rir = rx.weekly_rir(weeks)
    notes.append(
        Note(
            "routine.mesocycle",
            params={"weeks": weeks, "deload": deload, "rir": "-".join(map(str, rir))},
        )
    )
    notes.append(Note("routine.double_progression"))

    day_plans = tuple(
        _finalise_day(index + 1, day, inputs, tier) for index, day in enumerate(draft_days)
    )
    week = [(draft.exercise, draft.sets) for day in draft_days for draft in day.items]
    table = vol.volume_table(week, targets, inputs.priority_muscles)
    for entry in table:
        if entry.status == "low":
            notes.append(
                Note(
                    "routine.volume_low",
                    level="warning",
                    params={
                        "muscle": entry.muscle.value,
                        "planned": entry.planned_sets,
                        "target_min": entry.target_min,
                    },
                )
            )
    push, pull = _push_pull_sets(draft_days)
    ratio = round(pull / push, 2) if push else 0.0
    notes.append(Note("routine.push_pull", params={"push": push, "pull": pull, "ratio": ratio}))

    return RoutinePlan(
        status="ok",
        split_type=split,
        days_per_week=days,
        mesocycle_weeks=weeks,
        deload_every_weeks=deload,
        weekly_rir=rir,
        days=day_plans,
        volume=table,
        push_sets=push,
        pull_sets=pull,
        pull_to_push_ratio=ratio,
        cardio=cardio_prescription(inputs),
        notes=tuple(notes),
    )


def _blocked(reasons: tuple[Note, ...]) -> RoutinePlan:
    return RoutinePlan(
        status="blocked",
        split_type=None,
        days_per_week=0,
        mesocycle_weeks=0,
        deload_every_weeks=0,
        weekly_rir=(),
        blocked_reasons=reasons,
    )


def _fill_day(
    template: DayTemplate,
    pool: list[ExerciseInfo],
    relaxed_pool: list[ExerciseInfo],
    inputs: RoutineInputs,
    used: dict[str, int],
) -> DraftDay:
    tier = vol.experience_tier(inputs.training_experience)
    day = DraftDay(template, [])
    chosen_today: set[str] = set()
    for slot in template.slots:
        slot_notes: list[Note] = []
        exercise = pick(pool, slot, inputs, used, exclude=chosen_today)
        if exercise is None and relaxed_pool is not pool:
            exercise = pick(relaxed_pool, slot, inputs, used, exclude=chosen_today)
            if exercise is not None:
                slot_notes.append(Note("routine.level_relaxed", params={"exercise": exercise.name}))
        if exercise is None:
            level = "info" if slot.role == ISOLATION else "warning"
            day.notes.append(
                Note(
                    "routine.slot_unfilled",
                    level=level,
                    params={"pattern": slot.pattern.value, "day": template.name},
                )
            )
            continue
        used[exercise.slug] = used.get(exercise.slug, 0) + 1
        chosen_today.add(exercise.slug)
        day.items.append(Draft(slot, exercise, rx.default_sets(tier, slot.role), slot_notes))
    return day


def _scale_targets_to_time(
    targets: dict[MuscleGroup, tuple[int, int]], days: int, minutes: int, notes: list[Note]
) -> dict[MuscleGroup, tuple[int, int]]:
    """Shrink the weekly targets when the sessions cannot physically hold them."""
    feasible = days * max(0, minutes - rx.WARM_UP_MINUTES) / AVERAGE_SET_MINUTES
    total_low = sum(low for low, _ in targets.values())
    if total_low <= 0 or feasible >= total_low:
        return targets
    factor = feasible / total_low
    notes.append(Note("routine.volume_scaled_by_time", params={"pct": round((1 - factor) * 100)}))
    return {
        muscle: (
            max(MIN_SCALED_LOW, round(low * factor)),
            max(MIN_SCALED_LOW + 1, round(high * factor)),
        )
        for muscle, (low, high) in targets.items()
    }


def _ensure_priority_slots(
    days: list[DraftDay],
    inputs: RoutineInputs,
    pool: list[ExerciseInfo],
    used: dict[str, int],
    notes: list[Note],
) -> None:
    """A priority muscle without a dedicated exercise gets an isolation slot added."""
    tier = vol.experience_tier(inputs.training_experience)
    for muscle in inputs.priority_muscles:
        if any(draft.exercise.primary is muscle for day in days for draft in day.items):
            continue
        target_day = min(days, key=lambda day: (len(day.items), days.index(day)))
        slot = Slot(MovementPattern.ISOLATION, ISOLATION, muscle)
        exclude = {d.exercise.slug for d in target_day.items}
        exercise = pick(pool, slot, inputs, used, exclude=exclude)
        if exercise is None:
            continue
        used[exercise.slug] = used.get(exercise.slug, 0) + 1
        target_day.items.append(Draft(slot, exercise, rx.default_sets(tier, ISOLATION)))
        notes.append(
            Note(
                "routine.priority_slot_added",
                params={"muscle": muscle.value, "day": target_day.template.name},
            )
        )


def _adjust_volume(days: list[DraftDay], targets: dict[MuscleGroup, tuple[int, int]]) -> None:
    """Move set counts towards the weekly targets, one set at a time, a few passes."""
    for _ in range(VOLUME_PASSES):
        changed = False
        totals = vol.weekly_volume([(d.exercise, d.sets) for day in days for d in day.items])
        for muscle, (low, high) in targets.items():
            planned = totals.get(muscle, 0.0)
            drafts = [d for day in days for d in day.items if d.exercise.primary is muscle]
            if planned < low:
                candidates = [d for d in drafts if d.sets < rx.MAX_SETS]
                if candidates:
                    candidates.sort(key=lambda d: (d.sets, ROLE_TRIM_ORDER.index(d.slot.role)))
                    candidates[0].sets += 1
                    changed = True
            elif planned > high:
                candidates = [d for d in drafts if d.sets > rx.MIN_SETS]
                if candidates:
                    candidates.sort(key=lambda d: (-d.sets, -ROLE_TRIM_ORDER.index(d.slot.role)))
                    candidates[0].sets -= 1
                    changed = True
        if not changed:
            break


def _push_pull_sets(days: list[DraftDay]) -> tuple[int, int]:
    push = sum(d.sets for day in days for d in day.items if d.exercise.pattern in PUSH_PATTERNS)
    pull = sum(d.sets for day in days for d in day.items if d.exercise.pattern in PULL_PATTERNS)
    return push, pull


def _balance_push_pull(
    days: list[DraftDay],
    inputs: RoutineInputs,
    pool: list[ExerciseInfo],
    used: dict[str, int],
    notes: list[Note],
    allow_additions: bool,
) -> None:
    """Pulling sets at least match pushing sets (30 % more with shoulder history).

    First more sets on the pulling exercises, then an extra pulling accessory,
    and finally fewer pushing sets when the catalogue offers no more pulling.
    """
    target = PULL_RATIO_TARGET
    if has_shoulder_history(inputs.injuries):
        target = PULL_RATIO_WITH_SHOULDER_HISTORY
        if allow_additions:
            notes.append(Note("routine.pull_bias"))
    if _push_pull_sets(days)[0] == 0:
        return
    tier = vol.experience_tier(inputs.training_experience)
    guard = 0
    while _push_pull_sets(days)[1] < math.ceil(
        _push_pull_sets(days)[0] * (target - RATIO_TOLERANCE)
    ):
        guard += 1
        if guard > 40:
            break
        pull_drafts = [
            d
            for day in days
            for d in day.items
            if d.exercise.pattern in PULL_PATTERNS and d.sets < rx.MAX_SETS
        ]
        if pull_drafts and allow_additions:
            pull_drafts.sort(key=lambda d: (d.sets, ROLE_TRIM_ORDER.index(d.slot.role)))
            pull_drafts[0].sets += 1
            continue
        target_day = min(
            days,
            key=lambda day: sum(d.sets for d in day.items if d.exercise.pattern in PULL_PATTERNS),
        )
        slot = Slot(MovementPattern.HORIZONTAL_PULL, ACCESSORY, MuscleGroup.SHOULDERS)
        exclude = {d.exercise.slug for d in target_day.items}
        exercise = pick(pool, slot, inputs, used, exclude=exclude) if allow_additions else None
        if exercise is not None and used.get(exercise.slug, 0) < 2:
            used[exercise.slug] = used.get(exercise.slug, 0) + 1
            target_day.items.append(Draft(slot, exercise, rx.default_sets(tier, ACCESSORY)))
            continue
        push_drafts = [
            d
            for day in days
            for d in day.items
            if d.exercise.pattern in PUSH_PATTERNS and d.sets > rx.MIN_SETS
        ]
        if not push_drafts:
            if not allow_additions:
                notes.append(Note("routine.push_pull_unbalanced", level="warning"))
            break
        push_drafts.sort(key=lambda d: (-d.sets, -ROLE_TRIM_ORDER.index(d.slot.role)))
        push_drafts[0].sets -= 1


def _day_minutes(day: DraftDay, inputs: RoutineInputs, tier: str) -> int:
    items = [
        (
            d.exercise,
            d.slot.role,
            d.sets,
            rx.rep_range(d.slot.role, inputs.goal, tier, d.exercise.pattern)[1],
        )
        for d in day.items
    ]
    return rx.estimate_minutes(items)


def _fit_time(days: list[DraftDay], inputs: RoutineInputs, tier: str, notes: list[Note]) -> None:
    """Trim sets, then whole isolation/accessory exercises, until the day fits."""
    budget = inputs.session_minutes
    for day in days:
        while _day_minutes(day, inputs, tier) > budget * TIME_TOLERANCE:
            if not _trim_once(day):
                break
            day.trimmed = True
        estimated = _day_minutes(day, inputs, tier)
        if day.trimmed:
            notes.append(
                Note("routine.time_trimmed", params={"day": day.template.name, "minutes": budget})
            )
        if estimated > budget * TIME_TOLERANCE:
            notes.append(
                Note(
                    "routine.session_too_long",
                    level="warning",
                    params={"day": day.template.name, "estimated": estimated, "budget": budget},
                )
            )


def _trim_once(day: DraftDay) -> bool:
    """One trimming step in priority order; returns False when nothing else can go."""
    for role in ROLE_TRIM_ORDER:
        drafts = [d for d in day.items if d.slot.role == role and d.sets > rx.MIN_SETS]
        if drafts:
            drafts.sort(key=lambda d: (d.exercise.pattern in PULL_PATTERNS, -d.sets))
            drafts[0].sets -= 1
            return True
    for role in (ISOLATION, ACCESSORY):
        drafts = [d for d in day.items if d.slot.role == role]
        if drafts and len(day.items) > MIN_ITEMS_PER_DAY:
            day.items.remove(drafts[-1])
            return True
    for role in (SECONDARY, MAIN):
        drafts = [d for d in day.items if d.slot.role == role and d.sets > 1]
        if drafts:
            drafts.sort(key=lambda d: (d.exercise.pattern in PULL_PATTERNS, -d.sets))
            drafts[0].sets -= 1
            return True
    return False


def _check_coverage(
    days: list[DraftDay],
    pool: list[ExerciseInfo],
    catalogue: list[ExerciseInfo],
    inputs: RoutineInputs,
    notes: list[Note],
) -> None:
    """Explain every required pattern that is missing from the week, and why."""
    present = {d.exercise.pattern for day in days for d in day.items}
    in_pool = {exercise.pattern for exercise in pool}
    with_equipment = {
        exercise.pattern
        for exercise in catalogue
        if equipment_available(exercise, inputs.equipment)
    }
    trimmed = any(day.trimmed for day in days)
    for pattern in REQUIRED_PATTERNS:
        if pattern in present:
            continue
        params = {"pattern": pattern.value}
        if pattern in in_pool:
            code = "routine.pattern_trimmed" if trimmed else "routine.pattern_not_scheduled"
            notes.append(Note(code, params=params))
        elif pattern in with_equipment:
            notes.append(Note("routine.pattern_blocked_by_injury", level="warning", params=params))
        else:
            params["suggestion"] = PATTERN_SUGGESTION[pattern]
            notes.append(Note("routine.pattern_missing", level="warning", params=params))


def _finalise_day(index: int, day: DraftDay, inputs: RoutineInputs, tier: str) -> RoutineDayPlan:
    prescriptions: list[ExercisePrescription] = []
    for draft in day.items:
        rep_min, rep_max = rx.rep_range(draft.slot.role, inputs.goal, tier, draft.exercise.pattern)
        rir_start, rir_end = rx.rir_bounds(draft.slot.role)
        prescriptions.append(
            ExercisePrescription(
                slug=draft.exercise.slug,
                name=draft.exercise.name,
                pattern=draft.exercise.pattern,
                primary=draft.exercise.primary,
                role=draft.slot.role,
                sets=draft.sets,
                rep_min=rep_min,
                rep_max=rep_max,
                rir_start=rir_start,
                rir_end=rir_end,
                rest_seconds=rx.rest_seconds(draft.exercise, draft.slot.role),
                tempo=rx.tempo_for(draft.exercise, draft.slot.role),
                load_increment_kg=rx.load_increment_kg(draft.exercise, inputs.sex),
                is_unilateral=draft.exercise.is_unilateral,
                notes=tuple(draft.notes),
            )
        )
    return RoutineDayPlan(
        index=index,
        name=day.template.name,
        focus=day.template.focus,
        exercises=tuple(prescriptions),
        estimated_minutes=_day_minutes(day, inputs, tier),
        notes=tuple(day.notes),
    )


def split_label(split: SplitType) -> str:
    """Stable string for templates and JSON."""
    return split.value
