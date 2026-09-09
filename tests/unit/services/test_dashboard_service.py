"""Weight series, next session, review date, history, today's targets and alternatives."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.engine.adjustment.types import AdjustmentInputs
from app.engine.enums import Goal, InjuryArea, Severity, WorkoutStatus
from app.engine.equipment_presets import preset_for
from app.models import Equipment, Injury, PlanAdjustment, WeightLog, WorkoutSession
from app.services import dashboard, plans
from tests.factories import make_exercise, make_profile, make_user

TODAY = date(2026, 9, 9)


def test_review_interval_matches_the_engine_default() -> None:
    field = AdjustmentInputs.__dataclass_fields__["review_interval_days"]
    assert field.default == dashboard.REVIEW_INTERVAL_DAYS


def test_weight_series_smooths_and_limits_the_window(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    daily = {7: 80.6, 6: 80.5, 5: 80.4, 4: 80.0, 3: 80.4, 2: 79.8, 1: 80.2, 0: 80.0}
    for offset, kg in ((100, 90.0), *daily.items()):
        database.session.add(
            WeightLog(user=user, logged_on=TODAY - timedelta(days=offset), weight_kg=kg)
        )
    database.session.commit()
    series = dashboard.weight_series(user, TODAY)
    assert len(series.points) == len(daily)  # the weigh-in from 100 days ago is out of the window
    assert series.latest == (TODAY, 80.0)
    # The average starts once a whole 7-day window fits behind the day.
    assert series.smoothed[0][0] == TODAY - timedelta(days=1)
    assert series.change_kg is not None
    chart = series.to_chart()
    assert chart["labels"][-1] == TODAY.strftime("%d/%m")
    assert chart["average"][0] is None
    assert chart["average"][-1] == series.smoothed[-1][1]


def test_weight_series_without_data(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    series = dashboard.weight_series(user, TODAY)
    assert series.points == []
    assert series.latest is None
    assert series.change_kg is None
    assert series.to_chart() == {"labels": [], "weight": [], "average": []}


def _generate(seeded: SQLAlchemy, **profile_overrides: object):
    user = make_user(seeded.session)
    user.equipment = seeded.session.scalars(
        select(Equipment).where(Equipment.code.in_(preset_for("full_gym")))
    ).all()
    profile = make_profile(seeded.session, user, **profile_overrides)
    result = plans.generate_for_profile(user, profile, TODAY)
    seeded.session.commit()
    return user, profile, result


def test_next_routine_day_follows_completed_sessions(seeded: SQLAlchemy) -> None:
    user, _profile, result = _generate(seeded)
    routine = result.routine
    assert routine is not None
    assert dashboard.next_routine_day(user, None) is None
    assert dashboard.next_routine_day(user, routine) is routine.days[0]

    def session(day_id: int | None, status: WorkoutStatus, hours_ago: int) -> None:
        seeded.session.add(
            WorkoutSession(
                user=user,
                routine_day_id=day_id,
                started_at=datetime.now(UTC) - timedelta(hours=hours_ago),
                status=status,
            )
        )
        seeded.session.commit()

    session(routine.days[1].id, WorkoutStatus.COMPLETED, 48)
    session(routine.days[3].id, WorkoutStatus.ABANDONED, 24)  # ignored
    assert dashboard.next_routine_day(user, routine) is routine.days[2]
    session(routine.days[-1].id, WorkoutStatus.COMPLETED, 1)
    assert dashboard.next_routine_day(user, routine) is routine.days[0]  # wraps around


def test_next_review_uses_the_last_adjustment(seeded: SQLAlchemy) -> None:
    user, _profile, result = _generate(seeded)
    plan = result.plan
    assert plan is not None
    assert dashboard.next_review_on(plan) == TODAY + timedelta(days=14)
    later = PlanAdjustment(
        user=user,
        plan=plan,
        reason="scheduled_review",
        explanation="Revisión",
        created_at=datetime(2026, 10, 1, 9, tzinfo=UTC),
    )
    seeded.session.add(later)
    seeded.session.commit()
    assert dashboard.next_review_on(plan) == date(2026, 10, 15)


def test_plan_history_pairs_versions_with_their_adjustment(seeded: SQLAlchemy) -> None:
    user, _profile, first = _generate(seeded)
    second_profile = make_profile(seeded.session, user, version=2, goal=Goal.MAINTENANCE)
    second = plans.generate_for_profile(user, second_profile, TODAY)
    seeded.session.commit()
    history = dashboard.plan_history(user)
    assert [item.version for item, _adj in history] == [2, 1]
    assert history[0][0] is second.plan
    assert history[0][1] is not None
    assert history[0][1].reason.value == "profile_change"
    assert history[1][1] is not None
    assert history[1][1].reason.value == "initial"
    assert first.plan is history[1][0]


def test_today_targets_with_and_without_carb_cycling(seeded: SQLAlchemy) -> None:
    _user, _profile, plain = _generate(seeded)
    assert plain.plan is not None
    targets = dashboard.today_targets(plain.plan)
    assert targets["cycle"] is None
    assert targets["base"]["calories"] == plain.plan.calorie_target

    user2 = make_user(seeded.session, email="ciclo@example.com")
    user2.equipment = list(_user.equipment)
    profile2 = make_profile(seeded.session, user2, wants_carb_cycling=True)
    cycled = plans.generate_for_profile(user2, profile2, TODAY)
    seeded.session.commit()
    assert cycled.plan is not None
    targets = dashboard.today_targets(cycled.plan)
    assert targets["cycle"] is not None
    assert targets["cycle"]["high"]["carbs_g"] > targets["cycle"]["low"]["carbs_g"]
    assert targets["cycle"]["training_days"] == profile2.training_days_per_week


def test_usable_alternatives_respect_equipment_injuries_and_dislikes(seeded: SQLAlchemy) -> None:
    _user, profile, result = _generate(seeded)
    assert result.routine is not None
    items = [item for day in result.routine.days for item in day.exercises]
    item = next(item for item in items if item.exercise.alternatives)
    full = dashboard.usable_alternatives(item, profile, preset_for("full_gym"))
    assert full, "the full gym allows some alternative"
    assert all(alt.equipment_codes <= preset_for("full_gym") for alt in full)

    nothing = dashboard.usable_alternatives(item, profile, frozenset({"cardio_machine"}))
    assert nothing == []

    profile.disliked_exercises = [full[0].slug]
    fewer = dashboard.usable_alternatives(item, profile, preset_for("full_gym"))
    assert full[0] not in fewer

    profile.disliked_exercises = []
    for area in InjuryArea:
        profile.injuries.append(Injury(area=area, severity=Severity.SEVERE))
    seeded.session.flush()
    hurt = dashboard.usable_alternatives(item, profile, preset_for("full_gym"))
    assert len(hurt) <= len(full)
    assert all(not alt.contraindications for alt in hurt)


def test_image_frames(database: SQLAlchemy) -> None:
    exercise = make_exercise(database.session, image_path="img/exercises/bench-press/0.jpg")
    assert dashboard.image_frames(exercise) == [
        "img/exercises/bench-press/0.jpg",
        "img/exercises/bench-press/1.jpg",
    ]
    bare = make_exercise(database.session, slug="no-image")
    assert dashboard.image_frames(bare) == []
    odd = make_exercise(database.session, slug="odd-image", image_path="img/x/main.jpg")
    assert dashboard.image_frames(odd) == ["img/x/main.jpg"]
