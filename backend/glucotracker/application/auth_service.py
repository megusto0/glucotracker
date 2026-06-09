"""Application service for local user authentication."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from glucotracker.domain.auth import (
    Credentials,
    CurrentUserDetail,
    IssuedTokens,
)
from glucotracker.infra.db.models import RefreshToken, User
from glucotracker.infra.security import (
    ACCESS_TOKEN_TTL,
    REFRESH_TOKEN_TTL,
    issue_access_token,
    issue_refresh_token,
    refresh_token_hash,
    utc_now,
    verify_password,
)


class AuthServiceError(Exception):
    """Raised when an authentication operation must be rejected."""


def _as_aware_utc(value: datetime) -> datetime:
    """Normalize persisted datetimes that may round-trip from SQLite as naive."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class AuthService:
    """Authenticate users and manage refresh-token lifecycle."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def login(self, credentials: Credentials) -> IssuedTokens:
        """Authenticate username/password credentials and issue token pair."""
        username = credentials.username.strip()
        if not username:
            raise AuthServiceError

        user = self.session.scalar(select(User).where(User.username == username))
        if user is None:
            raise AuthServiceError
        if not verify_password(credentials.password, user.password_hash):
            raise AuthServiceError

        now = utc_now()
        user.last_login_at = now
        tokens = self._issue_tokens(user, issued_at=now)
        self.session.commit()
        return tokens

    def refresh(self, refresh_token: str) -> IssuedTokens:
        """Issue a fresh access token for a valid long-lived refresh token."""
        token_hash = refresh_token_hash(refresh_token)
        row = self.session.scalar(
            select(RefreshToken)
            .options(joinedload(RefreshToken.user))
            .where(RefreshToken.token_hash == token_hash)
        )
        now = utc_now()
        if (
            row is None
            or row.revoked_at is not None
            or _as_aware_utc(row.expires_at) <= now
            or row.user is None
        ):
            raise AuthServiceError

        row.expires_at = now + REFRESH_TOKEN_TTL
        access = issue_access_token(row.user.id, row.user.role, issued_at=now)
        tokens = IssuedTokens(
            access=access,
            refresh=refresh_token,
            access_expires_at=now + ACCESS_TOKEN_TTL,
            refresh_expires_at=row.expires_at,
        )
        self.session.commit()
        return tokens

    def logout(self, refresh_token: str) -> None:
        """Revoke a refresh token if it exists."""
        token_hash = refresh_token_hash(refresh_token)
        row = self.session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        if row is not None and row.revoked_at is None:
            row.revoked_at = utc_now()
        self.session.commit()

    def me(self, user_id: UUID) -> CurrentUserDetail:
        """Return current user details."""
        user = self.session.get(User, user_id)
        if user is None:
            raise AuthServiceError
        return CurrentUserDetail(
            id=user.id,
            role=user.role,
            username=user.username,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            feature_flags=dict(user.feature_flags or {}),
        )

    def _issue_tokens(self, user: User, *, issued_at: datetime) -> IssuedTokens:
        access = issue_access_token(user.id, user.role, issued_at=issued_at)
        refresh, refresh_expires_at = issue_refresh_token(
            self.session,
            user.id,
            issued_at=issued_at,
        )
        return IssuedTokens(
            access=access,
            refresh=refresh,
            access_expires_at=issued_at + ACCESS_TOKEN_TTL,
            refresh_expires_at=refresh_expires_at,
        )
