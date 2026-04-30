"""FastAPI application entry point for the Glucotracker backend."""

from fastapi import FastAPI
from sqlalchemy import text

from glucotracker.api.openapi import build_openapi
from glucotracker.api.routers import (
    admin_router,
    autocomplete_router,
    dashboard_router,
    database_router,
    glucose_router,
    meals_router,
    nightscout_router,
    nutrients_router,
    patterns_router,
    photos_router,
    products_router,
    reports_router,
)
from glucotracker.api.schemas import HealthResponse
from glucotracker.config import get_settings
from glucotracker.infra.db.session import get_engine

app = FastAPI(
    title="Glucotracker API",
    summary="Informational food diary API.",
    version="0.1.0",
)
app.include_router(admin_router)
app.include_router(autocomplete_router)
app.include_router(dashboard_router)
app.include_router(database_router)
app.include_router(glucose_router)
app.include_router(meals_router)
app.include_router(nightscout_router)
app.include_router(nutrients_router)
app.include_router(patterns_router)
app.include_router(photos_router)
app.include_router(products_router)
app.include_router(reports_router)
app.openapi = lambda: build_openapi(app)


@app.get(
    "/health",
    tags=["system"],
    response_model=HealthResponse,
    operation_id="getHealth",
)
async def health() -> HealthResponse:
    """Return service health for local and container checks."""
    db_status = "ok"
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        db_status = "unavailable"

    return HealthResponse(
        status="ok",
        version=get_settings().app_version,
        db=db_status,
    )
