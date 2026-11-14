"""Form fields shared by every blueprint."""

from __future__ import annotations

import re
from typing import Any

from flask_babel import format_decimal
from flask_babel import lazy_gettext as _l
from wtforms import FloatField

NUMBER = re.compile(r"[+-]?(\d+([.,]\d*)?|[.,]\d+)")


def strip_text(value: object) -> object:
    """Trim spaces before the length checks ("  B  " is one letter, not five)."""
    return value.strip() if isinstance(value, str) else value


class DecimalField(FloatField):
    """A decimal number written the way the person writes it.

    WTForms' ``FloatField`` renders a text input and only understands a dot, so
    "63,9" (how anyone in Spain writes it) was rejected with an English message,
    and the diary echoed "118.0" back. This field accepts a comma or a dot and
    shows the stored value in the reader's locale, without trailing zeros and
    without thousands separators (it goes back into an input).
    """

    invalid_message = _l("Escribe un número, por ejemplo 63,5.")

    def process_formdata(self, valuelist: list[Any]) -> None:
        """Parse "63,9", "63.9" or " 63 " into a float."""
        if not valuelist:
            return
        raw = str(valuelist[0]).strip().replace(" ", "")
        # Solo cifras con coma o punto: float() también acepta «6_4», «1e3» o «nan».
        if not NUMBER.fullmatch(raw):
            self.data = None
            raise ValueError(str(self.invalid_message))
        try:
            self.data = float(raw.replace(",", "."))
        except ValueError:
            self.data = None
            raise ValueError(str(self.invalid_message)) from None

    def _value(self) -> str:
        if self.raw_data:
            return str(self.raw_data[0])
        if self.data is None:
            return ""
        return format_decimal(self.data, format="0.##")
