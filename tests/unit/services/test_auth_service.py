"""Password hashing, registration, authentication and reset tokens."""

from __future__ import annotations

import functools
import time

import pytest
from argon2 import PasswordHasher
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import TimestampSigner, URLSafeTimedSerializer
from sqlalchemy import func, select

from app.models import User
from app.services import auth


def test_hash_and_verify_round_trip(app: Flask) -> None:
    with app.app_context():
        hashed = auth.hash_password("correct horse battery")
        assert hashed.startswith("$argon2id$")
        assert auth.verify_password(hashed, "correct horse battery") is True
        assert auth.verify_password(hashed, "wrong") is False
        assert auth.verify_password("not-a-hash", "whatever") is False


def test_password_policy_codes(app: Flask) -> None:
    with app.app_context():
        assert auth.password_problems("short", "a@b.com") == ["min_length:10"]
        assert "equals_email" in auth.password_problems("ana@example.com", "ana@example.com")
        assert "too_common" in auth.password_problems("1234567890")
        assert auth.password_problems("a long enough password", "a@b.com") == []


def test_register_creates_a_user_with_consent(database: SQLAlchemy) -> None:
    user = auth.register_user("  Ana@Example.com ", "una contraseña larga", "Ana")
    assert user.id is not None
    assert user.email == "ana@example.com"
    assert user.consent_accepted_at is not None
    assert user.password_hash.startswith("$argon2id$")
    with pytest.raises(auth.EmailTakenError):
        auth.register_user("ana@example.com", "otra contraseña larga", "Otra")
    with pytest.raises(auth.WeakPasswordError) as excinfo:
        auth.register_user("nueva@example.com", "corta", "Nueva")
    assert excinfo.value.problems == ["min_length:10"]


def test_authenticate_paths(database: SQLAlchemy) -> None:
    user = auth.register_user("ana@example.com", "una contraseña larga", "Ana")
    assert user.last_login_at is None
    logged = auth.authenticate("ANA@example.com", "una contraseña larga")
    assert logged is user
    assert logged.last_login_at is not None
    with pytest.raises(auth.InvalidCredentialsError):
        auth.authenticate("ana@example.com", "wrong password here")
    with pytest.raises(auth.InvalidCredentialsError):
        auth.authenticate("nobody@example.com", "una contraseña larga")
    user.is_active = False
    database.session.commit()
    with pytest.raises(auth.InactiveAccountError):
        auth.authenticate("ana@example.com", "una contraseña larga")
    user.is_active = True
    user.soft_delete()
    database.session.commit()
    with pytest.raises(auth.InactiveAccountError):
        auth.authenticate("ana@example.com", "una contraseña larga")


def test_authenticate_rehashes_when_parameters_change(
    database: SQLAlchemy, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = auth.register_user("ana@example.com", "una contraseña larga", "Ana")
    before = user.password_hash

    class RehashEverything(PasswordHasher):
        def check_needs_rehash(self, _hash: str) -> bool:
            return True

    monkeypatch.setattr(auth, "hasher", RehashEverything())
    auth.authenticate("ana@example.com", "una contraseña larga")
    assert user.password_hash != before
    assert auth.verify_password(user.password_hash, "una contraseña larga")


def test_load_user_only_returns_usable_accounts(database: SQLAlchemy) -> None:
    user = auth.register_user("ana@example.com", "una contraseña larga", "Ana")
    assert auth.load_user(str(user.id)) is user
    assert auth.load_user("abc") is None
    assert auth.load_user("999") is None
    user.is_active = False
    database.session.commit()
    assert auth.load_user(str(user.id)) is None


def test_reset_token_round_trip_and_invalidation(database: SQLAlchemy) -> None:
    user = auth.register_user("ana@example.com", "una contraseña larga", "Ana")
    token = auth.issue_reset_token(user)
    assert auth.verify_reset_token(token) is user
    with pytest.raises(auth.InvalidTokenError, match="invalid"):
        auth.verify_reset_token(token + "x")
    auth.reset_password(user, "otra contraseña larga")
    assert auth.verify_password(user.password_hash, "otra contraseña larga")
    with pytest.raises(auth.InvalidTokenError, match="stale"):
        auth.verify_reset_token(token)
    with pytest.raises(auth.WeakPasswordError):
        auth.reset_password(user, "corta")


def test_reset_token_expires(database: SQLAlchemy, monkeypatch: pytest.MonkeyPatch) -> None:
    user = auth.register_user("ana@example.com", "una contraseña larga", "Ana")

    class OldSigner(TimestampSigner):
        def get_timestamp(self) -> int:
            return int(time.time()) - 7200

    monkeypatch.setattr(
        auth, "URLSafeTimedSerializer", functools.partial(URLSafeTimedSerializer, signer=OldSigner)
    )
    token = auth.issue_reset_token(user)
    monkeypatch.setattr(auth, "URLSafeTimedSerializer", URLSafeTimedSerializer)
    with pytest.raises(auth.InvalidTokenError, match="expired"):
        auth.verify_reset_token(token)


def test_reset_token_for_deactivated_user_is_rejected(database: SQLAlchemy) -> None:
    user = auth.register_user("ana@example.com", "una contraseña larga", "Ana")
    token = auth.issue_reset_token(user)
    user.is_active = False
    database.session.commit()
    with pytest.raises(auth.InvalidTokenError):
        auth.verify_reset_token(token)


def test_register_handles_a_concurrent_duplicate(
    database: SQLAlchemy, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth.register_user("ana@example.com", "una contraseña larga", "Ana")
    monkeypatch.setattr(auth, "find_by_email", lambda _email: None)  # simulate the race
    with pytest.raises(auth.EmailTakenError):
        auth.register_user("ana@example.com", "otra contraseña larga", "Otra")
    total = database.session.execute(select(func.count()).select_from(User)).scalar_one()
    assert total == 1
