"""Figures and dates follow the reader's language, never Python's defaults."""

from __future__ import annotations

from datetime import date

import pytest
from flask import Flask

from app.formatting import MINUS, days_from_now, duration, fdate, kg, num, signed

DAY = date(2026, 11, 5)


@pytest.fixture
def es(app: Flask):
    with app.test_request_context("/?lang=es"):
        yield


@pytest.fixture
def en(app: Flask):
    with app.test_request_context("/?lang=en"):
        yield


@pytest.mark.usefixtures("es")
def test_spanish_uses_a_decimal_comma_and_drops_useless_zeros() -> None:
    assert num(84.0) == "84"
    assert num(2.5) == "2,5"
    assert num(12345.6) == "12.345,6"
    assert num(2.0, fixed=True) == "2,0"
    assert num(-0.38, 2) == f"{MINUS}0,38"
    assert signed(0.5) == "+0,5"
    assert signed(0) == "0"
    assert kg(62.5, 2) == "62,5 kg"
    assert num(None) == kg(None) == "—"


@pytest.mark.usefixtures("es")
def test_spanish_does_not_split_four_digit_numbers() -> None:
    """RAE: "1995 kcal" and "8000 pasos", like the |int figures beside them; "12.000" does split."""
    assert num(1995, 0) == "1995"
    assert num(8000, 0) == "8000"
    assert num(9999.5, 1) == "9999,5"
    assert num(-1500, 0) == f"{MINUS}1500"
    assert num(10000, 0) == "10.000"


@pytest.mark.usefixtures("en")
def test_english_keeps_its_thousands_comma() -> None:
    assert num(1995, 0) == "1,995"


@pytest.mark.usefixtures("en")
def test_english_keeps_the_decimal_point() -> None:
    assert num(2.5) == "2.5"
    assert num(12345.6) == "12,345.6"


@pytest.mark.usefixtures("es")
def test_durations_read_like_people_say_them() -> None:
    assert duration(180) == "3 min"
    assert duration(150) == "2 min 30 s"
    assert duration(45) == "45 s"


@pytest.mark.usefixtures("es")
def test_spanish_dates_never_show_iso() -> None:
    assert fdate(DAY) == "5/11/2026"
    assert fdate("2026-11-05") == "5/11/2026"
    assert fdate(DAY, "day") == "5/11"
    assert fdate(DAY, "long") == "5 de noviembre de 2026"
    assert fdate(None) == "—"
    assert days_from_now(date(2026, 11, 19), DAY) == "en 14 días"
    assert days_from_now(date(2026, 11, 6), DAY) == "mañana"
    assert days_from_now(DAY, DAY) == "hoy"


@pytest.mark.usefixtures("en")
def test_english_dates_spell_the_month() -> None:
    # 11/5/2026 es 5 de noviembre en EE. UU. y 11 de mayo en Reino Unido.
    assert fdate(DAY) == "Nov 5, 2026"
    assert fdate(DAY, "day") == "Nov 5"
    assert fdate(DAY, "long") == "November 5, 2026"
