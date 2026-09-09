"""Drafts, step bookkeeping, the draft ↔ profile round trip and completion."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.engine.enums import BodyFatMethod, InjuryArea, Severity, TrainingLocation
from app.engine.equipment_presets import preset_for
from app.models import Equipment, Injury, Profile, QuestionnaireDraft, WeightLog
from app.services import onboarding
from tests.factories import make_profile, make_user

TODAY = date(2026, 9, 9)

COMPLETE_DRAFT: dict[str, Any] = {
    "sex": "male",
    "birth_date": "1990-03-15",
    "height_cm": 178,
    "weight_kg": 84.5,
    "neck_cm": 39,
    "waist_cm": 92,
    "hip_cm": None,
    "body_fat_pct": None,
    "body_fat_method": "none",
    "job_activity": "sedentary",
    "daily_steps": 6500,
    "sleep_hours": 7,
    "stress_level": 3,
    "other_activity_type": "",
    "other_activity_sessions_per_week": 0,
    "other_activity_minutes": 0,
    "other_activity_intensity": "",
    "training_experience": "6_to_24_months",
    "training_days_per_week": 4,
    "session_minutes": 60,
    "training_location": "full_gym",
    "training_time": "evening",
    "equipment": sorted(preset_for("full_gym")),
    "equipment_for_location": "full_gym",
    "priority_muscles": ["back"],
    "injuries": {"knee": "mild", "shoulder": "none"},
    "disliked_exercises": ["barbell-squat"],
    "preferred_exercises": [],
    "goal": "fat_loss",
    "aggressiveness": "moderate",
    "target_weight_kg": 78,
    "target_date": None,
    "meals_per_day": 4,
    "diet_pattern": "omnivore",
    "food_aversions": ["hígado"],
    "allergies": [],
    "budget_level": "medium",
    "cooking_time": "low",
    "wants_carb_cycling": True,
    "alcohol_drinks_per_week": 2,
    "caffeine_cups_per_day": 3,
    "is_pregnant_or_breastfeeding": False,
    "has_eating_disorder_history": False,
    "notes": "  ",
}


def test_first_incomplete_step_walks_the_required_keys() -> None:
    assert onboarding.first_incomplete_step({}) == 1
    partial = {"sex": "male", "birth_date": "1990-01-01", "height_cm": 180, "weight_kg": 80}
    assert onboarding.first_incomplete_step(partial) == 2
    assert onboarding.first_incomplete_step(COMPLETE_DRAFT) is None
    assert onboarding.first_incomplete_step({**COMPLETE_DRAFT, "equipment": []}) == 4


def test_start_draft_is_idempotent_and_prefilled_from_the_profile(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    fresh = onboarding.start_draft(user)
    assert fresh.step == 0
    assert fresh.data == {}
    assert onboarding.start_draft(user) is fresh

    other = make_user(database.session, email="otra@example.com")
    profile = make_profile(database.session, other, priority_muscles=["glutes"])
    profile.injuries.append(Injury(area=InjuryArea.KNEE, severity=Severity.MILD))
    barbell = Equipment(code="barbell", name_es="Barra", name_en="Barbell", category="free_weights")
    other.equipment = [barbell]
    database.session.commit()
    prefilled = onboarding.start_draft(other)
    assert prefilled.step == onboarding.LAST_STEP
    assert prefilled.data["sex"] == "female"
    assert prefilled.data["birth_date"] == "1992-05-20"
    assert prefilled.data["injuries"] == {"knee": "mild"}
    assert prefilled.data["equipment"] == ["barbell"]
    assert prefilled.data["equipment_for_location"] == "full_gym"
    assert onboarding.first_incomplete_step(prefilled.data) is None


def test_save_step_merges_and_never_lowers_progress(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    draft = onboarding.start_draft(user)
    onboarding.save_step(draft, 1, {"sex": "male", "height_cm": 180})
    onboarding.save_step(draft, 2, {"job_activity": "standing"})
    onboarding.save_step(draft, 1, {"sex": "female"})
    stored = database.session.scalar(select(QuestionnaireDraft))
    assert stored is not None
    assert stored.step == 2
    assert stored.data == {"sex": "female", "height_cm": 180, "job_activity": "standing"}


def test_data_to_profile_values_normalises_the_answers() -> None:
    values, injuries, equipment = onboarding.data_to_profile_values(COMPLETE_DRAFT)
    assert values["birth_date"] == date(1990, 3, 15)
    assert values["body_fat_method"] is BodyFatMethod.NONE
    assert values["other_activity_intensity"] is None
    assert values["other_activity_type"] is None
    assert values["notes"] is None
    assert values["training_location"] is TrainingLocation.FULL_GYM
    assert values["wants_carb_cycling"] is True
    assert injuries == [(InjuryArea.KNEE, Severity.MILD)]
    assert equipment == sorted(preset_for("full_gym"))

    declared = onboarding.data_to_profile_values(
        {**COMPLETE_DRAFT, "body_fat_pct": 18, "body_fat_method": "none"}
    )[0]
    assert declared["body_fat_method"] is BodyFatMethod.VISUAL


@pytest.mark.parametrize(
    ("patch", "reason"),
    [
        ({"goal": ""}, "incomplete"),
        ({"goal": "become-a-fish"}, "invalid"),
        ({"height_cm": "tall"}, "invalid"),
        ({"injuries": {"knee": "catastrophic"}}, "invalid"),
    ],
)
def test_bad_drafts_are_rejected_with_a_code(patch: dict[str, Any], reason: str) -> None:
    with pytest.raises(onboarding.OnboardingError) as caught:
        onboarding.data_to_profile_values({**COMPLETE_DRAFT, **patch})
    assert caught.value.reason == reason


def test_complete_creates_profile_equipment_weight_and_plan(seeded: SQLAlchemy) -> None:
    user = make_user(seeded.session)
    draft = onboarding.start_draft(user)
    draft.data = dict(COMPLETE_DRAFT)
    seeded.session.commit()

    result = onboarding.complete(user, draft, TODAY)

    profile = onboarding.current_profile(user)
    assert profile is not None
    assert profile.version == 1
    assert profile.weight_kg == 84.5
    assert [(i.area, i.severity) for i in profile.injuries] == [(InjuryArea.KNEE, Severity.MILD)]
    assert {item.code for item in user.equipment} == preset_for("full_gym")
    weight = seeded.session.scalar(select(WeightLog).where(WeightLog.user_id == user.id))
    assert weight is not None
    assert weight.logged_on == TODAY
    assert weight.weight_kg == 84.5
    assert onboarding.get_draft(user) is None
    assert result.plan is not None
    assert result.routine is not None
    assert result.plan.details["carb_cycle"] is not None
    assert all(
        item.exercise.slug != "barbell-squat"
        for day in result.routine.days
        for item in day.exercises
    )


def test_complete_again_versions_the_profile_and_updates_the_weight(seeded: SQLAlchemy) -> None:
    user = make_user(seeded.session)
    draft = onboarding.start_draft(user)
    draft.data = dict(COMPLETE_DRAFT)
    seeded.session.commit()
    onboarding.complete(user, draft, TODAY)

    again = onboarding.start_draft(user)
    assert again.data["weight_kg"] == 84.5
    again.data = {**again.data, "weight_kg": 83.0, "goal": "maintenance"}
    seeded.session.commit()
    onboarding.complete(user, again, TODAY)

    versions = seeded.session.scalars(select(Profile).order_by(Profile.version)).all()
    assert [p.version for p in versions] == [1, 2]
    assert versions[0].superseded_at is not None
    assert versions[1].superseded_at is None
    weights = seeded.session.scalars(select(WeightLog)).all()
    assert len(weights) == 1
    assert weights[0].weight_kg == 83.0


def test_complete_rolls_back_when_the_engine_rejects_the_values(
    seeded: SQLAlchemy, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = make_user(seeded.session)
    draft = onboarding.start_draft(user)
    draft.data = dict(COMPLETE_DRAFT)
    seeded.session.commit()

    def explode(*_args: Any, **_kwargs: Any) -> None:
        from app.engine.types import InputError

        raise InputError("age=200 is outside the supported range")

    monkeypatch.setattr(onboarding.plans, "generate_for_profile", explode)
    with pytest.raises(onboarding.OnboardingError) as caught:
        onboarding.complete(user, draft, TODAY)
    assert caught.value.reason == "engine"
    assert seeded.session.scalars(select(Profile)).all() == []
    assert onboarding.get_draft(user) is not None


def test_catalogue_helpers(seeded: SQLAlchemy) -> None:
    groups = onboarding.equipment_groups()
    assert next(label for label, _items in groups) == "Peso corporal"
    assert sum(len(items) for _label, items in groups) == len(onboarding.equipment_names())
    lookup = onboarding.exercise_lookup()
    assert lookup.slug_of("Press de banca con barra") == "barbell-bench-press-medium-grip"
    assert lookup.slug_of("barbell bench press - medium grip") == "barbell-bench-press-medium-grip"
    assert lookup.slug_of("BARBELL-BENCH-PRESS-MEDIUM-GRIP") == "barbell-bench-press-medium-grip"
    assert lookup.slug_of("press de nada") is None
    assert lookup.name_of("barbell-bench-press-medium-grip") == "Press de banca con barra"
    assert "Press de banca con barra" in lookup.names


def test_declared_body_fat_keeps_its_method() -> None:
    values = onboarding.data_to_profile_values(
        {**COMPLETE_DRAFT, "body_fat_pct": 18, "body_fat_method": "calipers"}
    )[0]
    assert values["body_fat_method"] is BodyFatMethod.CALIPERS


def test_equipment_groups_skip_empty_categories(database: SQLAlchemy) -> None:
    database.session.add(
        Equipment(code="barbell", name_es="Barra", name_en="Barbell", category="free_weights")
    )
    database.session.commit()
    assert onboarding.equipment_groups() == [("Peso libre", [("barbell", "Barra")])]
    draft = onboarding.start_draft(make_user(database.session))
    assert repr(draft) == f"<QuestionnaireDraft user={draft.user_id} step=0>"
