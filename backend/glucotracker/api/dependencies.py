"""FastAPI dependencies for auth, settings, and request context."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from glucotracker.config import Settings, get_settings
from glucotracker.infra.db.session import get_session

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
AuthDep = Annotated[None, Depends(verify_token)]
