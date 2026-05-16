"""Domain types for authentication and authorization."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class UserRole(StrEnum):
    """Supported application roles."""

    gluco = "gluco"
    food = "food"


@dataclass(frozen=True)
class Credentials:
    """Username/password credentials submitted by a client."""

    username: str
    password: str


@dataclass(frozen=True)
class IssuedTokens:
    """Access and refresh tokens issued for an authenticated user."""

    access: str
    refresh: str
    access_expires_at: datetime
    refresh_expires_at: datetime


@dataclass(frozen=True)
class CurrentUser:
    """Authenticated user identity carried through request handling."""

    id: UUID
    role: UserRole


@dataclass(frozen=True)
class CurrentUserDetail(CurrentUser):
    """Detailed authenticated user data returned by /auth/me."""

    username: str
    created_at: datetime
    last_login_at: datetime | None = None
    feature_flags: dict[str, Any] = field(default_factory=dict)
