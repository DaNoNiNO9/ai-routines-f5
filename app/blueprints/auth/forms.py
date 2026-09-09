"""Registration, login and password-reset forms (server-side validation)."""

from __future__ import annotations

from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import BooleanField, EmailField, PasswordField, StringField
from wtforms.validators import DataRequired, Email, EqualTo, Length

from app.models.user import DISPLAY_NAME_MAX_LENGTH, EMAIL_MAX_LENGTH

PASSWORD_MAX_LENGTH = 128


class RegisterForm(FlaskForm):
    """New account: email, name, password twice and explicit consent."""

    email = EmailField(
        _l("Correo electrónico"),
        validators=[DataRequired(), Email(), Length(max=EMAIL_MAX_LENGTH)],
    )
    display_name = StringField(
        _l("Nombre"), validators=[DataRequired(), Length(min=2, max=DISPLAY_NAME_MAX_LENGTH)]
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
    consent = BooleanField(
        _l(
            "Entiendo que Forja es una herramienta orientativa y no sustituye el consejo "
            "de un profesional sanitario."
        ),
        validators=[DataRequired(message=_l("Es necesario aceptar el aviso."))],
    )


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
