"""Authentication endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field

from glucotracker.api.dependencies import CurrentUserDep, SessionDep
from glucotracker.api.dependencies.feature import features_for_role
from glucotracker.api.errors import raise_unauthorized
from glucotracker.application.auth_service import AuthService, AuthServiceError
from glucotracker.domain.auth import (
    Credentials,
    CurrentUserDetail,
    IssuedTokens,
    UserRole,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """Username/password login payload."""

    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    """Refresh-token rotation payload."""

    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    """Refresh-token revocation payload."""

    refresh_token: str = Field(min_length=1)


class IssuedTokensResponse(BaseModel):
    """Issued access and refresh token response."""

    access: str
    refresh: str
    access_expires_at: datetime
    refresh_expires_at: datetime


class CurrentUserDetailResponse(BaseModel):
    """Authenticated user details."""

    id: UUID
    username: str
    role: UserRole
    created_at: datetime
    last_login_at: datetime | None = None
    features: list[str] = Field(default_factory=list)
    feature_flags: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


def _tokens_response(tokens: IssuedTokens) -> IssuedTokensResponse:
    return IssuedTokensResponse(
        access=tokens.access,
        refresh=tokens.refresh,
        access_expires_at=tokens.access_expires_at,
        refresh_expires_at=tokens.refresh_expires_at,
    )


def _current_user_response(detail: CurrentUserDetail) -> CurrentUserDetailResponse:
    return CurrentUserDetailResponse(
        id=detail.id,
        username=detail.username,
        role=detail.role,
        created_at=detail.created_at,
        last_login_at=detail.last_login_at,
        features=sorted(features_for_role(detail.role)),
        feature_flags=detail.feature_flags,
    )


@router.post(
    "/login",
    response_model=IssuedTokensResponse,
    operation_id="login",
)
def login(payload: LoginRequest, session: SessionDep) -> IssuedTokensResponse:
    """Authenticate a user and issue access/refresh tokens."""
    try:
        tokens = AuthService(session).login(
            Credentials(username=payload.username, password=payload.password)
        )
    except AuthServiceError:
        raise_unauthorized()
    return _tokens_response(tokens)


@router.post(
    "/refresh",
    response_model=IssuedTokensResponse,
    operation_id="refreshAuthToken",
)
def refresh(payload: RefreshRequest, session: SessionDep) -> IssuedTokensResponse:
    """Rotate a refresh token and return a fresh token pair."""
    try:
        tokens = AuthService(session).refresh(payload.refresh_token)
    except AuthServiceError:
        raise_unauthorized()
    return _tokens_response(tokens)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="logout",
)
def logout(payload: LogoutRequest, session: SessionDep) -> None:
    """Revoke a refresh token."""
    AuthService(session).logout(payload.refresh_token)


@router.get(
    "/me",
    response_model=CurrentUserDetailResponse,
    operation_id="getAuthMe",
)
def me(current_user: CurrentUserDep, session: SessionDep) -> CurrentUserDetailResponse:
    """Return the authenticated user."""
    try:
        detail = AuthService(session).me(current_user.id)
    except AuthServiceError:
        raise_unauthorized()
    return _current_user_response(detail)
