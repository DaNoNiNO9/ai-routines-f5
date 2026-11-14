"""Account forms. Anything that changes credentials or deletes data asks for the password."""

from __future__ import annotations

from zoneinfo import available_timezones

from flask import current_app
from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import PasswordField, SelectField, StringField
from wtforms.validators import DataRequired, Email, Length, ValidationError

from app.fields import strip_text
from app.models.user import DISPLAY_NAME_MAX_LENGTH, EMAIL_MAX_LENGTH

PASSWORD_MAX_LENGTH = 128
DELETE_WORD = "BORRAR"
# Shown in the datalist; any IANA zone is accepted.
COMMON_TIMEZONES = (
    "Europe/Madrid",
    "Atlantic/Canary",
    "Europe/London",
    "Europe/Lisbon",
    "Europe/Paris",
    "America/Mexico_City",
    "America/Bogota",
    "America/Argentina/Buenos_Aires",
    "America/Santiago",
    "America/New_York",
    "UTC",
)


class ProfileForm(FlaskForm):
    """Name, language and time zone: nothing here needs the password."""

    display_name = StringField(
        _l("Nombre"),
        filters=[strip_text],
        validators=[DataRequired(), Length(min=2, max=DISPLAY_NAME_MAX_LENGTH)],
    )
    locale = SelectField(_l("Idioma"), validators=[DataRequired()])
    timezone = StringField(_l("Zona horaria"), validators=[DataRequired(), Length(max=64)])

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.locale.choices = list(current_app.config["LANGUAGES"].items())

    def validate_timezone(self, field: StringField) -> None:
        """Only real IANA zones: the whole diary is dated with this."""
        if field.data not in available_timezones():
            raise ValidationError(_l("Esa zona horaria no existe. Ejemplo: Europe/Madrid."))


class EmailForm(FlaskForm):
    """Changing the email is changing how you sign in, so it asks for the password."""

    email = StringField(
        _l("Correo nuevo"), validators=[DataRequired(), Email(), Length(max=EMAIL_MAX_LENGTH)]
    )
    current_password = PasswordField(
        _l("Tu contraseña"), validators=[DataRequired(), Length(max=PASSWORD_MAX_LENGTH)]
    )


class PasswordForm(FlaskForm):
    """Current password plus the new one, twice."""

    current_password = PasswordField(
        _l("Contraseña actual"), validators=[DataRequired(), Length(max=PASSWORD_MAX_LENGTH)]
    )
    password = PasswordField(
        _l("Contraseña nueva"), validators=[DataRequired(), Length(max=PASSWORD_MAX_LENGTH)]
    )
    password_confirm = PasswordField(
        _l("Repite la contraseña nueva"),
        validators=[DataRequired(), Length(max=PASSWORD_MAX_LENGTH)],
    )

    def validate_password_confirm(self, field: PasswordField) -> None:
        """Typed twice on purpose."""
        if field.data != self.password.data:
            raise ValidationError(_l("Las contraseñas no coinciden."))


class DeleteAccountForm(FlaskForm):
    """Password and the word, because this cannot be undone."""

    current_password = PasswordField(
        _l("Tu contraseña"), validators=[DataRequired(), Length(max=PASSWORD_MAX_LENGTH)]
    )
    confirmation = StringField(
        _l("Escribe %(word)s para confirmar", word=DELETE_WORD), validators=[DataRequired()]
    )

    def validate_confirmation(self, field: StringField) -> None:
        """A typo must not delete an account."""
        if (field.data or "").strip() != DELETE_WORD:
            raise ValidationError(_l("Escribe %(word)s exactamente.", word=DELETE_WORD))
