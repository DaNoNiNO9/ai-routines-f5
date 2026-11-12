"""How you arrive at the session: sleep, yesterday's food, last session and long deficits."""

from __future__ import annotations

from app.engine.messages import render
from app.engine.readiness import DayKind, Sleep, assess


def test_with_nothing_known_it_is_a_normal_day() -> None:
    day = assess(None, None, None, 0)
    assert day.kind is DayKind.NORMAL
    assert day.load_factor == 1.0
    assert day.extra_rir == 0
    assert day.reasons == ()


def test_sleeping_well_and_eating_enough_is_normal() -> None:
    assert assess(Sleep.GOOD, 0.98, 3, 2).kind is DayKind.NORMAL


def test_bad_sleep_alone_makes_an_easy_day() -> None:
    day = assess(Sleep.BAD, None, None, 0)
    assert day.kind is DayKind.EASY
    assert day.load_factor == 0.95
    assert day.extra_rir == 1


def test_one_mild_signal_is_not_enough() -> None:
    assert assess(Sleep.OK, None, None, 0).kind is DayKind.NORMAL
    assert assess(None, 0.8, None, 0).kind is DayKind.NORMAL


def test_bad_sleep_and_little_food_make_an_easier_day() -> None:
    day = assess(Sleep.BAD, 0.6, None, 0)
    assert day.kind is DayKind.EASIER
    assert day.load_factor == 0.90
    codes = [note.code for note in day.reasons]
    assert codes == ["readiness.sleep_bad", "readiness.underfed"]


def test_a_long_deficit_and_a_hard_last_session_add_up() -> None:
    day = assess(Sleep.OK, None, 5, 9)  # 1 + 1 + 1 = 3 puntos
    assert day.kind is DayKind.EASY
    assert day.points == 3
    assert assess(Sleep.BAD, None, 5, 9).kind is DayKind.EASIER  # 2 + 1 + 1
    assert "readiness.long_deficit" in [note.code for note in day.reasons]


def test_reasons_read_like_a_person() -> None:
    day = assess(Sleep.BAD, 0.62, 5, 10)
    texts = [render(note) for note in day.reasons]
    assert "Has dormido mal." in texts
    assert "Ayer comiste el 62 % de lo previsto." in texts
    assert "Llevas 10 semanas comiendo por debajo de lo que gastas." in texts
