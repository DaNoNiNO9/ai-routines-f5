"""Authentication service: passwords, sessions and password-reset tokens.

- Passwords are hashed with argon2id (``argon2-cffi`` defaults follow the
  OWASP recommendation) and re-hashed transparently when the parameters change.
- ``authenticate`` runs a dummy verification when the email is unknown so the
  response time does not reveal whether an account exists.
- Reset tokens are signed and time-limited (``itsdangerous``) and embed a
  fragment of the current password hash, so changing the password invalidates
  every token issued before.
"""

from __future__ import annotations

import logging

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import User
from app.models.base import utcnow

logger = logging.getLogger(__name__)

hasher = PasswordHasher()
RESET_SALT = "password-reset"
HASH_FRAGMENT_LENGTH = 12
COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "contraseña",
        "contrasena",
        "1234567890",
        "12345678910",
        "qwertyuiop",
        "abcdefghij",
    }
)
# Computed once so unknown emails cost the same as a real verification.
DUMMY_HASH = hasher.hash("dummy-password-for-constant-time")


class AuthError(Exception):
    """Base class for authentication failures the UI knows how to explain."""


class EmailTakenError(AuthError):
    """The email already has an account."""


class WeakPasswordError(AuthError):
    """The password does not meet the policy; ``problems`` lists the codes."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__(", ".join(problems))
        self.problems = problems


class InvalidCredentialsError(AuthError):
    """Unknown email or wrong password (never say which)."""


class InactiveAccountError(AuthError):
    """The account exists but is deactivated or deleted."""


class InvalidTokenError(AuthError):
    """The reset token is malformed, expired or already used."""


def password_problems(password: str, email: str = "") -> list[str]:
    """Policy violations as stable codes (empty list means the password is acceptable)."""
    minimum = int(current_app.config["PASSWORD_MIN_LENGTH"])
    problems: list[str] = []
    if len(password) < minimum:
        problems.append(f"min_length:{minimum}")
    if email and password.strip().lower() == email.strip().lower():
        problems.append("equals_email")
    if password.strip().lower() in COMMON_PASSWORDS:
        problems.append("too_common")
    return problems


def hash_password(password: str) -> str:
    """argon2id hash of ``password``."""
    return hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Whether ``password`` matches ``password_hash`` (never raises)."""
    try:
        return hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def find_by_email(email: str) -> User | None:
    """Look up a user by (normalised) email."""
    return db.session.scalar(select(User).where(User.email == email.strip().lower()))


def register_user(
    email: str, password: str, display_name: str, health_consent: bool = False
) -> User:
    """Create an account, recording consent now (and the health-data consent, if given).

    Raises:
        WeakPasswordError: If the password violates the policy.
        EmailTakenError: If the email is already registered (also under a race).
    """
    problems = password_problems(password, email)
    if problems:
        raise WeakPasswordError(problems)
    if find_by_email(email) is not None:
        raise EmailTakenError(email)
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name.strip(),
        consent_accepted_at=utcnow(),
    )
    if health_consent:
        from app.services.privacy import CONSENT_VERSION

        user.health_consent_at = utcnow()
        user.health_consent_version = CONSENT_VERSION
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        logger.warning("Registration race for an existing email")
        raise EmailTakenError(email) from exc
    logger.info("User %s registered", user.id)
    return user


def authenticate(email: str, password: str) -> User:
    """Return the user for valid credentials.

    Raises:
        InvalidCredentialsError: Unknown email or wrong password.
        InactiveAccountError: Deactivated or soft-deleted account.
    """
    user = find_by_email(email)
    if user is None:
        verify_password(DUMMY_HASH, password)
        raise InvalidCredentialsError
    if not verify_password(user.password_hash, password):
        logger.info("Failed login for user %s", user.id)
        raise InvalidCredentialsError
    if not user.is_active or user.deleted_at is not None:
        raise InactiveAccountError
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = utcnow()
    db.session.commit()
    logger.info("User %s logged in", user.id)
    return user


def load_user(user_id: str) -> User | None:
    """Flask-Login user loader: only active, non-deleted accounts get a session."""
    try:
        identifier = int(user_id)
    except (TypeError, ValueError):
        return None
    user = db.session.get(User, identifier)
    if user is None or not user.is_active or user.deleted_at is not None:
        return None
    return user


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=RESET_SALT)


def issue_reset_token(user: User) -> str:
    """Signed, time-limited token bound to the current password hash."""
    payload = {"uid": user.id, "v": user.password_hash[-HASH_FRAGMENT_LENGTH:]}
    return _serializer().dumps(payload)


def verify_reset_token(token: str) -> User:
    """Return the user a reset token belongs to.

    Raises:
        InvalidTokenError: If the token is malformed, expired, for an unusable
            account, or issued before the last password change.
    """
    max_age = int(current_app.config["PASSWORD_RESET_MAX_AGE"])
    try:
        payload = _serializer().loads(token, max_age=max_age)
    except SignatureExpired as exc:
        raise InvalidTokenError("expired") from exc
    except BadSignature as exc:
        raise InvalidTokenError("invalid") from exc
    user = load_user(str(payload.get("uid", "")))
    if user is None or payload.get("v") != user.password_hash[-HASH_FRAGMENT_LENGTH:]:
        raise InvalidTokenError("stale")
    return user


def change_password(user: User, current_password: str, new_password: str) -> None:
    """Replace the password after checking the current one.

    Raises:
        InvalidCredentialsError: If the current password is wrong.
        WeakPasswordError: If the new one violates the policy.
    """
    if not verify_password(user.password_hash, current_password):
        logger.info("Failed password change for user %s", user.id)
        raise InvalidCredentialsError
    reset_password(user, new_password)


def change_email(user: User, current_password: str, new_email: str) -> None:
    """Move the account to another email address.

    Raises:
        InvalidCredentialsError: If the password is wrong.
        EmailTakenError: If someone else already uses that address.
    """
    if not verify_password(user.password_hash, current_password):
        logger.info("Failed email change for user %s", user.id)
        raise InvalidCredentialsError
    normalised = new_email.strip().lower()
    existing = find_by_email(normalised)
    if existing is not None and existing.id != user.id:
        raise EmailTakenError(normalised)
    user.email = normalised
    user.email_verified_at = None
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        logger.warning("Email change race for an existing address")
        raise EmailTakenError(normalised) from exc
    logger.info("User %s changed their email", user.id)


def delete_account(user: User) -> None:
    """Erase the account and everything hanging from it (RGPD, artículo 17).

    This is a real delete, not a flag: the cascades take profiles, plans,
    routines, sessions, sets and every log with them.
    """
    from app.models.privacy import ERASURE_ACCOUNT
    from app.services.hevy import purge_pending
    from app.services.privacy import record_erasure

    user_id = user.id
    db.session.delete(user)
    record_erasure(user_id, ERASURE_ACCOUNT)
    db.session.commit()
    purge_pending(user_id)  # un CSV de Hevy a medio importar
    logger.info("Account %s deleted at the owner's request", user_id)


def reset_password(user: User, new_password: str) -> None:
    """Replace the password (invalidating outstanding tokens).

    Raises:
        WeakPasswordError: If the new password violates the policy.
    """
    problems = password_problems(new_password, user.email)
    if problems:
        raise WeakPasswordError(problems)
    user.password_hash = hash_password(new_password)
    db.session.commit()
    logger.info("Password reset for user %s", user.id)
