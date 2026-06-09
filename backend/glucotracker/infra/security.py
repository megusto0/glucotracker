"""Password hashing and token issuance helpers."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from sqlalchemy.orm import Session

from glucotracker.config import get_settings
from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.models import RefreshToken

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=3650)
JWT_ALGORITHM = "HS256"

_password_hasher = PasswordHasher()


class AccessTokenError(Exception):
    """Raised when an access token cannot be trusted."""


class AccessTokenExpired(AccessTokenError):
    """Raised when an access token is structurally valid but expired."""


def utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(UTC)


def hash_password(plain: str) -> str:
    """Hash a plaintext password with argon2id."""
    return _password_hasher.hash(plain)


def verify_password(plain: str, password_hash: str) -> bool:
    """Return whether a plaintext password matches an argon2 hash."""
    try:
        return _password_hasher.verify(password_hash, plain)
    except (VerifyMismatchError, VerificationError):
        return False


def _jwt_secret() -> str:
    return get_settings().validated_jwt_secret()


def issue_access_token(
    user_id: UUID,
    role: UserRole | str,
    *,
    issued_at: datetime | None = None,
    expires_delta: timedelta = ACCESS_TOKEN_TTL,
) -> str:
    """Return a short-lived signed JWT for an authenticated user."""
    now = issued_at or utc_now()
    role_value = role.value if isinstance(role, UserRole) else str(role)
    payload = {
        "sub": str(user_id),
        "role": role_value,
        "type": "access",
        "iat": now,
        "exp": now + expires_delta,
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def verify_access_token(token: str) -> dict[str, Any]:
    """Return verified JWT claims or raise an access-token error."""
    try:
        claims = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise AccessTokenExpired from exc
    except jwt.PyJWTError as exc:
        raise AccessTokenError from exc

    if (
        claims.get("type") != "access"
        or not claims.get("sub")
        or not claims.get("role")
    ):
        raise AccessTokenError
    return claims


def refresh_token_hash(token: str) -> str:
    """Return the server-side SHA-256 hash of a refresh token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_refresh_token(
    session: Session,
    user_id: UUID,
    *,
    issued_at: datetime | None = None,
    expires_delta: timedelta = REFRESH_TOKEN_TTL,
    device_label: str | None = None,
) -> tuple[str, datetime]:
    """Return a long opaque refresh token and store only its SHA-256 hash."""
    now = issued_at or utc_now()
    token = secrets.token_urlsafe(64)
    expires_at = now + expires_delta
    session.add(
        RefreshToken(
            user_id=user_id,
            token_hash=refresh_token_hash(token),
            issued_at=now,
            expires_at=expires_at,
            device_label=device_label,
        )
    )
    return token, expires_at
