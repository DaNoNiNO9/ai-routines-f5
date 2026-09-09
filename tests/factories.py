"""Helpers that build valid rows with sensible defaults; override anything by keyword."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.engine.enums import (
    BmrMethod,
    BodyFatMethod,
    Confidence,
    Force,
    Goal,
    JobActivity,
    Mechanic,
    MovementPattern,
    MuscleGroup,
    Sex,
    SplitType,
    TechnicalLevel,
    TrainingExperience,
    TrainingLocation,
)
from app.models import Equipment, Exercise, Plan, Profile, Routine, User

PROFILE_DEFAULTS: dict[str, Any] = {
    "sex": Sex.FEMALE,
    "birth_date": date(1992, 5, 20),
    "height_cm": 168.0,
    "weight_kg": 64.0,
    "neck_cm": 33.0,
    "waist_cm": 74.0,
    "hip_cm": 96.0,
    "body_fat_method": BodyFatMethod.NAVY,
    "job_activity": JobActivity.SEDENTARY,
    "daily_steps": 6000,
    "sleep_hours": 7.0,
    "stress_level": 3,
    "training_experience": TrainingExperience.MONTHS_6_TO_24,
    "training_days_per_week": 4,
    "session_minutes": 60,
    "training_location": TrainingLocation.FULL_GYM,
    "goal": Goal.FAT_LOSS,
    "priority_muscles": ["glutes", "shoulders"],
}

PLAN_DEFAULTS: dict[str, Any] = {
    "goal": Goal.FAT_LOSS,
    "calorie_target": 1800,
    "protein_g": 130.0,
    "carbs_g": 180.0,
    "fat_g": 60.0,
    "fiber_g": 25.0,
    "water_ml": 2200,
    "bmr_kcal": 1400.0,
    "tdee_kcal": 2200.0,
    "bmr_method": BmrMethod.MIFFLIN_ST_JEOR,
    "confidence": Confidence.MEDIUM,
}


def aware(year: int, month: int, day: int, hour: int = 10) -> datetime:
    """Aware UTC datetime shorthand."""
    return datetime(year, month, day, hour, tzinfo=UTC)


def make_user(session: Session, email: str = "ana@example.com", **overrides: Any) -> User:
    """Persist a user with placeholder credentials."""
    values: dict[str, Any] = {
        "email": email,
        "password_hash": "argon2-placeholder",
        "display_name": "Ana",
    }
    values.update(overrides)
    user = User(**values)
    session.add(user)
    session.flush()
    return user


def make_profile(session: Session, user: User, version: int = 1, **overrides: Any) -> Profile:
    """Persist a complete, valid questionnaire version for ``user``."""
    values = {**PROFILE_DEFAULTS, **overrides}
    profile = Profile(user=user, version=version, **values)
    session.add(profile)
    session.flush()
    return profile


def make_equipment(session: Session, code: str = "barbell", **overrides: Any) -> Equipment:
    """Persist one piece of equipment."""
    values: dict[str, Any] = {
        "code": code,
        "name_es": code,
        "name_en": code,
        "category": "free_weights",
    }
    values.update(overrides)
    item = Equipment(**values)
    session.add(item)
    session.flush()
    return item


def make_exercise(session: Session, slug: str = "bench-press", **overrides: Any) -> Exercise:
    """Persist a catalogue exercise (a barbell bench press by default)."""
    values: dict[str, Any] = {
        "slug": slug,
        "name_es": "Press de banca",
        "name_en": "Bench press",
        "primary_muscle": MuscleGroup.CHEST,
        "secondary_muscles": ["triceps", "shoulders"],
        "movement_pattern": MovementPattern.HORIZONTAL_PUSH,
        "mechanic": Mechanic.COMPOUND,
        "force": Force.PUSH,
        "technical_level": TechnicalLevel.BEGINNER,
    }
    values.update(overrides)
    exercise = Exercise(**values)
    session.add(exercise)
    session.flush()
    return exercise


def make_plan(
    session: Session, user: User, profile: Profile, version: int = 1, **overrides: Any
) -> Plan:
    """Persist a nutrition plan for ``profile``."""
    values = {**PLAN_DEFAULTS, "starts_on": date(2026, 9, 9), **overrides}
    plan = Plan(user=user, profile=profile, version=version, **values)
    session.add(plan)
    session.flush()
    return plan


def make_routine(
    session: Session, user: User, profile: Profile, version: int = 1, **overrides: Any
) -> Routine:
    """Persist a routine shell (no days) for ``profile``."""
    values: dict[str, Any] = {
        "name": "Full body 3 días",
        "split_type": SplitType.FULL_BODY,
        "days_per_week": 3,
    }
    values.update(overrides)
    routine = Routine(user=user, profile=profile, version=version, **values)
    session.add(routine)
    session.flush()
    return routine
