"""Password hashing (Argon2) and signed tokens (JWT, HS256) for the admin API."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

TokenKind = Literal["access", "refresh"]
ROLES: tuple[str, ...] = ("admin", "verifier")
MIN_SECRET_BYTES = 32
MIN_PASSWORD_LENGTH = 12
ALGORITHM = "HS256"
ISSUER = "app-reduc"

_hasher = PasswordHasher()
#: Verified when the email is unknown so both outcomes of a login take the same time.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


class AuthNotConfiguredError(Exception):
    """The signing secret is missing or too short; tokens must not be issued or accepted."""


class InvalidTokenError(Exception):
    """The token is malformed, expired, of the wrong kind or signed with another key."""


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    role: str
    kind: TokenKind
    expires_at: datetime
    #: Must match `app_user.token_version`; a password or role change invalidates older tokens.
    version: int


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres")
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-shape check: an unknown user still costs one Argon2 verification."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def _require_secret(secret: str) -> str:
    if len(secret.encode()) < MIN_SECRET_BYTES:
        raise AuthNotConfiguredError("REDUC_JWT_SECRET must be at least 32 bytes long")
    return secret


def create_token(
    secret: str,
    user_id: uuid.UUID,
    role: str,
    kind: TokenKind,
    lifetime: timedelta,
    now: datetime | None = None,
    version: int = 0,
) -> str:
    issued = now or datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "typ": kind,
        "ver": version,
        "iss": ISSUER,
        "iat": issued,
        "exp": issued + lifetime,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, _require_secret(secret), algorithm=ALGORITHM)


def decode_token(secret: str, token: str, kind: TokenKind) -> TokenClaims:
    """Validate signature, expiry, issuer and kind. A refresh token never works as an access token."""
    try:
        payload = jwt.decode(
            token,
            _require_secret(secret),
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "typ", "role", "iss", "ver"]},
        )
        if payload["typ"] != kind or payload["role"] not in ROLES:
            raise InvalidTokenError("wrong token kind")
        return TokenClaims(
            user_id=uuid.UUID(str(payload["sub"])),
            role=str(payload["role"]),
            kind=kind,
            expires_at=datetime.fromtimestamp(int(payload["exp"]), UTC),
            version=int(payload["ver"]),
        )
    except (jwt.PyJWTError, ValueError, KeyError, TypeError) as error:
        raise InvalidTokenError(str(error)) from error
