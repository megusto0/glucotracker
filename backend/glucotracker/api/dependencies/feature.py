"""Role-based feature gating dependency."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from glucotracker.api.dependencies import get_current_user
from glucotracker.domain.auth import CurrentUser, UserRole

ROLE_FEATURES: dict[UserRole, set[str]] = {
    UserRole.gluco: {"glucose", "nightscout", "insulin"},
    UserRole.food: set(),
}


def features_for_role(role: UserRole) -> set[str]:
    """Return the resolved feature set for a given role."""
    return ROLE_FEATURES.get(role, set())


def require_feature(name: str) -> Callable[..., None]:
    """Return a FastAPI dependency that gates access to a named feature."""

    def _check(
        request: Request,
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> None:
        state_user = getattr(request.state, "current_user", current_user)
        if name not in ROLE_FEATURES.get(state_user.role, set()):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "feature_disabled", "feature": name},
            )

    return _check
