"""Choosing a different exercise, by muscle group, with everything needed to decide.

Before, the routine offered «No me gusta: cámbialo» (the app picked the
replacement) and the session a bare list of names. Now the person browses every
exercise they can actually do (their equipment, their injuries, their level,
not set aside, not already in that day), grouped by the main muscle, with the
catalogue's own alternatives marked as recommended, opens any of them to see
the video and the steps, and chooses: only for today's session, or from now on
in the routine.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.engine.enums import MuscleGroup
from app.engine.routines import catalog
from app.engine.routines.types import InjuryInput
from app.extensions import db
from app.models import Exercise, Profile, RoutineExercise
from app.services.plans import exercise_info

logger = logging.getLogger(__name__)

ALL = "todos"


class SwapError(Exception):
    """The chosen exercise is not one this person can use in that slot."""


@dataclass(frozen=True)
class Candidate:
    """An exercise that could take the slot."""

    exercise: Exercise
    recommended: bool  # alternativa del catálogo para este ejercicio
    same_pattern: bool  # mismo movimiento (empuje horizontal, bisagra…)


@dataclass(frozen=True)
class Choice:
    """What the dialog shows: the muscle groups with options, and the options of one."""

    item: RoutineExercise
    muscles: list[tuple[str, int]]
    muscle: str
    candidates: list[Candidate]


def usable_pool(
    item: RoutineExercise, profile: Profile, equipment: frozenset[str]
) -> list[Exercise]:
    """Every exercise this person can do instead of ``item`` (never one already in that day)."""
    injuries = tuple(InjuryInput(injury.area, injury.severity) for injury in profile.injuries)
    ceiling = catalog.allowed_level(profile.training_experience)
    disliked = set(profile.disliked_exercises)
    in_day = {other.exercise_id for other in item.day.exercises}
    rows = db.session.scalars(
        select(Exercise)
        .where(Exercise.is_active.is_(True))
        .options(selectinload(Exercise.equipment))
        .order_by(Exercise.name_es)
    ).all()
    pool: list[Exercise] = []
    for row in rows:
        if row.id in in_day or row.slug in disliked:
            continue
        info = exercise_info(row, {})
        if (
            catalog.equipment_available(info, equipment)
            and not catalog.is_contraindicated(info, injuries)
            and catalog.level_ok(info, ceiling)
        ):
            pool.append(row)
    return pool


def choices(
    item: RoutineExercise, profile: Profile, equipment: frozenset[str], muscle: str | None
) -> Choice:
    """The options for ``item``, filtered by ``muscle`` (its own muscle by default)."""
    pool = usable_pool(item, profile, equipment)
    recommended = {link.alternative_id for link in item.exercise.alternatives}
    counts: dict[str, int] = {}
    for row in pool:
        counts[row.primary_muscle.value] = counts.get(row.primary_muscle.value, 0) + 1
    order = [m.value for m in MuscleGroup]
    muscles = [(m, counts[m]) for m in order if m in counts]
    own = item.exercise.primary_muscle.value
    wanted = muscle if muscle == ALL or muscle in counts else (own if own in counts else ALL)
    shown = [row for row in pool if wanted == ALL or row.primary_muscle.value == wanted]
    pattern = item.exercise.movement_pattern
    candidates = sorted(
        (Candidate(row, row.id in recommended, row.movement_pattern == pattern) for row in shown),
        key=lambda c: (not c.recommended, not c.same_pattern, c.exercise.display_name),
    )
    return Choice(item=item, muscles=muscles, muscle=wanted, candidates=candidates)


def apply_to_routine(
    item: RoutineExercise,
    exercise: Exercise,
    profile: Profile,
    equipment: frozenset[str],
    set_aside_old: bool = False,
) -> None:
    """Put ``exercise`` in the routine slot from now on (optionally setting the old one aside)."""
    if exercise.id not in {row.id for row in usable_pool(item, profile, equipment)}:
        raise SwapError("not_usable")
    old = item.exercise.slug
    if set_aside_old and old not in profile.disliked_exercises:
        profile.disliked_exercises = [*profile.disliked_exercises, old]
    item.exercise = exercise
    logger.info("User %s put %s instead of %s in the routine", profile.user_id, exercise.slug, old)
