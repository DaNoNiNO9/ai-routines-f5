"""Enum labels and the small helpers of the questionnaire forms."""

from __future__ import annotations

from datetime import date

from flask import Flask

from app import labels
from app.blueprints.onboarding.forms import _jsonable, split_list
from app.engine.enums import Goal, MuscleGroup


def test_choices_use_enum_values(app: Flask) -> None:
    with app.app_context():
        pairs = labels.choices(labels.GOAL)
        assert pairs[0][0] == "fat_loss"
        assert str(pairs[0][1]) == "Perder grasa"
        assert labels.choices(labels.STRESS_LEVEL)[0][0] == 1


def test_label_accepts_members_values_and_unknowns(app: Flask) -> None:
    with app.app_context():
        assert labels.label(labels.GOAL, Goal.MUSCLE_GAIN) == "Ganar músculo"
        assert labels.label(labels.GOAL, "muscle_gain") == "Ganar músculo"
        assert labels.label(labels.STRESS_LEVEL, 4) == "4 · Alto"
        assert labels.label(labels.GOAL, None) == ""
        assert labels.label(labels.GOAL, "") == ""
        assert labels.label(labels.GOAL, "unknown_goal") == "unknown_goal"


def test_priority_muscles_exclude_the_ones_the_engine_does_not_target() -> None:
    assert MuscleGroup.FOREARMS not in labels.PRIORITY_MUSCLES
    assert MuscleGroup.GLUTES in labels.PRIORITY_MUSCLES


def test_split_list_trims_dedupes_and_accepts_several_separators() -> None:
    assert split_list(None) == []
    assert split_list("  ") == []
    assert split_list("a, A ;b\nc,,") == ["a", "b", "c"]


def test_jsonable_handles_dates_and_lists() -> None:
    assert _jsonable(date(2026, 9, 9)) == "2026-09-09"
    assert _jsonable(("a", date(2026, 1, 1))) == ["a", "2026-01-01"]
    assert _jsonable(3.5) == 3.5
