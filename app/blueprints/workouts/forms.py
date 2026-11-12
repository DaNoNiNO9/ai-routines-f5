"""Forms of the live session: one set, a substitution, the closing questions."""

from __future__ import annotations

from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import IntegerField, RadioField, SelectField, TextAreaField
from wtforms.validators import InputRequired, Length, NumberRange, Optional, ValidationError

from app.engine.enums import SetType
from app.fields import DecimalField

FATIGUE_LABELS = {
    1: _l("1 · Fresco"),
    2: _l("2 · Bien"),
    3: _l("3 · Normal"),
    4: _l("4 · Cansado"),
    5: _l("5 · Agotado"),
}


class SetForm(FlaskForm):
    """One set: which prescription, which index, and what was done."""

    routine_exercise_id = IntegerField(validators=[InputRequired()])
    set_index = IntegerField(validators=[InputRequired(), NumberRange(min=1, max=20)])
    weight_kg = DecimalField(_l("kg"), validators=[InputRequired(), NumberRange(min=0, max=1000)])
    reps = IntegerField(_l("reps"), validators=[InputRequired(), NumberRange(min=0, max=200)])
    rir = IntegerField(_l("RIR"), validators=[Optional(), NumberRange(min=0, max=10)])
    set_type = SelectField(
        choices=[
            (SetType.WORKING.value, _l("efectiva")),
            (SetType.WARMUP.value, _l("calentamiento")),
        ],
        default=SetType.WORKING.value,
    )


class SubstituteForm(FlaskForm):
    """Swap the prescribed exercise for one of its alternatives (empty restores it)."""

    routine_exercise_id = IntegerField(validators=[InputRequired()])
    exercise_id = IntegerField(validators=[Optional()])


class FinishForm(FlaskForm):
    """How the session felt."""

    perceived_fatigue = RadioField(
        _l("¿Cómo has acabado?"),
        choices=list(FATIGUE_LABELS.items()),
        coerce=int,
        validate_choice=False,
    )
    notes = TextAreaField(_l("Notas (opcional)"), validators=[Optional(), Length(max=500)])

    def validate_perceived_fatigue(self, field: RadioField) -> None:
        """Optional, but 1-5 when given."""
        if field.data is not None and field.data not in FATIGUE_LABELS:
            raise ValidationError(_l("Elige un valor entre 1 y 5."))
