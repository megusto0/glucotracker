"""OpenAPI helpers for generated client compatibility."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

SCOPED_PATH_PREFIXES: tuple[str, ...] = (
    "/meals",
    "/meal_items",
    "/photos",
    "/patterns",
    "/glucose",
    "/fingersticks",
    "/sensors",
    "/settings/nightscout",
    "/nightscout",
    "/timeline",
    "/dashboard",
    "/profile",
    "/activity",
    "/reports",
    "/admin",
    "/database",
    "/autocomplete",
    "/products",
)

PUBLIC_PATHS: set[str] = {
    "/auth/login",
    "/auth/refresh",
    "/health",
}

GLUCOSE_FEATURE_PATH_PREFIXES: tuple[str, ...] = (
    "/glucose",
    "/fingersticks",
    "/sensors",
    "/timeline/insulin-links",
    "/reports/endocrinologist",
)

NIGHTSCOUT_FEATURE_PATH_PREFIXES: tuple[str, ...] = (
    "/settings/nightscout",
    "/nightscout",
    "/meals/{meal_id}/sync_nightscout",
    "/meals/{meal_id}/unsync_nightscout",
)

ROLE_VARIANT_PATHS: set[str] = {
    "/dashboard/today",
    "/timeline",
}


def _is_scoped_path(path: str) -> bool:
    return any(
        path == prefix or path.startswith(prefix + "/")
        for prefix in SCOPED_PATH_PREFIXES
    )


def _matches(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in prefixes)


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

    components: dict = schema.setdefault("components", {})
    security_schemes: dict = components.setdefault("securitySchemes", {})
    security_schemes["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }

    paths: dict = schema.get("paths", {})
    for path, methods in paths.items():
        for _method, operation in methods.items():
            if not isinstance(operation, dict):
                continue
            if path not in PUBLIC_PATHS:
                operation["security"] = [{"BearerAuth": []}]
            if _is_scoped_path(path):
                operation["x-glucotracker-scoped"] = True
            if _matches(path, GLUCOSE_FEATURE_PATH_PREFIXES):
                operation["x-glucotracker-required-feature"] = "glucose"
                operation["x-glucotracker-required-role"] = "gluco"
            if _matches(path, NIGHTSCOUT_FEATURE_PATH_PREFIXES):
                operation["x-glucotracker-required-feature"] = "nightscout"
                operation["x-glucotracker-required-role"] = "gluco"
            if path in ROLE_VARIANT_PATHS:
                operation["x-glucotracker-role-variant"] = True
                operation["x-glucotracker-food-omits"] = ["glucose", "nightscout"]

    app.openapi_schema = schema
    return schema
