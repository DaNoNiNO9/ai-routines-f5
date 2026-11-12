"""Workout sessions: start, log sets, substitute exercises, finish, history and progress.

A session follows a routine day. Sets are stored as they happen (one row per
session, exercise and set index; logging the same index again overwrites
it). Nothing here commits: the routes own the transaction.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import case, func, select
from sqlalchemy.orm import selectinload

from app import formatting
from app.engine.enums import SetType, Sex, TrainingExperience, WorkoutStatus
from app.engine.readiness import Readiness, Sleep, assess
from app.engine.routines.loads import loads_weight, next_set_load, round_load, starting_load
from app.engine.routines.prescription import weekly_rir
from app.engine.routines.types import ExerciseInfo
from app.extensions import db
from app.models import (
    Exercise,
    IntakeLog,
    Profile,
    Routine,
    RoutineDay,
    RoutineExercise,
    SetLog,
    User,
    WorkoutSession,
)
from app.models.base import utcnow
from app.services import dashboard, plans

EXTRA_SETS_ALLOWED = 2
EPLEY_DIVISOR = 30
MAX_HISTORY = 50
STREAK_LOOKBACK_WEEKS = 104


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
            return f"{formatting.kg(self.top_weight, 2)} {formatting.TIMES} {reps}"
        return " · ".join(
            f"{formatting.kg(kg, 2)} {formatting.TIMES} {reps}" for reps, kg in self.sets
        )


@dataclass
class SetRow:
    """One prescribed (or extra) set, what was logged for it and what to pre-fill."""

    index: int
    log: SetLog | None
    prefill_kg: float | None = None
    prefill_reps: int = 0
    adjusted: bool = False  # the load moved because of the set before


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
    first_time: bool = False  # suggested_kg is an estimate, not last session's load
    target_rir: int = 0
    takes_load: bool = True
    per_hand: bool = False

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


def last_performance(user: User, exercise: Exercise, before: WorkoutSession) -> Performance | None:
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
    return Performance(day=previous.started_at.date(), sets=sets)


def suggest_load(item: RoutineExercise, previous: Performance | None) -> float | None:
    """Double progression: same load until every set reaches the top of the range.

    ``None`` without a previous session; :func:`first_load` covers that case.
    """
    if previous is None:
        return None
    top = previous.top_weight
    if all(reps >= item.rep_max for reps, _kg in previous.sets):
        return round(top + (item.load_increment_kg or 0), 2)
    return top


def _info(exercise: Exercise) -> ExerciseInfo:
    return plans.exercise_info(exercise, {})


def first_load(exercise: Exercise, profile: Profile) -> float | None:
    """Estimated working load for an exercise never done before (``None`` if it takes no load)."""
    return starting_load(
        _info(exercise),
        Sex(profile.sex),
        profile.weight_kg,
        TrainingExperience(profile.training_experience),
    )


def target_rir(session: WorkoutSession, item: RoutineExercise) -> int:
    """RIR this week asks for, never below the exercise's floor for the block."""
    day = session.routine_day
    weeks = day.routine.mesocycle_weeks if day is not None else 4
    schedule = weekly_rir(weeks)
    week = min(max(session.mesocycle_week or 1, 1), len(schedule))
    return max(item.rir_end, min(item.rir_start, schedule[week - 1]))


def _prefill(
    info: ExerciseInfo,
    rows: list[SetRow],
    item: RoutineExercise,
    start_kg: float | None,
    rir: int,
) -> None:
    """Fill the open rows: the first from the suggestion, the rest from the set before."""
    target_reps = (item.rep_min + item.rep_max) // 2
    kg, reps, adjusted = start_kg, item.rep_min, False
    for row in rows:
        if row.log is not None:
            done = row.log
            kg = (
                next_set_load(info, done.weight_kg, done.reps, done.rir, target_reps, rir)
                if done.weight_kg > 0
                else done.weight_kg
            )
            adjusted = kg != done.weight_kg
            reps = done.reps
            continue
        row.prefill_kg, row.prefill_reps, row.adjusted = kg, reps, adjusted


SLEEP_ANSWERS = frozenset({"good", "ok", "bad", "skip", "normal"})


def readiness_for(user: User, session: WorkoutSession) -> Readiness | None:
    """How the person arrives today; ``None`` until the one-tap question is answered.

    ``normal`` means the person chose to train as usual: no easy day whatever
    the signals say.
    """
    answer = session.sleep_quality
    if answer is None:
        return None
    if answer == "normal":
        return assess(None, None, None, 0)
    from app.services import adjustments, plans

    plan = plans.active_plan(user)
    today = user.today()
    ratio = None
    if plan is not None and plan.calorie_target:
        yesterday = db.session.scalar(
            select(IntakeLog).where(
                IntakeLog.user_id == user.id, IntakeLog.logged_on == today - timedelta(days=1)
            )
        )
        if yesterday is not None and yesterday.calories > 0:
            ratio = yesterday.calories / plan.calorie_target
    last = db.session.scalars(
        select(WorkoutSession)
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.status == WorkoutStatus.COMPLETED,
            WorkoutSession.started_at < session.started_at,
            WorkoutSession.deleted_at.is_(None),
        )
        .order_by(WorkoutSession.started_at.desc())
    ).first()
    return assess(
        Sleep(answer) if answer in {"good", "ok", "bad"} else None,
        ratio,
        last.perceived_fatigue if last else None,
        adjustments.weeks_in_deficit(user, plan, today) if plan else 0,
    )


def session_blocks(
    user: User,
    session: WorkoutSession,
    profile: Profile,
    equipment: frozenset[str],
    readiness: Readiness | None = None,
) -> list[ExerciseBlock]:
    """What the live page shows: one block per prescribed exercise.

    On an easy day the first set's suggestion goes down and the reserve goes up
    (``engine.readiness``); the sets after it adjust from how each one went.
    """
    easy = readiness is not None and readiness.is_easy
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
        previous = last_performance(user, exercise, session)
        info = _info(exercise)
        suggested = suggest_load(item, previous)
        first_time = previous is None
        if first_time:
            suggested = first_load(exercise, profile)
        rir = target_rir(session, item)
        if easy and readiness is not None:
            rir += readiness.extra_rir
            if suggested and loads_weight(info):
                suggested = round_load(info, suggested * readiness.load_factor)
        _prefill(info, rows, item, suggested, rir)
        blocks.append(
            ExerciseBlock(
                item=item,
                exercise=exercise,
                is_substituted=exercise.id != item.exercise_id,
                rows=rows,
                previous=previous,
                suggested_kg=suggested,
                alternatives=dashboard.usable_alternatives(item, profile, equipment),
                first_time=first_time and suggested is not None,
                target_rir=rir,
                takes_load=loads_weight(info),
                per_hand=bool({"dumbbells", "kettlebell"} & info.equipment)
                and not {"barbell", "ez_bar", "trap_bar", "smith_machine"} & info.equipment,
            )
        )
    return blocks


def _epley_sql() -> Any:
    """El 1RM de Epley en SQL, con la misma excepción para la serie de una repetición."""
    return case(
        (SetLog.reps <= 1, SetLog.weight_kg),
        else_=SetLog.weight_kg * (1 + SetLog.reps / float(EPLEY_DIVISOR)),
    )


def previous_bests(user: User) -> dict[tuple[int, int], float]:
    """Mejor 1RM anterior a cada sesión, por ejercicio, en una sola consulta.

    El historial pinta 50 sesiones con varios ejercicios cada una: preguntar
    "¿cuál era mi marca antes de esta?" una vez por casilla eran cientos de
    consultas que además cargaban todas las series de la cuenta.
    """
    rows = db.session.execute(
        select(
            WorkoutSession.id,
            SetLog.exercise_id,
            func.max(_epley_sql()),
        )
        .join(SetLog, SetLog.workout_session_id == WorkoutSession.id)
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.status == WorkoutStatus.COMPLETED,
            WorkoutSession.deleted_at.is_(None),
            SetLog.set_type == SetType.WORKING,
            SetLog.reps >= 1,
        )
        .group_by(WorkoutSession.id, SetLog.exercise_id)
        .order_by(WorkoutSession.started_at, WorkoutSession.id)
    ).all()
    best_so_far: dict[int, float] = {}
    before: dict[tuple[int, int], float] = {}
    for session_id, exercise_id, best in rows:
        earlier = best_so_far.get(exercise_id)
        if earlier is not None:
            before[(session_id, exercise_id)] = round(earlier, 1)
        best_so_far[exercise_id] = max(earlier or 0.0, float(best))
    return before


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


@dataclass(frozen=True)
class NewRecord:
    """A set that just beat the person's best estimated max for that exercise."""

    exercise: Exercise
    weight_kg: float
    reps: int
    est_1rm: float
    previous_1rm: float


def new_record(user: User, session: WorkoutSession, row: SetLog) -> NewRecord | None:
    """The record ``row`` sets, or ``None``.

    Only against finished sessions: the first time an exercise is done there is
    nothing to beat, so it is not celebrated. Within the session only the set
    that goes past the others counts, so repeating it is not a second record.
    """
    if row.set_type != SetType.WORKING or row.reps < 1:
        return None
    previous = _best_1rm_before(user, row.exercise_id, session)
    if previous is None:
        return None
    best = estimated_1rm(row.weight_kg, row.reps)
    others = [
        estimated_1rm(other.weight_kg, other.reps)
        for other in session.sets
        if other.id != row.id
        and other.exercise_id == row.exercise_id
        and other.set_type == SetType.WORKING
        and other.reps >= 1
    ]
    if best <= previous + 0.01 or (others and best <= max(others) + 0.01):
        return None
    return NewRecord(
        exercise=row.exercise,
        weight_kg=row.weight_kg,
        reps=row.reps,
        est_1rm=best,
        previous_1rm=previous,
    )


@dataclass(frozen=True)
class Streak:
    """Weeks in a row meeting the training days, with one day of slack."""

    weeks: int
    this_week: int
    target: int

    @property
    def met_this_week(self) -> bool:
        """This week already counts."""
        return self.this_week >= self.target


def weekly_streak(user: User, today: date, planned_days: int) -> Streak:
    """Consecutive weeks (Monday to Sunday) with enough finished sessions.

    A week counts with the planned days minus one: missing one session does not
    break anything. The week in progress never breaks the streak; it only adds
    to it once it is met.
    """
    target = max(1, planned_days - 1)
    try:
        zone = ZoneInfo(user.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
    this_monday = today - timedelta(days=today.weekday())
    since = this_monday - timedelta(weeks=STREAK_LOOKBACK_WEEKS)
    started = db.session.scalars(
        select(WorkoutSession.started_at).where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.status == WorkoutStatus.COMPLETED,
            WorkoutSession.deleted_at.is_(None),
            WorkoutSession.started_at >= datetime.combine(since, time.min, tzinfo=UTC),
        )
    ).all()
    per_week: dict[date, int] = {}
    for moment in started:
        aware = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
        day = aware.astimezone(zone).date()
        monday = day - timedelta(days=day.weekday())
        per_week[monday] = per_week.get(monday, 0) + 1
    this_week = per_week.get(this_monday, 0)
    week = this_monday if this_week >= target else this_monday - timedelta(weeks=1)
    weeks = 0
    while per_week.get(week, 0) >= target:
        weeks += 1
        week -= timedelta(weeks=1)
    return Streak(weeks=weeks, this_week=this_week, target=target)


def summarise(
    user: User,
    session: WorkoutSession,
    now: datetime | None = None,
    *,
    earlier_bests: Mapping[tuple[int, int], float] | None = None,
) -> SessionSummary:
    """Totals and per-exercise best sets of a session.

    ``earlier_bests`` viene de ``previous_bests`` cuando se resumen muchas
    sesiones de golpe; sin él se pregunta por cada ejercicio, que es lo
    razonable para una sola sesión.
    """
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
                previous_1rm=(
                    earlier_bests.get((session.id, exercise_id))
                    if earlier_bests is not None
                    else _best_1rm_before(user, exercise_id, session)
                ),
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
    earlier = previous_bests(user)
    return [summarise(user, session, earlier_bests=earlier) for session in sessions]


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
    rows = db.session.execute(
        select(WorkoutSession.started_at, SetLog.weight_kg, SetLog.reps)
        .join(SetLog, SetLog.workout_session_id == WorkoutSession.id)
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.status == WorkoutStatus.COMPLETED,
            WorkoutSession.deleted_at.is_(None),
            SetLog.exercise_id == exercise.id,
            SetLog.set_type == SetType.WORKING,
            SetLog.reps >= 1,
        )
        .order_by(WorkoutSession.started_at, WorkoutSession.id)
    ).all()
    # Una sola consulta: la mejor serie de cada sesión se elige aquí.
    best_by_session: dict[datetime, tuple[float, int]] = {}
    for started_at, weight_kg, reps in rows:
        current = best_by_session.get(started_at)
        score = (estimated_1rm(weight_kg, reps), weight_kg)
        if current is None or score > (estimated_1rm(*current), current[0]):
            best_by_session[started_at] = (weight_kg, reps)
    points: list[ProgressPoint] = []
    for started_at in sorted(best_by_session):
        weight_kg, reps = best_by_session[started_at]
        points.append(
            ProgressPoint(
                day=started_at.date(),
                top_weight=weight_kg,
                top_reps=reps,
                est_1rm=estimated_1rm(weight_kg, reps),
            )
        )
    return points
