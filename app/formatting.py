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
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from babel.dates import format_skeleton
from flask import Flask, has_request_context
from flask_babel import format_currency, format_date, format_decimal, get_locale, gettext, ngettext
from flask_login import current_user

TRIM_ZEROS = {0: "#,##0", 1: "#,##0.#", 2: "#,##0.##"}
FIXED = {0: "#,##0", 1: "#,##0.0", 2: "#,##0.00"}
# Spanish does not split four-digit numbers ("1995 kcal", "8000 pasos"; RAE,
# Ortografía 2010), although Babel would print "1.995". From five digits on it does.
UNGROUPED = {key: pattern.replace("#,##", "") for key, pattern in TRIM_ZEROS.items()}
UNGROUPED_FIXED = {key: pattern.replace("#,##", "") for key, pattern in FIXED.items()}
DEFAULT_ZONE = "Europe/Madrid"
MINUS = chr(0x2212)  # typographic minus, not the hyphen
TIMES = chr(0xD7)  # the multiplication sign of 60 kg x 8


def num(value: Any, decimals: int = 1, *, fixed: bool = False) -> str:
    """A number with the locale's separators; trailing zeros dropped unless ``fixed``.

    ``None`` renders as an em dash so a missing value is visible, not "None".
    A negative number uses the true minus sign, as typography asks.
    """
    if value is None or value == "":
        return "—"
    number = float(value)
    if abs(number) < 10000 and str(get_locale() or "es").startswith("es"):
        pattern = (UNGROUPED_FIXED if fixed else UNGROUPED)[decimals]
    else:
        pattern = (FIXED if fixed else TRIM_ZEROS)[decimals]
    text = format_decimal(number, format=pattern)
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
    ``long`` 25 de noviembre de 2026, ``weekday`` Lunes 25 (en: Monday 25).

    ISO strings (as kept in drafts and JSON snapshots) are accepted too.
    """
    if value is None or value == "":
        return "—"
    if isinstance(value, str):
        value = date.fromisoformat(value[:10])
    if isinstance(value, datetime):
        value = _local(value).date()
    if style == "long":
        return format_date(value, format="long")
    if style == "weekday":
        text = format_skeleton("EEEEd", value, locale=get_locale())
        return text[:1].upper() + text[1:]
    skeleton = {"day": "dM", "medium": "MMMd"}.get(style, "yMd")
    return format_skeleton(skeleton, value, locale=get_locale())


def local_date(moment: datetime, user: Any) -> date:
    """The calendar day of ``moment`` in ``user``'s time zone (Madrid when unknown)."""
    aware = moment if moment.tzinfo else moment.replace(tzinfo=ZoneInfo("UTC"))
    try:
        zone = ZoneInfo(getattr(user, "timezone", None) or DEFAULT_ZONE)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo(DEFAULT_ZONE)
    return aware.astimezone(zone).date()


def _local(moment: datetime) -> datetime:
    """An aware datetime in the reader's time zone (Madrid when unknown).

    Events are stored in UTC; a session at 00:30 in Madrid belongs to that day,
    not to the evening before.
    """
    if moment.tzinfo is None:
        return moment
    zone = DEFAULT_ZONE
    if has_request_context() and current_user.is_authenticated:
        zone = current_user.timezone or DEFAULT_ZONE
    try:
        return moment.astimezone(ZoneInfo(zone))
    except (ZoneInfoNotFoundError, ValueError):
        return moment.astimezone(ZoneInfo(DEFAULT_ZONE))


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


def tempo(code: str | None) -> str:
    """``2-0-1-0`` in words: ``Baja en 2 s y sube en 1 s``.

    The four figures are seconds lowering, paused at the bottom, lifting and
    paused at the top. A malformed code is shown as it came, never hidden.
    """
    if not code:
        return ""
    try:
        down, bottom, up, _top = (int(part) for part in code.split("-"))
    except ValueError:
        return code
    if bottom:
        return gettext(
            "Baja en %(down)s s, para %(pause)s s abajo y sube en %(up)s s",
            down=down,
            pause=bottom,
            up=up,
        )
    return gettext("Baja en %(down)s s y sube en %(up)s s", down=down, up=up)


def money(amount: Any, currency: str = "EUR") -> str:
    """``7,99 €`` in Spanish, ``€7.99`` in English; whole amounts without ``,00``."""
    if amount is None:
        return "—"
    value = float(amount)
    if value % 1:
        return format_currency(value, currency.upper())
    spanish = str(get_locale() or "es").startswith("es")
    pattern = "#,##0\u00a0\u00a4" if spanish else "\u00a4#,##0"
    return format_currency(value, currency.upper(), format=pattern, currency_digits=False)


def register(app: Flask) -> None:
    """Expose the helpers as Jinja filters."""
    app.add_template_filter(num, "num")
    app.add_template_filter(money, "money")
    app.add_template_filter(signed, "signed")
    app.add_template_filter(kg, "kg")
    app.add_template_filter(duration, "duration")
    app.add_template_filter(fdate, "fdate")
    app.add_template_filter(tempo, "tempo")
    app.add_template_global(days_from_now, "days_from_now")
