"""Daily diary (weight, intake, activity) and weekly body measurements.

Every entry is one row per user and day; saving the same day again updates
it. Nothing here commits: the routes own the transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select

from app.engine.enums import BodyFatMethod, CardioKind
from app.extensions import db
from app.models import ActivityLog, BodyMeasurement, IntakeLog, User, WeightLog

DIARY_DAYS = 14
MEASUREMENTS_LIMIT = 12


@dataclass(frozen=True)
class DiaryRow:
    """Everything logged for one day (``None`` where nothing was)."""

    day: date
    weight_kg: float | None = None
    calories: int | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    adherence_pct: int | None = None
    steps: int | None = None
    cardio_kind: CardioKind | None = None
    cardio_minutes: int | None = None

    @property
    def is_empty(self) -> bool:
        """Whether nothing at all was logged that day."""
        return self.weight_kg is None and self.calories is None and self.steps is None


def upsert_weight(user: User, day: date, weight_kg: float, notes: str | None = None) -> WeightLog:
    """Create or update the weigh-in of ``day``."""
    row = db.session.scalar(
        select(WeightLog).where(WeightLog.user_id == user.id, WeightLog.logged_on == day)
    )
    if row is None:
        row = WeightLog(user=user, logged_on=day, weight_kg=weight_kg, notes=notes)
        db.session.add(row)
    else:
        row.weight_kg = weight_kg
        row.notes = notes
    return row


def upsert_intake(
    user: User,
    day: date,
    calories: int,
    protein_g: float | None = None,
    carbs_g: float | None = None,
    fat_g: float | None = None,
    adherence_pct: int | None = None,
    notes: str | None = None,
) -> IntakeLog:
    """Create or update what was eaten on ``day``."""
    row = db.session.scalar(
        select(IntakeLog).where(IntakeLog.user_id == user.id, IntakeLog.logged_on == day)
    )
    if row is None:
        row = IntakeLog(user=user, logged_on=day, calories=calories)
        db.session.add(row)
    row.calories = calories
    row.protein_g = protein_g
    row.carbs_g = carbs_g
    row.fat_g = fat_g
    row.adherence_pct = adherence_pct
    row.notes = notes
    return row


def upsert_activity(
    user: User,
    day: date,
    steps: int | None,
    cardio_kind: CardioKind | None = None,
    cardio_minutes: int | None = None,
    notes: str | None = None,
) -> ActivityLog:
    """Create or update the steps and cardio of ``day``."""
    row = db.session.scalar(
        select(ActivityLog).where(ActivityLog.user_id == user.id, ActivityLog.logged_on == day)
    )
    if row is None:
        row = ActivityLog(user=user, logged_on=day)
        db.session.add(row)
    row.steps = steps
    row.cardio_kind = cardio_kind if cardio_minutes else None
    row.cardio_minutes = cardio_minutes if cardio_kind else None
    row.notes = notes
    return row


def upsert_measurement(
    user: User,
    day: date,
    *,
    neck_cm: float | None = None,
    chest_cm: float | None = None,
    waist_cm: float | None = None,
    hip_cm: float | None = None,
    arm_cm: float | None = None,
    thigh_cm: float | None = None,
    calf_cm: float | None = None,
    body_fat_pct: float | None = None,
    body_fat_method: BodyFatMethod = BodyFatMethod.NONE,
    notes: str | None = None,
) -> BodyMeasurement:
    """Create or update the tape measures of ``day``."""
    row = db.session.scalar(
        select(BodyMeasurement).where(
            BodyMeasurement.user_id == user.id, BodyMeasurement.measured_on == day
        )
    )
    if row is None:
        row = BodyMeasurement(user=user, measured_on=day)
        db.session.add(row)
    row.neck_cm = neck_cm
    row.chest_cm = chest_cm
    row.waist_cm = waist_cm
    row.hip_cm = hip_cm
    row.arm_cm = arm_cm
    row.thigh_cm = thigh_cm
    row.calf_cm = calf_cm
    row.body_fat_pct = body_fat_pct
    row.body_fat_method = body_fat_method if body_fat_pct is not None else BodyFatMethod.NONE
    row.notes = notes
    return row


def diary_rows(user: User, today: date, days: int = DIARY_DAYS) -> list[DiaryRow]:
    """The last ``days`` calendar days, newest first, with whatever was logged."""
    since = today - timedelta(days=days - 1)
    weights = {
        row.logged_on: row
        for row in db.session.scalars(
            select(WeightLog).where(WeightLog.user_id == user.id, WeightLog.logged_on >= since)
        )
    }
    intakes = {
        row.logged_on: row
        for row in db.session.scalars(
            select(IntakeLog).where(IntakeLog.user_id == user.id, IntakeLog.logged_on >= since)
        )
    }
    activity = {
        row.logged_on: row
        for row in db.session.scalars(
            select(ActivityLog).where(
                ActivityLog.user_id == user.id, ActivityLog.logged_on >= since
            )
        )
    }
    rows: list[DiaryRow] = []
    for offset in range(days):
        day = today - timedelta(days=offset)
        weight = weights.get(day)
        intake = intakes.get(day)
        moved = activity.get(day)
        rows.append(
            DiaryRow(
                day=day,
                weight_kg=weight.weight_kg if weight else None,
                calories=intake.calories if intake else None,
                protein_g=intake.protein_g if intake else None,
                carbs_g=intake.carbs_g if intake else None,
                fat_g=intake.fat_g if intake else None,
                adherence_pct=intake.adherence_pct if intake else None,
                steps=moved.steps if moved else None,
                cardio_kind=moved.cardio_kind if moved else None,
                cardio_minutes=moved.cardio_minutes if moved else None,
            )
        )
    return rows


def recent_measurements(user: User, limit: int = MEASUREMENTS_LIMIT) -> list[BodyMeasurement]:
    """Latest tape measures, newest first."""
    return list(
        db.session.scalars(
            select(BodyMeasurement)
            .where(BodyMeasurement.user_id == user.id)
            .order_by(BodyMeasurement.measured_on.desc())
            .limit(limit)
        )
    )


def entry_for(user: User, day: date) -> DiaryRow:
    """What is already logged for ``day`` (to pre-fill the forms)."""
    rows = diary_rows(user, day, days=1)
    return rows[0]


# --- «Tu semana» y «Primeros pasos» (en vez de 14 filas vacías) ---------------

HISTORY_MIN_DAYS = 7
HISTORY_LIMIT = 30


@dataclass(frozen=True)
class WeekDay:
    """One day of the week strip: what was logged, and whether it can be opened."""

    day: date
    weight: bool
    food: bool
    activity: bool
    workout: bool
    before_signup: bool
    future: bool


@dataclass(frozen=True)
class Week:
    """Monday to Sunday around a day, with the neighbouring weeks when they make sense."""

    days: list[WeekDay]
    previous: date | None
    following: date | None


@dataclass(frozen=True)
class FirstStep:
    """One thing to do in the first days, ticked off on its own."""

    key: str
    done: bool


def signup_day(user: User) -> date:
    """The calendar day the account was created, in the person's time zone."""
    from app.formatting import local_date

    return local_date(user.created_at, user)


def _logged_days(model: type, user: User, since: date, until: date) -> set[date]:
    column = model.logged_on
    return set(
        db.session.scalars(
            select(column).where(model.user_id == user.id, column >= since, column <= until)
        )
    )


def _workout_days(user: User, since: date, until: date) -> set[date]:
    from datetime import UTC, datetime, time

    from app.engine.enums import WorkoutStatus
    from app.formatting import local_date
    from app.models import WorkoutSession

    # Un día de margen a cada lado por la zona horaria; el filtro fino va después.
    lower = datetime.combine(since - timedelta(days=1), time.min, tzinfo=UTC)
    upper = datetime.combine(until + timedelta(days=2), time.min, tzinfo=UTC)
    moments = db.session.scalars(
        select(WorkoutSession.started_at).where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.status == WorkoutStatus.COMPLETED,
            WorkoutSession.started_at >= lower,
            WorkoutSession.started_at < upper,
        )
    )
    days = {local_date(moment, user) for moment in moments}
    return {d for d in days if since <= d <= until}


def week_of(user: User, day: date, today: date) -> Week:
    """The Monday-to-Sunday strip that contains ``day``."""
    from app.models import FoodEntry

    monday = day - timedelta(days=day.weekday())
    sunday = monday + timedelta(days=6)
    start = signup_day(user)
    weights = _logged_days(WeightLog, user, monday, sunday)
    intakes = _logged_days(IntakeLog, user, monday, sunday) | _logged_days(
        FoodEntry, user, monday, sunday
    )
    moved = _logged_days(ActivityLog, user, monday, sunday)
    trained = _workout_days(user, monday, sunday)
    days = [
        WeekDay(
            day=current,
            weight=current in weights,
            food=current in intakes,
            activity=current in moved,
            workout=current in trained,
            before_signup=current < start,
            future=current > today,
        )
        for current in (monday + timedelta(days=offset) for offset in range(7))
    ]
    previous = monday - timedelta(days=7)
    following = monday + timedelta(days=7)
    return Week(
        days=days,
        previous=previous if previous + timedelta(days=6) >= start else None,
        following=following if following <= today else None,
    )


def first_steps(user: User, today: date) -> list[FirstStep] | None:
    """The checklist for the first days; ``None`` once done or after two weeks."""
    from app.engine.enums import WorkoutStatus
    from app.models import FoodEntry, WorkoutSession

    if (today - signup_day(user)).days > 14:
        return None

    def exists(model: type, *conditions: object) -> bool:
        return (
            db.session.scalar(
                select(model.id).where(model.user_id == user.id, *conditions).limit(1)
            )
            is not None
        )

    steps = [
        FirstStep("weight", exists(WeightLog)),
        FirstStep("food", exists(IntakeLog) or exists(FoodEntry)),
        FirstStep(
            "workout", exists(WorkoutSession, WorkoutSession.status == WorkoutStatus.COMPLETED)
        ),
    ]
    return None if all(step.done for step in steps) else steps


def history_rows(user: User, today: date) -> list[DiaryRow]:
    """Recent days with something logged (never empty rows); empty until there are 7."""
    start = signup_day(user)
    if (today - start).days + 1 < HISTORY_MIN_DAYS:
        return []  # ni siquiera hay siete días de cuenta: nada que consultar
    since = max(start, today - timedelta(days=89))
    rows = [
        row for row in diary_rows(user, today, days=(today - since).days + 1) if not row.is_empty
    ]
    return rows[:HISTORY_LIMIT] if len(rows) >= HISTORY_MIN_DAYS else []
