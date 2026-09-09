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


def test_note_params_turn_internal_codes_into_words(app: Flask) -> None:
    """El motor pone códigos en los parámetros; nadie debería leerlos."""
    with app.app_context():
        params = labels.note_params("routine.split", {"split": "upper_lower", "days": 4})
        assert params["split"] == "Torso / pierna"
        assert params["days"] == 4

        volume = labels.note_params("routine.volume_low", {"muscle": "calves"})
        assert volume["muscle"] == "Gemelos"

        priority = labels.note_params("routine.priority_applied", {"muscles": "glutes, shoulders"})
        assert priority["muscles"] == "glúteos, hombros"

        missing = labels.note_params("routine.pattern_missing", {"pattern": "vertical_pull"})
        assert missing["pattern"] == "Tracción vertical"
        assert missing["suggestion"] == "una barra de dominadas o bandas"


def test_note_params_are_left_alone_outside_the_application() -> None:
    """En los logs y en los tests del motor mandan los códigos, que son estables."""
    params = {"split": "upper_lower", "days": 4}
    assert labels.note_params("routine.split", params) is params


def test_rendered_notes_never_show_an_internal_code(app: Flask) -> None:
    from app.engine import messages
    from app.engine.types import Note

    with app.test_request_context("/"):
        text = messages.render(Note("routine.split", params={"split": "ppl_twice", "days": 6}))
        assert text == "Split Empuje / tracción / pierna, dos veces de 6 días."
        assert "ppl_twice" not in text
