"""FastAPI application entry point for the Glucotracker backend."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from sqlalchemy import text

from glucotracker.api.errors import UnauthorizedError, unauthorized_exception_handler
from glucotracker.api.openapi import build_openapi
from glucotracker.api.routers import (
    activity_router,
    admin_router,
    auth_router,
    autocomplete_router,
    dashboard_router,
    database_router,
    glucose_router,
    goals_router,
    meals_router,
    nightscout_router,
    nutrients_router,
    patterns_router,
    photos_router,
    products_router,
    reports_router,
    schedule_router,
    stats_router,
)
from glucotracker.api.schemas import HealthResponse
from glucotracker.application.nightscout_background import NightscoutBackgroundImporter
from glucotracker.application.postprandial.worker import PostprandialSweeper
from glucotracker.config import get_settings
from glucotracker.infra.db.session import get_engine, get_session_factory
from glucotracker.workers.anchor_recompute import AnchorRecomputeWorker


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Reject startup when JWT signing is not configured safely."""
    settings = get_settings()
    settings.validated_jwt_secret()
    background_task: asyncio.Task[None] | None = None
    anchor_task: asyncio.Task[None] | None = None
    sweeper_task: asyncio.Task[None] | None = None
    if settings.nightscout_background_import_enabled and not app.dependency_overrides:
        background_task = asyncio.create_task(
            NightscoutBackgroundImporter(get_session_factory()).run_forever()
        )
    if not app.dependency_overrides:
        anchor_task = asyncio.create_task(
            AnchorRecomputeWorker().run_forever()
        )
        sweeper_task = asyncio.create_task(
            PostprandialSweeper().run_forever()
        )
    try:
        yield
    finally:
        if background_task is not None:
            background_task.cancel()
            with suppress(asyncio.CancelledError):
                await background_task
        if anchor_task is not None:
            anchor_task.cancel()
            with suppress(asyncio.CancelledError):
                await anchor_task
        if sweeper_task is not None:
            sweeper_task.cancel()
            with suppress(asyncio.CancelledError):
                await sweeper_task


app = FastAPI(
    title="Glucotracker API",
    summary="Informational food diary API.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_exception_handler(UnauthorizedError, unauthorized_exception_handler)
app.include_router(admin_router)
app.include_router(activity_router)
app.include_router(auth_router)
app.include_router(autocomplete_router)
app.include_router(dashboard_router)
app.include_router(database_router)
app.include_router(glucose_router)
app.include_router(goals_router)
app.include_router(meals_router)
app.include_router(nightscout_router)
app.include_router(nutrients_router)
app.include_router(patterns_router)
app.include_router(photos_router)
app.include_router(products_router)
app.include_router(reports_router)
app.include_router(schedule_router)
app.include_router(stats_router)
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
