"""Sessions, sets, substitutions, closing, summaries and progress."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.engine.enums import SetType, WorkoutStatus
from app.engine.equipment_presets import preset_for
from app.models import Equipment, Profile, Routine, SetLog, User, WorkoutSession
from app.models.base import utcnow
from app.services import dashboard, plans, workouts
from app.services.workouts import WorkoutError
from tests.factories import make_profile, make_user

TODAY = date(2026, 9, 9)


def _hours_ago(hours: int):
    """A moment in the past, so ``finished_at`` (now) never precedes ``started_at``."""
    return utcnow() - timedelta(hours=hours)


def _setup(seeded: SQLAlchemy) -> tuple[User, Profile, Routine]:
    user = make_user(seeded.session)
    user.equipment = seeded.session.scalars(
        select(Equipment).where(Equipment.code.in_(preset_for("full_gym")))
    ).all()
    profile = make_profile(seeded.session, user)
    result = plans.generate_for_profile(user, profile, TODAY)
    seeded.session.commit()
    assert result.routine is not None
    return user, profile, result.routine


def _equipment(user: User) -> frozenset[str]:
    return frozenset(item.code for item in user.equipment)


def test_estimated_1rm_uses_epley_and_returns_the_load_for_a_single() -> None:
    assert workouts.estimated_1rm(100, 1) == 100
    assert workouts.estimated_1rm(100, 0) == 100
    assert workouts.estimated_1rm(100, 10) == pytest.approx(133.3)
    assert workouts.estimated_1rm(60, 5) == pytest.approx(70.0)


def test_mesocycle_week_cycles(seeded: SQLAlchemy) -> None:
    _user, _profile, routine = _setup(seeded)
    assert routine.mesocycle_weeks >= 3
    assert workouts.mesocycle_week(routine, TODAY) == 1
    assert workouts.mesocycle_week(routine, TODAY + timedelta(days=8)) == 2
    weeks = routine.mesocycle_weeks
    assert workouts.mesocycle_week(routine, TODAY + timedelta(weeks=weeks)) == 1
    routine.starts_on = None
    assert workouts.mesocycle_week(routine, TODAY) == 1


def test_start_session_is_idempotent_while_one_is_open(seeded: SQLAlchemy) -> None:
    user, _profile, routine = _setup(seeded)
    first = workouts.start_session(user, routine, routine.days[0], TODAY)
    seeded.session.commit()
    again = workouts.start_session(user, routine, routine.days[1], TODAY)
    assert again is first  # the open session wins; the route warns about it
    assert workouts.active_session(user) is first
    assert first.mesocycle_week == 1
    assert len(seeded.session.scalars(select(WorkoutSession)).all()) == 1


def test_log_set_creates_overwrites_and_validates(seeded: SQLAlchemy) -> None:
    user, _profile, routine = _setup(seeded)
    session = workouts.start_session(user, routine, routine.days[0], TODAY)
    item = routine.days[0].exercises[0]

    row = workouts.log_set(session, item, 1, 8, 60.0, 2)
    seeded.session.commit()
    assert row.exercise_id == item.exercise_id
    assert row.routine_exercise_id == item.id
    assert row.set_type is SetType.WORKING

    workouts.log_set(session, item, 1, 9, 62.5, 1)
    seeded.session.commit()
    stored = seeded.session.scalars(select(SetLog)).all()
    assert len(stored) == 1
    assert (stored[0].reps, stored[0].weight_kg, stored[0].rir) == (9, 62.5, 1)

    with pytest.raises(WorkoutError) as caught:
        workouts.log_set(session, item, 0, 8, 60.0, None)
    assert caught.value.reason == "bad_index"
    with pytest.raises(WorkoutError):
        workouts.log_set(session, item, item.sets + 3, 8, 60.0, None)

    # Two extra sets beyond the prescription are allowed.
    workouts.log_set(session, item, item.sets + 1, 6, 60.0, 0)
    seeded.session.commit()
    assert len(seeded.session.scalars(select(SetLog)).all()) == 2


def test_delete_set_and_closed_sessions_reject_changes(seeded: SQLAlchemy) -> None:
    user, _profile, routine = _setup(seeded)
    session = workouts.start_session(user, routine, routine.days[0], TODAY)
    item = routine.days[0].exercises[0]
    row = workouts.log_set(session, item, 1, 8, 60.0, 2)
    seeded.session.commit()

    with pytest.raises(WorkoutError) as caught:
        workouts.delete_set(session, row.id + 999)
    assert caught.value.reason == "not_found"

    workouts.delete_set(session, row.id)
    seeded.session.commit()
    assert seeded.session.scalars(select(SetLog)).all() == []

    workouts.abandon(session)
    seeded.session.commit()
    for action in (
        lambda: workouts.log_set(session, item, 1, 8, 60.0, None),
        lambda: workouts.delete_set(session, 1),
        lambda: workouts.finish(session, 3, None),
        lambda: workouts.abandon(session),
    ):
        with pytest.raises(WorkoutError) as caught:
            action()
        assert caught.value.reason == "closed"


def test_substitution_only_accepts_usable_alternatives(seeded: SQLAlchemy) -> None:
    user, profile, routine = _setup(seeded)
    session = workouts.start_session(user, routine, routine.days[0], TODAY)
    item = next(
        candidate for candidate in routine.days[0].exercises if candidate.exercise.alternatives
    )
    options = dashboard.usable_alternatives(item, profile, _equipment(user))
    assert options

    workouts.substitute(session, item, options[0], profile, _equipment(user))
    seeded.session.commit()
    assert session.substitutions == {str(item.id): options[0].id}
    assert workouts.effective_exercise(session, item) is options[0]

    # The set is logged against the substitute, not the prescribed exercise.
    workouts.log_set(session, item, 1, 10, 30.0, 2)
    seeded.session.commit()
    assert seeded.session.scalar(select(SetLog)).exercise_id == options[0].id

    with pytest.raises(WorkoutError) as caught:
        workouts.substitute(session, item, None, profile, _equipment(user))
    assert caught.value.reason == "sets_logged"


def test_substitution_rejects_an_exercise_outside_the_alternatives(seeded: SQLAlchemy) -> None:
    user, profile, routine = _setup(seeded)
    session = workouts.start_session(user, routine, routine.days[0], TODAY)
    item = routine.days[0].exercises[0]
    stranger = next(
        candidate.exercise
        for day in routine.days
        for candidate in day.exercises
        if candidate.exercise_id != item.exercise_id
    )
    with pytest.raises(WorkoutError) as caught:
        workouts.substitute(session, item, stranger, profile, _equipment(user))
    assert caught.value.reason == "not_an_alternative"

    options = dashboard.usable_alternatives(item, profile, _equipment(user))
    workouts.substitute(session, item, options[0], profile, _equipment(user))
    workouts.substitute(session, item, None, profile, _equipment(user))
    assert session.substitutions == {}
    assert workouts.effective_exercise(session, item) is item.exercise


def test_blocks_carry_the_previous_performance_and_the_suggested_load(
    seeded: SQLAlchemy,
) -> None:
    user, profile, routine = _setup(seeded)
    item = routine.days[0].exercises[0]

    first = workouts.start_session(user, routine, routine.days[0], TODAY)
    first.started_at = _hours_ago(24 * 7)
    for index in range(1, item.sets + 1):
        workouts.log_set(first, item, index, item.rep_max, 60.0, 1)
    workouts.finish(first, 3, None)
    seeded.session.commit()
    assert first.status is WorkoutStatus.COMPLETED

    second = workouts.start_session(user, routine, routine.days[0], TODAY)
    seeded.session.commit()
    blocks = workouts.session_blocks(user, second, profile, _equipment(user))
    assert len(blocks) == len(routine.days[0].exercises)
    block = blocks[0]
    assert block.previous is not None
    assert block.previous.day == (utcnow() - timedelta(days=7)).date()
    assert f"{item.rep_max}" in block.previous.summary()
    # Every set hit the top of the range, so the load goes up by the increment.
    assert block.suggested_kg == pytest.approx(60.0 + (item.load_increment_kg or 0))
    assert block.done == 0
    assert len(block.rows) == item.sets
    assert block.is_substituted is False


def test_suggested_load_holds_when_the_range_was_not_completed(seeded: SQLAlchemy) -> None:
    user, profile, routine = _setup(seeded)
    item = routine.days[0].exercises[0]
    first = workouts.start_session(user, routine, routine.days[0], TODAY)
    first.started_at = _hours_ago(24 * 7)
    workouts.log_set(first, item, 1, item.rep_max, 60.0, 1)
    workouts.log_set(first, item, 2, item.rep_min, 60.0, 0)
    workouts.finish(first, 4, "duro")
    seeded.session.commit()

    second = workouts.start_session(user, routine, routine.days[0], TODAY)
    seeded.session.commit()
    block = workouts.session_blocks(user, second, profile, _equipment(user))[0]
    assert block.suggested_kg == 60.0
    assert workouts.suggest_load(item, None) is None


def test_finish_without_sets_counts_as_abandoned(seeded: SQLAlchemy) -> None:
    user, _profile, routine = _setup(seeded)
    session = workouts.start_session(user, routine, routine.days[0], TODAY)
    workouts.finish(session, None, None)
    seeded.session.commit()
    assert session.status is WorkoutStatus.ABANDONED
    assert session.finished_at is not None


def test_summary_totals_and_personal_records(seeded: SQLAlchemy) -> None:
    user, _profile, routine = _setup(seeded)
    item = routine.days[0].exercises[0]

    first = workouts.start_session(user, routine, routine.days[0], TODAY)
    first.started_at = _hours_ago(24 * 8)
    workouts.log_set(first, item, 1, 8, 60.0, 2)
    workouts.log_set(first, item, 2, 8, 60.0, 1)
    workouts.finish(first, 3, None)
    first.finished_at = first.started_at + timedelta(minutes=52)
    seeded.session.commit()

    summary = workouts.summarise(user, first)
    assert summary.working_sets == 2
    assert summary.total_reps == 16
    assert summary.tonnage_kg == pytest.approx(960.0)
    assert summary.duration_minutes == 52
    assert len(summary.exercises) == 1
    best = summary.exercises[0]
    assert best.top_weight == 60.0
    assert best.est_1rm == pytest.approx(76.0)
    assert best.previous_1rm is None
    assert best.is_pr is True
    assert summary.prs == 1

    second = workouts.start_session(user, routine, routine.days[0], TODAY)
    second.started_at = _hours_ago(24)
    workouts.log_set(second, item, 1, 8, 55.0, 2)  # lighter: no record
    workouts.finish(second, 2, None)
    seeded.session.commit()
    assert workouts.summarise(user, second).prs == 0

    third = workouts.start_session(user, routine, routine.days[0], TODAY)
    third.started_at = _hours_ago(2)
    workouts.log_set(third, item, 1, 9, 62.5, 1)
    workouts.finish(third, 3, None)
    seeded.session.commit()
    assert workouts.summarise(user, third).prs == 1


def test_warmup_sets_do_not_count(seeded: SQLAlchemy) -> None:
    user, _profile, routine = _setup(seeded)
    item = routine.days[0].exercises[0]
    session = workouts.start_session(user, routine, routine.days[0], TODAY)
    workouts.log_set(session, item, 1, 12, 20.0, None, SetType.WARMUP)
    workouts.log_set(session, item, 2, 8, 60.0, 2)
    workouts.finish(session, 3, None)
    seeded.session.commit()
    summary = workouts.summarise(user, session)
    assert summary.working_sets == 1
    assert summary.total_reps == 8


def test_history_and_progress(seeded: SQLAlchemy) -> None:
    user, _profile, routine = _setup(seeded)
    item = routine.days[0].exercises[0]
    for offset, kg in ((14, 55.0), (7, 60.0), (0, 62.5)):
        session = workouts.start_session(user, routine, routine.days[0], TODAY)
        session.started_at = _hours_ago(24 * offset + 2)
        workouts.log_set(session, item, 1, 8, kg, 2)
        workouts.finish(session, 3, None)
        seeded.session.commit()

    items = workouts.history(user)
    assert len(items) == 3
    assert items[0].session.started_at > items[-1].session.started_at

    trained = workouts.trained_exercises(user)
    assert [row.id for row in trained] == [item.exercise_id]

    points = workouts.exercise_progress(user, item.exercise)
    assert [point.top_weight for point in points] == [55.0, 60.0, 62.5]
    assert points[0].day < points[-1].day
    assert points[-1].est_1rm > points[0].est_1rm


def test_sessions_of_other_users_are_never_returned(seeded: SQLAlchemy) -> None:
    user, _profile, routine = _setup(seeded)
    session = workouts.start_session(user, routine, routine.days[0], TODAY)
    seeded.session.commit()
    stranger = make_user(seeded.session, email="otro@example.com")
    seeded.session.commit()
    assert workouts.get_session(user, session.id) is session
    assert workouts.get_session(stranger, session.id) is None
    assert workouts.active_session(stranger) is None
