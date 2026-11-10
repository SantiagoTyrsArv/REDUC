"""Password hashing and token rules (T-23)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from reduc.core.security import (
    AuthNotConfiguredError,
    InvalidTokenError,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)

SECRET = "s" * 32
USER = uuid.UUID("11111111-1111-1111-1111-111111111111")


def test_passwords_are_hashed_with_argon2_and_verified() -> None:
    hashed = hash_password("correct horse battery")

    assert hashed.startswith("$argon2id$")
    assert verify_password("correct horse battery", hashed)
    assert not verify_password("wrong", hashed)
    # An unknown user (no hash) never verifies, and neither does a corrupted hash.
    assert not verify_password("anything", None)
    assert not verify_password("anything", "not-a-hash")
    with pytest.raises(ValueError, match="12 caracteres"):
        hash_password("short")


def test_token_round_trip_and_kinds_are_not_interchangeable() -> None:
    access = create_token(SECRET, USER, "verifier", "access", timedelta(minutes=15))
    refresh = create_token(SECRET, USER, "verifier", "refresh", timedelta(days=7))

    claims = decode_token(SECRET, access, "access")
    assert (claims.user_id, claims.role, claims.kind) == (USER, "verifier", "access")
    assert decode_token(SECRET, refresh, "refresh").kind == "refresh"
    with pytest.raises(InvalidTokenError):
        decode_token(SECRET, refresh, "access")
    with pytest.raises(InvalidTokenError):
        decode_token(SECRET, access, "refresh")


def test_expired_tampered_and_foreign_tokens_are_rejected() -> None:
    past = datetime.now(UTC) - timedelta(hours=1)
    expired = create_token(SECRET, USER, "admin", "access", timedelta(minutes=15), now=past)
    valid = create_token(SECRET, USER, "admin", "access", timedelta(minutes=15))

    for token in (expired, valid[:-2] + "xx", "garbage", create_token("x" * 32, USER, "admin", "access", timedelta(1))):
        with pytest.raises(InvalidTokenError):
            decode_token(SECRET, token, "access")
    # A role outside the known set is never trusted.
    with pytest.raises(InvalidTokenError):
        decode_token(SECRET, create_token(SECRET, USER, "root", "access", timedelta(minutes=1)), "access")


@pytest.mark.parametrize("secret", ["", "too-short"])
def test_missing_or_weak_secret_fails_closed(secret: str) -> None:
    with pytest.raises(AuthNotConfiguredError):
        create_token(secret, USER, "admin", "access", timedelta(minutes=1))
    with pytest.raises(AuthNotConfiguredError):
        decode_token(secret, "whatever", "access")
