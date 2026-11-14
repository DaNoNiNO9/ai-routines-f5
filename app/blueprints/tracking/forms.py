"""Diary forms: weight, intake, activity and the weekly tape measures.

Ranges mirror the CHECK constraints of ``app/models/tracking.py``: the forms
say no in Spanish, the database says no in SQL, and neither trusts the other.
"""

from __future__ import annotations

from datetime import date, timedelta

from flask_babel import lazy_gettext as _l
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import DateField, IntegerField, SelectField, StringField
from wtforms.validators import InputRequired, Length, NumberRange, Optional, ValidationError
from wtforms.widgets import HiddenInput

from app import labels
from app.engine.enums import BodyFatMethod, CardioKind
from app.fields import DecimalField

CARDIO_CHOICES = [
    ("", _l("—")),
    (CardioKind.LISS.value, _l("Cardio suave")),
    (CardioKind.HIIT.value, _l("Intervalos")),
]


# Más atrás no sirve para la revisión y suele ser un error al teclear el año.
OLDEST_DAYS = 730


def check_diary_day(day: date | None) -> None:
    """A diary day has to have happened, within the last two years (the user's time zone)."""
    if day is None:
        return
    today = current_user.today()
    if day > today:
        raise ValidationError(_l("Ese día todavía no ha llegado."))
    if day < today - timedelta(days=OLDEST_DAYS):
        raise ValidationError(_l("Solo se pueden apuntar días de los dos últimos años."))


class DayForm(FlaskForm):
    """Base for the diary forms: they all act on one day, never on a future one."""

    day = DateField(_l("Día"), validators=[InputRequired()], widget=HiddenInput())

    def validate_day(self, field: DateField) -> None:
        """Only days that have happened, and not further back than two years."""
        check_diary_day(field.data)


class WeightForm(DayForm):
    """The morning weigh-in."""

    weight_kg = DecimalField(
        _l("Peso (kg)"), validators=[InputRequired(), NumberRange(min=25, max=350)]
    )
    notes = StringField(_l("Nota (opcional)"), validators=[Optional(), Length(max=200)])


class IntakeForm(DayForm):
    """What was actually eaten (decision D-07: one simple entry per day)."""

    calories = IntegerField(
        _l("Calorías"), validators=[InputRequired(), NumberRange(min=0, max=20000)]
    )
    protein_g = DecimalField(
        _l("Proteína (g)"), validators=[Optional(), NumberRange(min=0, max=1000)]
    )
    carbs_g = DecimalField(
        _l("Carbohidratos (g)"), validators=[Optional(), NumberRange(min=0, max=2000)]
    )
    fat_g = DecimalField(_l("Grasa (g)"), validators=[Optional(), NumberRange(min=0, max=1000)])
    adherence_pct = IntegerField(
        _l("Cuánto has seguido el plan (%)"), validators=[Optional(), NumberRange(min=0, max=100)]
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

    def validate(self, extra_validators: dict | None = None) -> bool:
        """Minutes and kind travel together, or neither does.

        This is a form-level check on purpose: ``Optional()`` stops the chain
        when a field is empty, so an inline validator would never see the case
        of a kind without minutes.
        """
        ok = super().validate(extra_validators)
        kind = self.cardio_kind.data
        minutes = self.cardio_minutes.data
        if minutes and not kind:
            self.cardio_kind.errors = [
                *self.cardio_kind.errors,
                _l("Indica qué tipo de cardio has hecho."),
            ]
            ok = False
        if kind and not minutes:
            self.cardio_minutes.errors = [
                *self.cardio_minutes.errors,
                _l("Indica cuántos minutos han sido."),
            ]
            ok = False
        return ok


class MeasurementForm(FlaskForm):
    """Weekly tape measures; the day is visible because they are not always taken today."""

    day = DateField(_l("Día"), validators=[InputRequired()])
    neck_cm = DecimalField(_l("Cuello (cm)"), validators=[Optional(), NumberRange(min=20, max=80)])
    waist_cm = DecimalField(
        _l("Cintura (cm)"), validators=[Optional(), NumberRange(min=40, max=250)]
    )
    hip_cm = DecimalField(_l("Cadera (cm)"), validators=[Optional(), NumberRange(min=50, max=250)])
    chest_cm = DecimalField(_l("Pecho (cm)"), validators=[Optional(), NumberRange(min=50, max=250)])
    arm_cm = DecimalField(_l("Brazo (cm)"), validators=[Optional(), NumberRange(min=15, max=90)])
    thigh_cm = DecimalField(_l("Muslo (cm)"), validators=[Optional(), NumberRange(min=25, max=120)])
    calf_cm = DecimalField(_l("Gemelo (cm)"), validators=[Optional(), NumberRange(min=15, max=90)])
    body_fat_pct = DecimalField(
        _l("Grasa corporal (%)"), validators=[Optional(), NumberRange(min=2, max=70)]
    )
    body_fat_method = SelectField(
        _l("Método"), choices=labels.choices(labels.BODY_FAT_DECLARED), default="none"
    )
    notes = StringField(_l("Nota (opcional)"), validators=[Optional(), Length(max=200)])

    def validate_day(self, field: DateField) -> None:
        """Only days that have happened, and not further back than two years."""
        check_diary_day(field.data)

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
