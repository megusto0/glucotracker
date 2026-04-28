"""OpenAPI helpers for generated client compatibility."""

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def build_openapi(app: FastAPI) -> dict:
    """Build a stable OpenAPI schema for generated clients."""
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        summary=app.summary,
        routes=app.routes,
    )
    app.openapi_schema = schema
    return app.openapi_schema
