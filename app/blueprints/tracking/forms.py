"""Diary forms: weight, intake, activity and the weekly tape measures.

Ranges mirror the CHECK constraints of ``app/models/tracking.py``: the forms
say no in Spanish, the database says no in SQL, and neither trusts the other.
"""

from __future__ import annotations

from datetime import date

from flask_babel import lazy_gettext as _l
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import DateField, FloatField, IntegerField, SelectField, StringField
from wtforms.validators import InputRequired, Length, NumberRange, Optional, ValidationError
from wtforms.widgets import HiddenInput

from app import labels
from app.engine.enums import BodyFatMethod, CardioKind

CARDIO_CHOICES = [
    ("", _l("—")),
    (CardioKind.LISS.value, _l("Cardio suave (LISS)")),
    (CardioKind.HIIT.value, _l("HIIT")),
]


class DayForm(FlaskForm):
    """Base for the diary forms: they all act on one day, never on a future one."""

    day = DateField(_l("Día"), validators=[InputRequired()], widget=HiddenInput())

    def validate_day(self, field: DateField) -> None:
        """Reject days that have not happened yet (in the user's time zone)."""
        if field.data is not None and field.data > current_user.today():
            raise ValidationError(_l("Ese día todavía no ha llegado."))


class WeightForm(DayForm):
    """The morning weigh-in."""

    weight_kg = FloatField(
        _l("Peso (kg)"), validators=[InputRequired(), NumberRange(min=25, max=350)]
    )
    notes = StringField(_l("Nota (opcional)"), validators=[Optional(), Length(max=200)])


class IntakeForm(DayForm):
    """What was actually eaten (decision D-07: one simple entry per day)."""

    calories = IntegerField(
        _l("Calorías"), validators=[InputRequired(), NumberRange(min=0, max=20000)]
    )
    protein_g = FloatField(
        _l("Proteína (g)"), validators=[Optional(), NumberRange(min=0, max=1000)]
    )
    carbs_g = FloatField(
        _l("Carbohidratos (g)"), validators=[Optional(), NumberRange(min=0, max=2000)]
    )
    fat_g = FloatField(_l("Grasa (g)"), validators=[Optional(), NumberRange(min=0, max=1000)])
    adherence_pct = IntegerField(
        _l("Adherencia (%)"), validators=[Optional(), NumberRange(min=0, max=100)]
    )
    notes = StringField(_l("Nota (opcional)"), validators=[Optional(), Length(max=200)])


class ActivityForm(DayForm):
    """Steps and cardio of the day."""

    steps = IntegerField(_l("Pasos"), validators=[Optional(), NumberRange(min=0, max=100000)])
    cardio_kind = SelectField(_l("Tipo de cardio"), choices=CARDIO_CHOICES, default="")
    cardio_minutes = IntegerField(
        _l("Minutos"), validators=[Optional(), NumberRange(min=0, max=600)]
    )
    notes = StringField(_l("Nota (opcional)"), validators=[Optional(), Length(max=200)])

    def validate_cardio_minutes(self, field: IntegerField) -> None:
        """Minutes and kind travel together, or neither does."""
        if field.data and not self.cardio_kind.data:
            raise ValidationError(_l("Indica qué tipo de cardio has hecho."))
        if self.cardio_kind.data and not field.data:
            raise ValidationError(_l("Indica cuántos minutos han sido."))


class MeasurementForm(FlaskForm):
    """Weekly tape measures; the day is visible because they are not always taken today."""

    day = DateField(_l("Día"), validators=[InputRequired()])
    neck_cm = FloatField(_l("Cuello (cm)"), validators=[Optional(), NumberRange(min=20, max=80)])
    waist_cm = FloatField(_l("Cintura (cm)"), validators=[Optional(), NumberRange(min=40, max=250)])
    hip_cm = FloatField(_l("Cadera (cm)"), validators=[Optional(), NumberRange(min=50, max=250)])
    chest_cm = FloatField(_l("Pecho (cm)"), validators=[Optional(), NumberRange(min=50, max=250)])
    arm_cm = FloatField(_l("Brazo (cm)"), validators=[Optional(), NumberRange(min=15, max=90)])
    thigh_cm = FloatField(_l("Muslo (cm)"), validators=[Optional(), NumberRange(min=25, max=120)])
    calf_cm = FloatField(_l("Gemelo (cm)"), validators=[Optional(), NumberRange(min=15, max=90)])
    body_fat_pct = FloatField(
        _l("Grasa corporal (%)"), validators=[Optional(), NumberRange(min=2, max=70)]
    )
    body_fat_method = SelectField(
        _l("Método"), choices=labels.choices(labels.BODY_FAT_DECLARED), default="none"
    )
    notes = StringField(_l("Nota (opcional)"), validators=[Optional(), Length(max=200)])

    def validate_day(self, field: DateField) -> None:
        """No measurements from the future."""
        if field.data is not None and field.data > current_user.today():
            raise ValidationError(_l("Ese día todavía no ha llegado."))

    def validate_body_fat_method(self, field: SelectField) -> None:
        """A declared percentage needs its method (it decides how much to trust it)."""
        if self.body_fat_pct.data is not None and field.data == BodyFatMethod.NONE.value:
            raise ValidationError(_l("Indica cómo has medido el porcentaje de grasa."))

    def validate(self, extra_validators: dict | None = None) -> bool:
        """At least one measurement, otherwise the row would be empty."""
        ok = super().validate(extra_validators)
        measures = (
            self.neck_cm.data,
            self.waist_cm.data,
            self.hip_cm.data,
            self.chest_cm.data,
            self.arm_cm.data,
            self.thigh_cm.data,
            self.calf_cm.data,
            self.body_fat_pct.data,
        )
        if all(value is None for value in measures):
            self.neck_cm.errors = [*self.neck_cm.errors, _l("Rellena al menos una medida.")]
            ok = False
        return ok


def today_or(value: date | None) -> date:
    """``value`` when given, today in the user's time zone otherwise."""
    return value or current_user.today()
