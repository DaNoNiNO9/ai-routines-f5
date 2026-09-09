"""Workout sessions: start, log sets, substitute exercises, finish, history and progress.

A session follows a routine day. Sets are stored as they happen (one row per
session, exercise and set index; logging the same index again overwrites
it). Nothing here commits: the routes own the transaction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.engine.enums import SetType, WorkoutStatus
from app.extensions import db
from app.models import (
    Exercise,
    Profile,
    Routine,
    RoutineDay,
    RoutineExercise,
    SetLog,
    User,
    WorkoutSession,
)
from app.models.base import utcnow
from app.services import dashboard

EXTRA_SETS_ALLOWED = 2
EPLEY_DIVISOR = 30
MAX_HISTORY = 50


class WorkoutError(Exception):
    """A logging action that does not apply (wrong session, closed session, bad set)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Performance:
    """Working sets of one exercise in a previous session."""

    day: date
    sets: tuple[tuple[int, float], ...]  # (reps, kg)

    @property
    def top_weight(self) -> float:
        """Heaviest working set."""
        return max(kg for _reps, kg in self.sets)

    def summary(self) -> str:
        """``"60 kg x 8, 8, 7"``-style line (weights collapsed when they are all the same)."""
        weights = {kg for _reps, kg in self.sets}
        reps = ", ".join(str(reps) for reps, _kg in self.sets)
        if len(weights) == 1:
            return f"{_fmt(self.top_weight)} kg x {reps}"
        return " · ".join(f"{_fmt(kg)}x{reps}" for reps, kg in self.sets)


def _fmt(value: float) -> str:
    return f"{value:g}"


@dataclass
class SetRow:
    """One prescribed (or extra) set and what was logged for it."""

    index: int
    log: SetLog | None


@dataclass
class ExerciseBlock:
    """Everything the session page shows for one prescribed exercise."""

    item: RoutineExercise
    exercise: Exercise
    is_substituted: bool
    rows: list[SetRow]
    previous: Performance | None
    suggested_kg: float | None
    alternatives: list[Exercise] = field(default_factory=list)

    @property
    def done(self) -> int:
        """Sets logged so far."""
        return sum(1 for row in self.rows if row.log is not None)


@dataclass(frozen=True)
class ExerciseSummary:
    """Best set of an exercise in a session, versus the best before it."""

    exercise: Exercise
    sets: int
    top_weight: float
    top_reps: int
    est_1rm: float
    previous_1rm: float | None

    @property
    def is_pr(self) -> bool:
        """New best estimated one-rep max."""
        return self.previous_1rm is None or self.est_1rm > self.previous_1rm + 0.01


@dataclass(frozen=True)
class SessionSummary:
    """Totals of a session."""

    session: WorkoutSession
    working_sets: int
    total_reps: int
    tonnage_kg: float
    duration_minutes: int
    exercises: tuple[ExerciseSummary, ...] = ()

    @property
    def prs(self) -> int:
        """Number of exercises with a new estimated one-rep max."""
        return sum(1 for item in self.exercises if item.is_pr)


def estimated_1rm(weight_kg: float, reps: int) -> float:
    """Epley estimate (``w * (1 + reps/30)``); the weight itself for a single."""
    if reps <= 1:
        return round(weight_kg, 1)
    return round(weight_kg * (1 + reps / EPLEY_DIVISOR), 1)


def mesocycle_week(routine: Routine, today: date) -> int:
    """Week of the mesocycle (1-based, cycling after the last week)."""
    if routine.starts_on is None:
        return 1
    elapsed = max(0, (today - routine.starts_on).days)
    return (elapsed // 7) % routine.mesocycle_weeks + 1


def active_session(user: User) -> WorkoutSession | None:
    """The session in progress, if any (at most one)."""
    return db.session.scalar(
        select(WorkoutSession)
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.status == WorkoutStatus.IN_PROGRESS,
            WorkoutSession.deleted_at.is_(None),
        )
        .order_by(WorkoutSession.started_at.desc())
    )


def get_session(user: User, session_id: int) -> WorkoutSession | None:
    """A session of ``user`` (never someone else's)."""
    return db.session.scalar(
        select(WorkoutSession)
        .where(
            WorkoutSession.id == session_id,
            WorkoutSession.user_id == user.id,
            WorkoutSession.deleted_at.is_(None),
        )
        .options(selectinload(WorkoutSession.sets))
    )


def start_session(user: User, routine: Routine, day: RoutineDay, today: date) -> WorkoutSession:
    """Open a session for ``day`` (or return the one already in progress)."""
    current = active_session(user)
    if current is not None:
        return current
    session = WorkoutSession(
        user=user,
        routine_day=day,
        started_at=utcnow(),
        status=WorkoutStatus.IN_PROGRESS,
        mesocycle_week=mesocycle_week(routine, today),
        substitutions={},
    )
    db.session.add(session)
    db.session.flush()
    return session


def _require_open(session: WorkoutSession) -> None:
    if session.status is not WorkoutStatus.IN_PROGRESS:
        raise WorkoutError("closed")


def effective_exercise(session: WorkoutSession, item: RoutineExercise) -> Exercise:
    """The exercise actually done for a prescription (a substitute or the original)."""
    chosen = (session.substitutions or {}).get(str(item.id))
    if chosen is not None:
        exercise = db.session.get(Exercise, int(chosen))
        if exercise is not None:
            return exercise
    return item.exercise


def substitute(
    session: WorkoutSession,
    item: RoutineExercise,
    exercise: Exercise | None,
    profile: Profile,
    equipment: frozenset[str],
) -> None:
    """Use ``exercise`` instead of the prescribed one for this session (``None`` restores it).

    Raises:
        WorkoutError: If the session is closed, sets were already logged for the
            prescription, or the exercise is not a usable alternative.
    """
    _require_open(session)
    if any(row.routine_exercise_id == item.id for row in session.sets):
        raise WorkoutError("sets_logged")
    current = dict(session.substitutions or {})
    if exercise is None:
        current.pop(str(item.id), None)
    else:
        allowed = {alt.id for alt in dashboard.usable_alternatives(item, profile, equipment)}
        if exercise.id not in allowed:
            raise WorkoutError("not_an_alternative")
        current[str(item.id)] = exercise.id
    session.substitutions = current


def log_set(
    session: WorkoutSession,
    item: RoutineExercise,
    set_index: int,
    reps: int,
    weight_kg: float,
    rir: int | None,
    set_type: SetType = SetType.WORKING,
) -> SetLog:
    """Record (or overwrite) one set of a prescribed exercise.

    Raises:
        WorkoutError: If the session is closed or the set index is out of range.
    """
    _require_open(session)
    if not 1 <= set_index <= item.sets + EXTRA_SETS_ALLOWED:
        raise WorkoutError("bad_index")
    exercise = effective_exercise(session, item)
    row = next(
        (
            existing
            for existing in session.sets
            if existing.exercise_id == exercise.id and existing.set_index == set_index
        ),
        None,
    )
    if row is None:
        row = SetLog(
            session=session,
            exercise=exercise,
            routine_exercise=item,
            set_index=set_index,
            set_type=set_type,
            reps=reps,
            weight_kg=weight_kg,
            rir=rir,
            completed_at=utcnow(),
        )
        session.sets.append(row)
    else:
        row.reps = reps
        row.weight_kg = weight_kg
        row.rir = rir
        row.set_type = set_type
        row.completed_at = utcnow()
    db.session.flush()
    return row


def delete_set(session: WorkoutSession, set_id: int) -> None:
    """Remove a logged set.

    Raises:
        WorkoutError: If the session is closed or the set is not in it.
    """
    _require_open(session)
    row = next((existing for existing in session.sets if existing.id == set_id), None)
    if row is None:
        raise WorkoutError("not_found")
    session.sets.remove(row)
    db.session.flush()


def finish(session: WorkoutSession, perceived_fatigue: int | None, notes: str | None) -> None:
    """Close the session as completed (a session without sets is abandoned instead)."""
    _require_open(session)
    session.finished_at = utcnow()
    session.perceived_fatigue = perceived_fatigue
    session.notes = notes
    session.status = WorkoutStatus.COMPLETED if session.sets else WorkoutStatus.ABANDONED


def abandon(session: WorkoutSession) -> None:
    """Close the session without counting it."""
    _require_open(session)
    session.finished_at = utcnow()
    session.status = WorkoutStatus.ABANDONED


def last_performance(
    user: User, item: RoutineExercise, exercise: Exercise, before: WorkoutSession
) -> Performance | None:
    """Working sets of the most recent completed session with this exercise."""
    previous = db.session.scalar(
        select(WorkoutSession)
        .join(SetLog, SetLog.workout_session_id == WorkoutSession.id)
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.status == WorkoutStatus.COMPLETED,
            WorkoutSession.id != before.id,
            SetLog.exercise_id == exercise.id,
            SetLog.set_type == SetType.WORKING,
        )
        .order_by(WorkoutSession.started_at.desc(), WorkoutSession.id.desc())
    )
    if previous is None:
        return None
    sets = tuple(
        (row.reps, row.weight_kg)
        for row in sorted(previous.sets, key=lambda row: row.set_index)
        if row.exercise_id == exercise.id and row.set_type is SetType.WORKING
    )
    if not sets:
        return None
    del item  # the prescription may differ between routine versions; the exercise is what counts
    return Performance(day=previous.started_at.date(), sets=sets)


def suggest_load(item: RoutineExercise, previous: Performance | None) -> float | None:
    """Double progression: same load until every set reaches the top of the range."""
    if previous is None:
        return None
    top = previous.top_weight
    if all(reps >= item.rep_max for reps, _kg in previous.sets):
        return round(top + (item.load_increment_kg or 0), 2)
    return top


def session_blocks(
    user: User, session: WorkoutSession, profile: Profile, equipment: frozenset[str]
) -> list[ExerciseBlock]:
    """What the live page shows: one block per prescribed exercise."""
    day = session.routine_day
    if day is None:
        return []
    blocks: list[ExerciseBlock] = []
    for item in day.exercises:
        exercise = effective_exercise(session, item)
        logged = {
            row.set_index: row
            for row in session.sets
            if row.exercise_id == exercise.id and row.routine_exercise_id == item.id
        }
        count = max(item.sets, *(logged.keys() or [0]))
        rows = [SetRow(index=index, log=logged.get(index)) for index in range(1, count + 1)]
        previous = last_performance(user, item, exercise, session)
        blocks.append(
            ExerciseBlock(
                item=item,
                exercise=exercise,
                is_substituted=exercise.id != item.exercise_id,
                rows=rows,
                previous=previous,
                suggested_kg=suggest_load(item, previous),
                alternatives=dashboard.usable_alternatives(item, profile, equipment),
            )
        )
    return blocks


def _best_1rm_before(user: User, exercise_id: int, before: WorkoutSession) -> float | None:
    rows = db.session.scalars(
        select(SetLog)
        .join(WorkoutSession, SetLog.workout_session_id == WorkoutSession.id)
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.status == WorkoutStatus.COMPLETED,
            WorkoutSession.started_at < before.started_at,
            SetLog.exercise_id == exercise_id,
            SetLog.set_type == SetType.WORKING,
            SetLog.reps >= 1,
        )
    ).all()
    if not rows:
        return None
    return max(estimated_1rm(row.weight_kg, row.reps) for row in rows)


def summarise(user: User, session: WorkoutSession, now: datetime | None = None) -> SessionSummary:
    """Totals and per-exercise best sets of a session."""
    working = [row for row in session.sets if row.set_type is SetType.WORKING]
    end = session.finished_at or now or utcnow()
    duration = max(0, int((end - session.started_at).total_seconds() // 60))
    by_exercise: dict[int, list[SetLog]] = {}
    for row in working:
        by_exercise.setdefault(row.exercise_id, []).append(row)
    exercises: list[ExerciseSummary] = []
    for exercise_id, rows in by_exercise.items():
        best = max(rows, key=lambda row: (estimated_1rm(row.weight_kg, row.reps), row.weight_kg))
        exercises.append(
            ExerciseSummary(
                exercise=best.exercise,
                sets=len(rows),
                top_weight=best.weight_kg,
                top_reps=best.reps,
                est_1rm=estimated_1rm(best.weight_kg, best.reps),
                previous_1rm=_best_1rm_before(user, exercise_id, session),
            )
        )
    return SessionSummary(
        session=session,
        working_sets=len(working),
        total_reps=sum(row.reps for row in working),
        tonnage_kg=round(sum(row.reps * row.weight_kg for row in working), 1),
        duration_minutes=duration,
        exercises=tuple(exercises),
    )


def history(user: User, limit: int = MAX_HISTORY) -> list[SessionSummary]:
    """Closed sessions, newest first."""
    sessions = db.session.scalars(
        select(WorkoutSession)
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.status != WorkoutStatus.IN_PROGRESS,
            WorkoutSession.deleted_at.is_(None),
        )
        .options(selectinload(WorkoutSession.sets))
        .order_by(WorkoutSession.started_at.desc())
        .limit(limit)
    ).all()
    return [summarise(user, session) for session in sessions]


def trained_exercises(user: User) -> list[Exercise]:
    """Exercises with at least one working set in a completed session, by name."""
    rows = db.session.scalars(
        select(Exercise)
        .join(SetLog, SetLog.exercise_id == Exercise.id)
        .join(WorkoutSession, SetLog.workout_session_id == WorkoutSession.id)
        .where(WorkoutSession.user_id == user.id, WorkoutSession.status == WorkoutStatus.COMPLETED)
        .distinct()
        .order_by(Exercise.name_es)
    ).all()
    return list(rows)


@dataclass(frozen=True)
class ProgressPoint:
    """Best set of an exercise in one session."""

    day: date
    top_weight: float
    top_reps: int
    est_1rm: float


def exercise_progress(user: User, exercise: Exercise) -> list[ProgressPoint]:
    """One point per completed session, oldest first."""
    sessions = db.session.scalars(
        select(WorkoutSession)
        .join(SetLog, SetLog.workout_session_id == WorkoutSession.id)
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.status == WorkoutStatus.COMPLETED,
            SetLog.exercise_id == exercise.id,
        )
        .distinct()
        .order_by(WorkoutSession.started_at)
    ).all()
    points: list[ProgressPoint] = []
    for session in sessions:
        rows = [
            row
            for row in session.sets
            if row.exercise_id == exercise.id and row.set_type is SetType.WORKING and row.reps >= 1
        ]
        if not rows:
            continue
        best = max(rows, key=lambda row: (estimated_1rm(row.weight_kg, row.reps), row.weight_kg))
        points.append(
            ProgressPoint(
                day=session.started_at.date(),
                top_weight=best.weight_kg,
                top_reps=best.reps,
                est_1rm=estimated_1rm(best.weight_kg, best.reps),
            )
        )
    return points
