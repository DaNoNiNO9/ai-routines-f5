"""Numbers, weights, durations and dates in the reader's language.

One place decides how a figure looks, so "84,5 kg" never sits next to
"84.5 kg" and a date is never shown as ``2026-11-25``. Registered as Jinja
filters by the factory and used from Python code that builds text.

Outside a request (scripts, engine tests) Flask-Babel falls back to the default
locale, which is what those callers expect.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from babel.dates import format_skeleton
from flask import Flask
from flask_babel import format_date, format_decimal, get_locale, gettext, ngettext

TRIM_ZEROS = {0: "#,##0", 1: "#,##0.#", 2: "#,##0.##"}
FIXED = {0: "#,##0", 1: "#,##0.0", 2: "#,##0.00"}
MINUS = chr(0x2212)  # typographic minus, not the hyphen
TIMES = chr(0xD7)  # the multiplication sign of 60 kg x 8


def num(value: Any, decimals: int = 1, *, fixed: bool = False) -> str:
    """A number with the locale's separators; trailing zeros dropped unless ``fixed``.

    ``None`` renders as an em dash so a missing value is visible, not "None".
    A negative number uses the true minus sign, as typography asks.
    """
    if value is None or value == "":
        return "—"
    pattern = (FIXED if fixed else TRIM_ZEROS)[decimals]
    text = format_decimal(float(value), format=pattern)
    return text.replace("-", MINUS)


def signed(value: Any, decimals: int = 1) -> str:
    """Like :func:`num` but always with a sign (``+0,5`` / minus ``0,38``)."""
    if value is None:
        return "—"
    text = num(value, decimals)
    return text if text.startswith(MINUS) or float(value) == 0 else f"+{text}"


def kg(value: Any, decimals: int = 1) -> str:
    """``84,5 kg``; ``—`` when unknown."""
    return "—" if value is None else f"{num(value, decimals)} kg"


def duration(seconds: Any) -> str:
    """``3 min``, ``2 min 30 s`` or ``45 s``: rest times as people say them."""
    total = round(float(seconds or 0))
    minutes, rest = divmod(total, 60)
    if minutes and rest:
        return gettext("%(min)s min %(s)s s", min=minutes, s=rest)
    if minutes:
        return gettext("%(min)s min", min=minutes)
    return gettext("%(s)s s", s=rest)


def fdate(value: date | datetime | str | None, style: str = "short") -> str:
    """A calendar date in the locale's own order.

    ``short`` 25/11/2026 (en: 11/25/2026), ``day`` 25/11, ``medium`` 25 nov,
    ``long`` 25 de noviembre de 2026.

    ISO strings (as kept in drafts and JSON snapshots) are accepted too.
    """
    if value is None or value == "":
        return "—"
    if isinstance(value, str):
        value = date.fromisoformat(value[:10])
    if isinstance(value, datetime):
        value = value.date()
    if style == "long":
        return format_date(value, format="long")
    skeleton = {"day": "dM", "medium": "MMMd"}.get(style, "yMd")
    return format_skeleton(skeleton, value, locale=get_locale())


def days_from_now(value: date, today: date) -> str:
    """``hoy``, ``mañana`` or ``en 14 días``."""
    delta = (value - today).days
    if delta == 0:
        return gettext("hoy")
    if delta == 1:
        return gettext("mañana")
    if delta < 0:
        return ngettext("hace %(num)s día", "hace %(num)s días", -delta)
    return ngettext("en %(num)s día", "en %(num)s días", delta)


def register(app: Flask) -> None:
    """Expose the helpers as Jinja filters."""
    app.add_template_filter(num, "num")
    app.add_template_filter(signed, "signed")
    app.add_template_filter(kg, "kg")
    app.add_template_filter(duration, "duration")
    app.add_template_filter(fdate, "fdate")
