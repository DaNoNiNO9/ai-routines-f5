"""Names the engine generates and the database keeps, shown in the reader's language.

Routines, their days and the meals of a plan are stored with the name they got
when they were generated («Torso A», «Desayuno», «Torso / pierna · 4 días»).
They are data, but the person did not write them: an English reader should see
«Upper A», «Breakfast» and «Upper / lower · 4 days». Names that are not ours
(written by hand, or from a future generator) come back untouched.
"""

from __future__ import annotations

import re
from typing import Any

from flask import Flask, has_request_context
from flask_babel import force_locale, lazy_pgettext, ngettext
from flask_babel import lazy_gettext as _l

from app.labels import SPLIT_TYPE

# Días de las rutinas (app/engine/routines/splits.py), sin la letra final.
DAY_NAMES: dict[str, Any] = {
    "Cuerpo completo": _l("Cuerpo completo"),
    "Torso": _l("Torso"),
    "Pierna": _l("Pierna"),
    "Empuje": _l("Empuje"),
    "Tirón": _l("Tirón"),
    "Pecho y espalda": _l("Pecho y espalda"),
    "Hombros y brazos": _l("Hombros y brazos"),
}

# Comidas del plan (app/engine/meals.py), sin el número final.
MEAL_NAMES: dict[str, Any] = {
    "Desayuno": lazy_pgettext("nombre de comida", "Desayuno"),
    "Media mañana": lazy_pgettext("nombre de comida", "Media mañana"),
    "Comida": lazy_pgettext("nombre de comida", "Comida"),
    "Merienda": lazy_pgettext("nombre de comida", "Merienda"),
    "Cena": lazy_pgettext("nombre de comida", "Cena"),
    "Recena": lazy_pgettext("nombre de comida", "Recena"),
    "Comida extra": lazy_pgettext("nombre de comida", "Comida extra"),
}

_SUFFIX = re.compile(r"^(?P<base>.+?)(?P<suffix> (?:[A-Z]|\d+))?$")
_ROUTINE = re.compile(r"^(?P<split>.+) · (?P<days>\d+) (?:días|days?)$")


def _split_label(text: str) -> Any | None:
    """The split label whatever language it was stored in (it was rendered at creation)."""
    for label in SPLIT_TYPE.values():
        if text == label._args[0]:
            return label
        with force_locale("en"):
            if text == str(label):
                return label
    return None


def stored_name(text: str | None) -> str:
    """Translate a generated name; leave anything else as it is."""
    if not text or not has_request_context():
        return text or ""
    routine = _ROUTINE.match(text)
    if routine:
        label = _split_label(routine.group("split"))
        if label is not None:
            days = int(routine.group("days"))
            # Fuera del f-string: pybabel no mira dentro de ellos.
            count = ngettext("%(num)s día", "%(num)s días", days)
            return f"{label} · {count}"
    parts = _SUFFIX.match(text)
    if parts:
        base, suffix = parts.group("base"), parts.group("suffix") or ""
        known = DAY_NAMES.get(base) or MEAL_NAMES.get(base)
        if known is not None:
            return f"{known}{suffix}"
    return text


def register(app: Flask) -> None:
    """Expose ``stored_name`` as the ``stored`` Jinja filter."""
    app.add_template_filter(stored_name, "stored")
