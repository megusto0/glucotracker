"""FastAPI dependencies for auth, settings, and request context."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.api.errors import raise_unauthorized
from glucotracker.config import Settings, get_settings
from glucotracker.domain.auth import CurrentUser, UserRole
from glucotracker.infra.db.models import User
from glucotracker.infra.db.session import get_read_session, get_session
from glucotracker.infra.security import AccessTokenError, verify_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def verify_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Verify the single configured bearer token."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )
    if settings.token is None or credentials.credentials != settings.token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token.",
        )


SessionDep = Annotated[Session, Depends(get_session)]
ReadSessionDep = Annotated[Session, Depends(get_read_session)]
AuthDep = Annotated[None, Depends(verify_token)]


def get_current_user(
    request: Request,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Verify the JWT bearer token and return the current user identity."""
    if authorization is None:
        raise_unauthorized()

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise_unauthorized()

    try:
        claims = verify_access_token(token)
        user_id = UUID(str(claims["sub"]))
        UserRole(str(claims["role"]))
    except (AccessTokenError, KeyError, TypeError, ValueError):
        raise_unauthorized()

    cached = getattr(request.state, "current_user", None)
    if isinstance(cached, CurrentUser) and cached.id == user_id:
        session.info["current_user_id"] = cached.id
        return cached

    cached_user = getattr(request.state, "current_user_row", None)
    if isinstance(cached_user, User) and cached_user.id == user_id:
        current_user = CurrentUser(id=cached_user.id, role=cached_user.role)
        request.state.current_user = current_user
        session.info["current_user_id"] = current_user.id
        return current_user

    user = session.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise_unauthorized()

    request.state.current_user_row = user
    current_user = CurrentUser(id=user.id, role=user.role)
    request.state.current_user = current_user
    session.info["current_user_id"] = user.id
    return current_user


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
