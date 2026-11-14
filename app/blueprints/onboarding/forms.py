"""One form per questionnaire step; ranges mirror the engine and the CHECK constraints."""

from __future__ import annotations

from datetime import date
from typing import Any

from flask_babel import lazy_gettext as _l
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    IntegerField,
    RadioField,
    SelectField,
    SelectMultipleField,
    StringField,
    widgets,
)
from wtforms.validators import InputRequired, Length, NumberRange, Optional, ValidationError

from app import labels
from app.engine.enums import InjuryArea, Sex
from app.engine.routines.types import MAX_PRIORITY_MUSCLES
from app.fields import DecimalField

MIN_AGE = 18
MAX_AGE = 110


def age_on(birth: date, today: date) -> int:
    """Whole years old on ``today``."""
    years = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        years -= 1
    return years


def check_adult(birth: date | None, today: date) -> None:
    """Adults only and a plausible age (the engine repeats the first check)."""
    if birth is None:
        return
    age = age_on(birth, today)
    if age < MIN_AGE:
        raise ValidationError(_l("Alza es solo para mayores de 18 años."))
    if age > MAX_AGE:
        raise ValidationError(_l("Revisa la fecha de nacimiento."))


SESSION_MINUTE_OPTIONS = (30, 45, 60, 75, 90, 120)
MEAL_OPTIONS = (2, 3, 4, 5, 6)
INJURY_FIELDS = {area: f"injury_{area.value}" for area in InjuryArea}


class MultiCheckboxField(SelectMultipleField):
    """A list of checkboxes."""

    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


def _jsonable(value: Any) -> Any:
    """Field data as JSON: dates become ISO strings, tuples become lists."""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return value


class StepForm(FlaskForm):
    """Base with the JSON round trip used by the draft."""

    def to_data(self) -> dict[str, Any]:
        """Answers as plain JSON (dates as ISO strings)."""
        return {
            name: _jsonable(field.data)
            for name, field in self._fields.items()
            if name != "csrf_token"
        }


class BodyForm(StepForm):
    """Block A: anthropometrics."""

    sex = RadioField(
        _l("Sexo biológico"), choices=labels.choices(labels.SEX), validators=[InputRequired()]
    )
    birth_date = DateField(_l("Fecha de nacimiento"), validators=[InputRequired()])
    height_cm = DecimalField(
        _l("Altura (cm)"), validators=[InputRequired(), NumberRange(min=100, max=250)]
    )
    weight_kg = DecimalField(
        _l("Peso actual (kg)"), validators=[InputRequired(), NumberRange(min=25, max=350)]
    )
    neck_cm = DecimalField(_l("Cuello (cm)"), validators=[Optional(), NumberRange(min=20, max=80)])
    waist_cm = DecimalField(
        _l("Cintura (cm)"), validators=[Optional(), NumberRange(min=40, max=250)]
    )
    hip_cm = DecimalField(_l("Cadera (cm)"), validators=[Optional(), NumberRange(min=50, max=250)])
    body_fat_pct = DecimalField(
        _l("Porcentaje de grasa corporal"), validators=[Optional(), NumberRange(min=2, max=70)]
    )
    body_fat_method = SelectField(
        _l("¿Cómo lo has medido?"), choices=labels.choices(labels.BODY_FAT_DECLARED), default="none"
    )

    def validate_birth_date(self, field: DateField) -> None:
        """Adults only (the engine repeats the check) and a plausible age."""
        check_adult(field.data, current_user.today())

    def validate_body_fat_method(self, field: SelectField) -> None:
        """A declared percentage needs its method (it decides how much to trust it)."""
        if self.body_fat_pct.data is not None and field.data == "none":
            raise ValidationError(_l("Indica cómo has medido el porcentaje de grasa."))

    def validate(self, extra_validators: Any = None) -> bool:
        """Form-level check: the Navy formula for women needs the hip as well.

        (An inline ``validate_hip_cm`` would never run: ``Optional`` stops the
        chain when the field is empty.)
        """
        ok = super().validate(extra_validators)
        if (
            self.sex.data == Sex.FEMALE.value
            and self.waist_cm.data is not None
            and self.neck_cm.data is not None
            and self.hip_cm.data is None
        ):
            self.hip_cm.errors = [
                *self.hip_cm.errors,
                _l("Para estimar la grasa en mujeres hace falta también la cadera."),
            ]
            ok = False
        return ok


class ActivityForm(StepForm):
    """Block B: activity and lifestyle."""

    job_activity = RadioField(
        _l("Actividad en tu trabajo o día a día"),
        choices=labels.choices(labels.JOB_ACTIVITY),
        validators=[InputRequired()],
    )
    daily_steps = IntegerField(
        _l("Pasos diarios (si los conoces)"),
        validators=[Optional(), NumberRange(min=0, max=60000)],
    )
    sleep_hours = DecimalField(
        _l("Horas de sueño por noche"), validators=[InputRequired(), NumberRange(min=3, max=16)]
    )
    stress_level = RadioField(
        _l("Nivel de estrés habitual"),
        choices=labels.choices(labels.STRESS_LEVEL),
        coerce=int,
        validators=[InputRequired()],
    )
    other_activity_type = StringField(
        _l("Otro deporte o actividad (opcional)"), validators=[Optional(), Length(max=80)]
    )
    other_activity_sessions_per_week = IntegerField(
        _l("Sesiones por semana"),
        default=0,
        validators=[InputRequired(), NumberRange(min=0, max=14)],
    )
    other_activity_minutes = IntegerField(
        _l("Minutos por sesión"),
        default=0,
        validators=[InputRequired(), NumberRange(min=0, max=300)],
    )
    other_activity_intensity = SelectField(
        _l("Intensidad"),
        choices=[("", _l("—")), *labels.choices(labels.ACTIVITY_INTENSITY)],
        default="",
    )

    def validate_other_activity_intensity(self, field: SelectField) -> None:
        """Sessions imply minutes and an intensity (they drive the EAT estimate)."""
        sessions = self.other_activity_sessions_per_week.data or 0
        if sessions > 0:
            if not self.other_activity_minutes.data:
                raise ValidationError(_l("Indica cuánto dura cada sesión."))
            if not field.data:
                raise ValidationError(_l("Indica la intensidad de esa actividad."))


class TrainingForm(StepForm):
    """Block C (part 1): experience, schedule and place."""

    training_experience = RadioField(
        _l("Experiencia con pesas"),
        choices=labels.choices(labels.TRAINING_EXPERIENCE),
        validators=[InputRequired()],
    )
    training_days_per_week = SelectField(
        _l("Días de entrenamiento por semana"),
        choices=[(n, str(n)) for n in range(1, 7)],
        coerce=int,
        default=3,
        validators=[InputRequired()],
    )
    session_minutes = SelectField(
        _l("Minutos por sesión"),
        choices=[(n, f"{n} min") for n in SESSION_MINUTE_OPTIONS],
        coerce=int,
        default=60,
        validators=[InputRequired()],
    )
    training_location = RadioField(
        _l("¿Dónde entrenas?"),
        choices=labels.choices(labels.TRAINING_LOCATION),
        validators=[InputRequired()],
    )
    training_time = RadioField(
        _l("¿A qué hora sueles entrenar?"),
        choices=labels.choices(labels.TRAINING_TIME),
        default="none",
        validators=[InputRequired()],
    )


class EquipmentForm(StepForm):
    """Block C (part 2): equipment, priorities, injuries and exercise preferences."""

    equipment = MultiCheckboxField(_l("Material disponible"), choices=[])
    priority_muscles = MultiCheckboxField(
        _l("¿Hay algún músculo que quieras trabajar más? (opcional, máximo dos)"),
        choices=labels.choices(labels.PRIORITY_MUSCLES),
    )
    # Solo abre la parte de lesiones: no se guarda, las zonas hablan por sí solas.
    has_injuries = BooleanField(_l("Tengo alguna molestia o lesión"))
    # Los ejercicios que gustan o no se marcan desde la rutina, viéndolos, no aquí
    # de memoria contra un catálogo de 190 nombres.

    def validate_equipment(self, field: MultiCheckboxField) -> None:
        """At least one item (bodyweight counts)."""
        if not field.data:
            raise ValidationError(_l("Marca al menos una opción; el peso corporal cuenta."))

    def validate_priority_muscles(self, field: MultiCheckboxField) -> None:
        """The volume model can favour at most two muscles without starving the rest."""
        if field.data and len(field.data) > MAX_PRIORITY_MUSCLES:
            raise ValidationError(_l("Elige como mucho dos músculos."))

    def injuries(self) -> dict[str, str]:
        """Declared injuries as ``{area: severity}`` (only the ones that are not 'none')."""
        result: dict[str, str] = {}
        for area, name in INJURY_FIELDS.items():
            value = self._fields[name].data
            if value and value != "none":
                result[area.value] = value
        return result

    def to_data(self) -> dict[str, Any]:
        """Answers plus the injuries dictionary (the per-area selects are not stored)."""
        data = {
            k: v
            for k, v in super().to_data().items()
            if not k.startswith("injury_") and k != "has_injuries"
        }
        data["injuries"] = self.injuries()
        return data


for _area, _name in INJURY_FIELDS.items():
    setattr(
        EquipmentForm,
        _name,
        SelectField(
            labels.INJURY_AREA[_area],
            choices=[("none", _l("Sin molestias")), *labels.choices(labels.SEVERITY)],
            default="none",
        ),
    )


class GoalForm(StepForm):
    """Block D: goal and pace."""

    goal = RadioField(
        _l("Objetivo principal"), choices=labels.choices(labels.GOAL), validators=[InputRequired()]
    )
    aggressiveness = RadioField(
        _l("Ritmo"),
        choices=labels.choices(labels.AGGRESSIVENESS),
        default="moderate",
        validators=[InputRequired()],
    )
    target_weight_kg = DecimalField(
        _l("Peso objetivo (kg, opcional)"), validators=[Optional(), NumberRange(min=25, max=350)]
    )
    target_date = DateField(_l("Fecha objetivo (opcional)"), validators=[Optional()])

    def validate_target_date(self, field: DateField) -> None:
        """A date in the past cannot be a goal."""
        if field.data is not None and field.data <= current_user.today():
            raise ValidationError(_l("La fecha objetivo tiene que ser futura."))


class NutritionForm(StepForm):
    """Block E: nutrition habits.

    Only what the engine uses today. Food dislikes, allergies, budget and cooking
    time belong to the meal planner and will be asked there, in context; the
    profile columns stay so earlier answers are not lost.
    """

    meals_per_day = SelectField(
        _l("Comidas al día"),
        choices=[(n, str(n)) for n in MEAL_OPTIONS],
        coerce=int,
        default=4,
        validators=[InputRequired()],
    )
    diet_pattern = SelectField(
        _l("Tipo de alimentación"),
        choices=labels.choices(labels.DIET_PATTERN),
        default="omnivore",
        validators=[InputRequired()],
    )
    wants_carb_cycling = BooleanField(
        _l("Quiero más hidratos los días de entreno y menos los de descanso")
    )
    alcohol_drinks_per_week = IntegerField(
        _l("Bebidas alcohólicas por semana"),
        default=0,
        validators=[InputRequired(), NumberRange(min=0, max=50)],
    )


class HealthForm(StepForm):
    """Safety flags and free notes."""

    is_pregnant_or_breastfeeding = BooleanField(_l("Estoy embarazada o en periodo de lactancia"))
    has_eating_disorder_history = BooleanField(
        _l("Tengo o he tenido un trastorno de la conducta alimentaria")
    )


def split_list(text: str | None) -> list[str]:
    """``"a, b;c"`` → ``["a", "b", "c"]`` (trimmed, no empties, no duplicates)."""
    if not text:
        return []
    items: list[str] = []
    for chunk in text.replace(";", ",").replace("\n", ",").split(","):
        item = chunk.strip()
        if item and item.lower() not in {existing.lower() for existing in items}:
            items.append(item)
    return items


STEP_FORMS: dict[int, type[StepForm]] = {
    1: BodyForm,
    2: ActivityForm,
    3: TrainingForm,
    4: EquipmentForm,
    5: GoalForm,
    6: NutritionForm,
    7: HealthForm,
}


class QuickForm(StepForm):
    """The plan in a minute: only what the plan cannot do without.

    The fields and their checks are the same objects as in the full
    questionnaire (adults only, plausible ranges, the two health questions that
    block a plan), so both roads apply the same rules. Everything else takes a
    prudent default (``onboarding.quick_answers``) and is refined later.
    """

    sex = BodyForm.sex
    birth_date = BodyForm.birth_date
    height_cm = BodyForm.height_cm
    weight_kg = BodyForm.weight_kg
    goal = GoalForm.goal
    target_weight_kg = GoalForm.target_weight_kg
    training_experience = TrainingForm.training_experience
    training_days_per_week = TrainingForm.training_days_per_week
    session_minutes = TrainingForm.session_minutes
    training_location = TrainingForm.training_location
    has_injuries = BooleanField(_l("Tengo alguna molestia o lesión"))
    is_pregnant_or_breastfeeding = HealthForm.is_pregnant_or_breastfeeding
    has_eating_disorder_history = HealthForm.has_eating_disorder_history

    validate_birth_date = BodyForm.validate_birth_date
