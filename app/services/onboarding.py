"""Questionnaire flow: drafts, step bookkeeping and turning answers into a profile.

The blueprint validates each step with a form and stores the answers as plain
JSON in a :class:`QuestionnaireDraft`. Completing the questionnaire creates a
new ``Profile`` version, records the equipment, logs today's weight and asks
``services.plans`` to generate the plan and the routine, all in one
transaction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from flask_babel import lazy_gettext as _l
from sqlalchemy import func, select

from app.engine.enums import (
    ActivityIntensity,
    Aggressiveness,
    BodyFatMethod,
    DietPattern,
    Goal,
    InjuryArea,
    JobActivity,
    Level,
    Severity,
    Sex,
    TrainingExperience,
    TrainingLocation,
    TrainingTime,
)
from app.engine.safety import SafetyError
from app.engine.types import InputError
from app.extensions import db
from app.labels import EQUIPMENT_CATEGORY
from app.models import Equipment, Exercise, Injury, Profile, QuestionnaireDraft, User, WeightLog
from app.services import plans
from app.services.plans import GenerationResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Step:
    """One page of the questionnaire."""

    number: int
    key: str
    title: Any
    required: tuple[str, ...]


STEPS: tuple[Step, ...] = (
    Step(1, "body", _l("Sobre ti"), ("sex", "birth_date", "height_cm", "weight_kg")),
    Step(2, "activity", _l("Actividad"), ("job_activity", "sleep_hours", "stress_level")),
    Step(
        3,
        "training",
        _l("Entrenamiento"),
        (
            "training_experience",
            "training_days_per_week",
            "session_minutes",
            "training_location",
        ),
    ),
    Step(4, "equipment", _l("Material y lesiones"), ("equipment",)),
    Step(5, "goal", _l("Objetivo"), ("goal",)),
    Step(6, "nutrition", _l("Nutrición"), ("meals_per_day", "diet_pattern")),
    Step(7, "health", _l("Salud"), ("has_eating_disorder_history",)),
)
LAST_STEP = STEPS[-1].number
STEP_BY_NUMBER: dict[int, Step] = {step.number: step for step in STEPS}
DATE_FIELDS = frozenset({"birth_date", "target_date"})
LIST_FIELDS = (
    "priority_muscles",
    "disliked_exercises",
    "preferred_exercises",
    "food_aversions",
    "allergies",
    "equipment",
)


class OnboardingError(Exception):
    """The questionnaire could not be completed; ``reason`` is a stable code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def get_draft(user: User) -> QuestionnaireDraft | None:
    """The user's draft, if any."""
    return db.session.scalar(
        select(QuestionnaireDraft).where(QuestionnaireDraft.user_id == user.id)
    )


def current_profile(user: User) -> Profile | None:
    """The profile version in force."""
    return db.session.scalar(
        select(Profile)
        .where(Profile.user_id == user.id, Profile.superseded_at.is_(None))
        .order_by(Profile.version.desc())
    )


def start_draft(user: User) -> QuestionnaireDraft:
    """Return the existing draft or create one pre-filled from the current profile."""
    draft = get_draft(user)
    if draft is not None:
        return draft
    profile = current_profile(user)
    data = profile_to_data(profile, [item.code for item in user.equipment]) if profile else {}
    draft = QuestionnaireDraft(user=user, step=LAST_STEP if profile else 0, data=data)
    db.session.add(draft)
    db.session.commit()
    return draft


def save_step(draft: QuestionnaireDraft, number: int, values: dict[str, Any]) -> None:
    """Merge one step's answers into the draft and record the progress."""
    draft.data = {**draft.data, **values}
    draft.step = max(draft.step, number)
    db.session.commit()


def first_incomplete_step(data: dict[str, Any]) -> int | None:
    """Number of the first step whose required answers are missing (``None`` when complete)."""
    for step in STEPS:
        if any(data.get(key) in (None, "", []) for key in step.required):
            return step.number
    return None


def profile_to_data(profile: Profile, equipment_codes: list[str]) -> dict[str, Any]:
    """Draft answers pre-filled from a stored profile (for updating the questionnaire)."""
    data: dict[str, Any] = {
        "sex": profile.sex.value,
        "birth_date": profile.birth_date.isoformat(),
        "height_cm": profile.height_cm,
        "weight_kg": profile.weight_kg,
        "neck_cm": profile.neck_cm,
        "waist_cm": profile.waist_cm,
        "hip_cm": profile.hip_cm,
        "body_fat_pct": profile.body_fat_pct,
        "body_fat_method": profile.body_fat_method.value,
        "job_activity": profile.job_activity.value,
        "daily_steps": profile.daily_steps,
        "sleep_hours": profile.sleep_hours,
        "stress_level": profile.stress_level,
        "other_activity_type": profile.other_activity_type or "",
        "other_activity_sessions_per_week": profile.other_activity_sessions_per_week,
        "other_activity_minutes": profile.other_activity_minutes,
        "other_activity_intensity": (
            profile.other_activity_intensity.value if profile.other_activity_intensity else ""
        ),
        "training_experience": profile.training_experience.value,
        "training_days_per_week": profile.training_days_per_week,
        "session_minutes": profile.session_minutes,
        "training_location": profile.training_location.value,
        "training_time": profile.training_time.value,
        "equipment": sorted(equipment_codes),
        "equipment_for_location": profile.training_location.value,
        "priority_muscles": list(profile.priority_muscles),
        "injuries": {injury.area.value: injury.severity.value for injury in profile.injuries},
        "disliked_exercises": list(profile.disliked_exercises),
        "preferred_exercises": list(profile.preferred_exercises),
        "goal": profile.goal.value,
        "aggressiveness": profile.aggressiveness.value,
        "target_weight_kg": profile.target_weight_kg,
        "target_date": profile.target_date.isoformat() if profile.target_date else None,
        "meals_per_day": profile.meals_per_day,
        "diet_pattern": profile.diet_pattern.value,
        "food_aversions": list(profile.food_aversions),
        "allergies": list(profile.allergies),
        "budget_level": profile.budget_level.value,
        "cooking_time": profile.cooking_time.value,
        "wants_carb_cycling": profile.wants_carb_cycling,
        "alcohol_drinks_per_week": profile.alcohol_drinks_per_week,
        "caffeine_cups_per_day": profile.caffeine_cups_per_day,
        "is_pregnant_or_breastfeeding": profile.is_pregnant_or_breastfeeding,
        "has_eating_disorder_history": profile.has_eating_disorder_history,
        "notes": profile.notes or "",
    }
    return data


def _optional_float(value: Any) -> float | None:
    return None if value in (None, "") else float(value)


def _optional_date(value: Any) -> date | None:
    return None if value in (None, "") else date.fromisoformat(str(value))


def _list(value: Any) -> list[str]:
    return [str(item) for item in (value or [])]


def data_to_profile_values(
    data: dict[str, Any],
) -> tuple[dict[str, Any], list[tuple[InjuryArea, Severity]], list[str]]:
    """Profile constructor kwargs, injuries and equipment codes from a complete draft.

    Raises:
        OnboardingError: If a required answer is missing or has an impossible value.
    """
    if first_incomplete_step(data) is not None:
        raise OnboardingError("incomplete")
    try:
        body_fat_pct = _optional_float(data.get("body_fat_pct"))
        method = BodyFatMethod(data.get("body_fat_method") or "none")
        if body_fat_pct is None:
            method = BodyFatMethod.NONE
        elif method is BodyFatMethod.NONE:
            method = BodyFatMethod.VISUAL
        intensity = data.get("other_activity_intensity") or None
        values: dict[str, Any] = {
            "sex": Sex(data["sex"]),
            "birth_date": date.fromisoformat(str(data["birth_date"])),
            "height_cm": float(data["height_cm"]),
            "weight_kg": float(data["weight_kg"]),
            "neck_cm": _optional_float(data.get("neck_cm")),
            "waist_cm": _optional_float(data.get("waist_cm")),
            "hip_cm": _optional_float(data.get("hip_cm")),
            "body_fat_pct": body_fat_pct,
            "body_fat_method": method,
            "job_activity": JobActivity(data["job_activity"]),
            "daily_steps": (
                None if data.get("daily_steps") in (None, "") else int(data["daily_steps"])
            ),
            "sleep_hours": float(data["sleep_hours"]),
            "stress_level": int(data["stress_level"]),
            "other_activity_type": (data.get("other_activity_type") or "").strip() or None,
            "other_activity_sessions_per_week": int(
                data.get("other_activity_sessions_per_week") or 0
            ),
            "other_activity_minutes": int(data.get("other_activity_minutes") or 0),
            "other_activity_intensity": ActivityIntensity(intensity) if intensity else None,
            "training_experience": TrainingExperience(data["training_experience"]),
            "training_days_per_week": int(data["training_days_per_week"]),
            "session_minutes": int(data["session_minutes"]),
            "training_location": TrainingLocation(data["training_location"]),
            "training_time": TrainingTime(data.get("training_time") or "none"),
            "priority_muscles": _list(data.get("priority_muscles"))[:2],
            "disliked_exercises": _list(data.get("disliked_exercises")),
            "preferred_exercises": _list(data.get("preferred_exercises")),
            "goal": Goal(data["goal"]),
            "aggressiveness": Aggressiveness(data.get("aggressiveness") or "moderate"),
            "target_date": _optional_date(data.get("target_date")),
            "target_weight_kg": _optional_float(data.get("target_weight_kg")),
            "meals_per_day": int(data["meals_per_day"]),
            "diet_pattern": DietPattern(data["diet_pattern"]),
            "food_aversions": _list(data.get("food_aversions")),
            "allergies": _list(data.get("allergies")),
            "budget_level": Level(data.get("budget_level") or "medium"),
            "cooking_time": Level(data.get("cooking_time") or "medium"),
            "wants_carb_cycling": bool(data.get("wants_carb_cycling", False)),
            "alcohol_drinks_per_week": int(data.get("alcohol_drinks_per_week") or 0),
            "caffeine_cups_per_day": int(data.get("caffeine_cups_per_day") or 0),
            "is_pregnant_or_breastfeeding": bool(data.get("is_pregnant_or_breastfeeding", False)),
            "has_eating_disorder_history": bool(data.get("has_eating_disorder_history", False)),
            "notes": (data.get("notes") or "").strip() or None,
        }
        injuries = [
            (InjuryArea(area), Severity(severity))
            for area, severity in (data.get("injuries") or {}).items()
            if severity and severity != "none"
        ]
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("Draft with an invalid value: %s", exc)
        raise OnboardingError("invalid") from exc
    return values, injuries, _list(data.get("equipment"))


def _upsert_weight(user: User, today: date, weight_kg: float) -> None:
    existing = db.session.scalar(
        select(WeightLog).where(WeightLog.user_id == user.id, WeightLog.logged_on == today)
    )
    if existing is None:
        db.session.add(WeightLog(user=user, logged_on=today, weight_kg=weight_kg))
    else:
        existing.weight_kg = weight_kg


def complete(user: User, draft: QuestionnaireDraft, today: date) -> GenerationResult:
    """Turn the draft into a new profile version and generate plan and routine.

    Raises:
        OnboardingError: ``incomplete`` / ``invalid`` for a bad draft, ``engine``
            when the engine rejected the values or produced an unsafe plan (the
            transaction is rolled back and the draft kept in every case).
    """
    values, injuries, equipment_codes = data_to_profile_values(draft.data)
    previous = current_profile(user)
    version = (
        db.session.scalar(select(func.max(Profile.version)).where(Profile.user_id == user.id)) or 0
    ) + 1
    profile = Profile(user=user, version=version, **values)
    for area, severity in injuries:
        profile.injuries.append(Injury(area=area, severity=severity))
    if previous is not None:
        previous.supersede()
    db.session.add(profile)
    equipment = db.session.scalars(
        select(Equipment).where(Equipment.code.in_(equipment_codes))
    ).all()
    user.equipment = list(equipment)
    _upsert_weight(user, today, values["weight_kg"])
    try:
        db.session.flush()
        result = plans.generate_for_profile(user, profile, today)
    except (InputError, SafetyError):
        db.session.rollback()
        logger.exception("Plan generation failed for user %s", user.id)
        raise OnboardingError("engine") from None
    db.session.delete(draft)
    db.session.commit()
    logger.info("Questionnaire completed by user %s (profile v%s)", user.id, version)
    return result


def equipment_names() -> list[tuple[str, str]]:
    """``(code, Spanish name)`` for every piece of equipment, in catalogue order."""
    rows = db.session.scalars(
        select(Equipment).order_by(Equipment.sort_order, Equipment.name_es)
    ).all()
    return [(row.code, row.name_es) for row in rows]


def equipment_groups() -> list[tuple[str, list[tuple[str, str]]]]:
    """Equipment grouped by category, ready for the checkbox fieldset."""
    rows = db.session.scalars(
        select(Equipment).order_by(Equipment.sort_order, Equipment.name_es)
    ).all()
    groups: list[tuple[str, list[tuple[str, str]]]] = []
    for category in EQUIPMENT_CATEGORY:
        items = [(row.code, row.name_es) for row in rows if row.category is category]
        if items:
            groups.append((str(EQUIPMENT_CATEGORY[category]), items))
    return groups


@dataclass(frozen=True)
class ExerciseLookup:
    """Exercise names for the datalist and the name ↔ slug mapping."""

    names: tuple[str, ...]
    slug_by_key: dict[str, str]
    name_by_slug: dict[str, str]

    def slug_of(self, name: str) -> str | None:
        """Slug for a Spanish or English name (case-insensitive) or a slug itself."""
        return self.slug_by_key.get(name.strip().lower())

    def name_of(self, slug: str) -> str | None:
        """Spanish name of an exercise slug."""
        return self.name_by_slug.get(slug)


def exercise_lookup() -> ExerciseLookup:
    """Names and slugs of the active exercises."""
    rows = db.session.execute(
        select(Exercise.slug, Exercise.name_es, Exercise.name_en)
        .where(Exercise.is_active.is_(True))
        .order_by(Exercise.name_es)
    ).all()
    slug_by_key: dict[str, str] = {}
    for slug, name_es, name_en in rows:
        slug_by_key[slug.lower()] = slug
        slug_by_key[name_es.strip().lower()] = slug
        slug_by_key[name_en.strip().lower()] = slug
    return ExerciseLookup(
        names=tuple(name_es for _slug, name_es, _en in rows),
        slug_by_key=slug_by_key,
        name_by_slug={slug: name_es for slug, name_es, _en in rows},
    )
