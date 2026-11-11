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
def test_english_dates_put_the_month_first() -> None:
    assert fdate(DAY) == "11/5/2026"
    assert fdate(DAY, "long") == "November 5, 2026"
