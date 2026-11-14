"""Registration, login and password-reset forms (server-side validation)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import BooleanField, DateField, EmailField, PasswordField, StringField
from wtforms.validators import DataRequired, Email, EqualTo, InputRequired, Length

from app.fields import strip_text
from app.models.user import DISPLAY_NAME_MAX_LENGTH, EMAIL_MAX_LENGTH

PASSWORD_MAX_LENGTH = 128


class RegisterForm(FlaskForm):
    """New account: email, name, password twice and explicit consent."""

    email = EmailField(
        _l("Correo electrónico"),
        validators=[DataRequired(), Email(), Length(max=EMAIL_MAX_LENGTH)],
    )
    display_name = StringField(
        _l("Nombre"),
        filters=[strip_text],
        validators=[DataRequired(), Length(min=2, max=DISPLAY_NAME_MAX_LENGTH)],
    )
    password = PasswordField(
        _l("Contraseña"), validators=[DataRequired(), Length(max=PASSWORD_MAX_LENGTH)]
    )
    password_confirm = PasswordField(
        _l("Repite la contraseña"),
        validators=[
            DataRequired(),
            EqualTo("password", message=_l("Las contraseñas no coinciden.")),
        ],
    )
    birth_date = DateField(
        _l("Fecha de nacimiento"),
        validators=[InputRequired(message=_l("Indica tu fecha de nacimiento."))],
    )
    consent = BooleanField(
        _l(
            "Entiendo que Alza es una herramienta orientativa y no sustituye el consejo "
            "de un profesional sanitario."
        ),
        validators=[DataRequired(message=_l("Es necesario aceptar el aviso."))],
    )
    health_consent = BooleanField(
        _l(
            "Doy mi consentimiento explícito para que Alza trate mis datos de salud (peso, "
            "medidas, sueño, comida, entrenos y molestias) y, si lo indico, mi tipo de dieta, "
            "solo para calcular y ajustar mi plan. Puedo retirarlo cuando quiera."
        ),
        validators=[
            DataRequired(message=_l("Sin este consentimiento no podemos calcular tu plan."))
        ],
    )

    def validate_birth_date(self, field: DateField) -> None:
        """No accounts for minors: the date decides, as in the questionnaire."""
        from app.blueprints.onboarding.forms import check_adult

        # Aún no hay cuenta ni zona horaria: el día de hoy en Madrid.
        check_adult(field.data, datetime.now(ZoneInfo("Europe/Madrid")).date())


class LoginForm(FlaskForm):
    """Email and password, with an optional persistent session."""

    email = EmailField(_l("Correo electrónico"), validators=[DataRequired(), Email()])
    password = PasswordField(
        _l("Contraseña"), validators=[DataRequired(), Length(max=PASSWORD_MAX_LENGTH)]
    )
    remember = BooleanField(_l("Mantener la sesión iniciada"))


class ForgotPasswordForm(FlaskForm):
    """Request a reset link."""

    email = EmailField(_l("Correo electrónico"), validators=[DataRequired(), Email()])


class ResetPasswordForm(FlaskForm):
    """Choose a new password."""

    password = PasswordField(
        _l("Nueva contraseña"), validators=[DataRequired(), Length(max=PASSWORD_MAX_LENGTH)]
    )
    password_confirm = PasswordField(
        _l("Repite la contraseña"),
        validators=[
            DataRequired(),
            EqualTo("password", message=_l("Las contraseñas no coinciden.")),
        ],
    )
