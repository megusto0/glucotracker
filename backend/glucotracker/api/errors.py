"""Shared API error helpers."""

from __future__ import annotations

from typing import NoReturn

from fastapi import Request, status
from fastapi.responses import JSONResponse


class UnauthorizedError(Exception):
    """Raised when a request lacks valid user authentication."""


def raise_unauthorized() -> NoReturn:
    """Raise a 401 response with the auth error shape used by clients."""
    raise UnauthorizedError


async def unauthorized_exception_handler(
    _: Request,
    __: UnauthorizedError,
) -> JSONResponse:
    """Render user-auth failures without leaking token details."""
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"code": "unauthorized"},
    )
