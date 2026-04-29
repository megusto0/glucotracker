"""Nightscout optional sync and read-only context endpoints."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from glucotracker.api.dependencies import SessionDep, verify_token
from glucotracker.api.schemas import (
    NightscoutDayStatusResponse,
    NightscoutEventsResponse,
    NightscoutGlucoseEntryResponse,
    NightscoutImportRequest,
    NightscoutImportResponse,
    NightscoutInsulinEventResponse,
    NightscoutSettingsPatch,
    NightscoutSettingsResponse,
    NightscoutStatusResponse,
    NightscoutSyncResponse,
    NightscoutSyncTodayRequest,
    NightscoutSyncTodayResponse,
    NightscoutTestResponse,
    TimelineResponse,
)
from glucotracker.application.nightscout_context import (
    FoodEpisodeService,
    NightscoutContextImportService,
)
from glucotracker.application.nightscout_sync import (
    NightscoutSettingsService,
    NightscoutSyncService,
)
from glucotracker.infra.nightscout.client import (
    NightscoutClient,
    get_nightscout_client,
)

router = APIRouter(
    tags=["nightscout"],
    dependencies=[Depends(verify_token)],
)

NightscoutDep = Annotated[NightscoutClient | None, Depends(get_nightscout_client)]


@router.get(
    "/settings/nightscout",
    response_model=NightscoutSettingsResponse,
    operation_id="getNightscoutSettings",
)
def get_nightscout_settings(session: SessionDep) -> NightscoutSettingsResponse:
    """Return masked server-side Nightscout settings."""
    return NightscoutSettingsService(session).response()


@router.put(
    "/settings/nightscout",
    response_model=NightscoutSettingsResponse,
    operation_id="updateNightscoutSettings",
)
def update_nightscout_settings(
    payload: NightscoutSettingsPatch,
    session: SessionDep,
) -> NightscoutSettingsResponse:
    """Update server-side Nightscout settings. Secret is write-only."""
    return NightscoutSettingsService(session).update(payload)


@router.post(
    "/settings/nightscout/test",
    response_model=NightscoutTestResponse,
    operation_id="testNightscoutConnection",
)
async def test_nightscout_connection(
    session: SessionDep,
    client: NightscoutDep,
) -> NightscoutTestResponse:
    """Test Nightscout connection and persist masked status."""
    return await NightscoutSettingsService(session).test_connection(client)


@router.get(
    "/nightscout/status",
    response_model=NightscoutStatusResponse,
    operation_id="getNightscoutStatus",
)
async def get_nightscout_status(
    session: SessionDep,
    client: NightscoutDep,
) -> NightscoutStatusResponse:
    """Return optional Nightscout status without breaking local use."""
    return await NightscoutSyncService(session, client).status()


@router.post(
    "/meals/{meal_id}/sync_nightscout",
    response_model=NightscoutSyncResponse,
    operation_id="syncMealToNightscout",
)
async def sync_meal_to_nightscout(
    meal_id: UUID,
    session: SessionDep,
    client: NightscoutDep,
) -> NightscoutSyncResponse:
    """Sync an accepted meal as a diary-only Nightscout treatment."""
    return await NightscoutSyncService(session, client).sync_meal(meal_id)


@router.post(
    "/meals/{meal_id}/unsync_nightscout",
    response_model=NightscoutSyncResponse,
    operation_id="unsyncMealFromNightscout",
)
async def unsync_meal_from_nightscout(
    meal_id: UUID,
    session: SessionDep,
    client: NightscoutDep,
) -> NightscoutSyncResponse:
    """Delete a remote Nightscout treatment and clear local sync fields."""
    return await NightscoutSyncService(session, client).unsync_meal(meal_id)


@router.post(
    "/nightscout/sync/today",
    response_model=NightscoutSyncTodayResponse,
    operation_id="syncTodayToNightscout",
)
async def sync_today_to_nightscout(
    payload: NightscoutSyncTodayRequest,
    session: SessionDep,
    client: NightscoutDep,
) -> NightscoutSyncTodayResponse:
    """Manually send accepted unsynced meals for a selected day."""
    return await NightscoutSyncService(session, client).sync_today(
        payload.date,
        confirm=payload.confirm,
    )


@router.get(
    "/nightscout/day_status",
    response_model=NightscoutDayStatusResponse,
    operation_id="getNightscoutDayStatus",
)
async def get_nightscout_day_status(
    session: SessionDep,
    client: NightscoutDep,
    date: date_type,
) -> NightscoutDayStatusResponse:
    """Return Nightscout manual-sync counters for a selected day."""
    return await NightscoutSyncService(session, client).day_status(date)


@router.get(
    "/nightscout/glucose",
    response_model=list[NightscoutGlucoseEntryResponse],
    operation_id="getNightscoutGlucose",
)
async def get_nightscout_glucose(
    session: SessionDep,
    client: NightscoutDep,
    from_datetime: Annotated[datetime, Query(alias="from")],
    to_datetime: Annotated[datetime, Query(alias="to")],
) -> list[NightscoutGlucoseEntryResponse]:
    """Return read-only Nightscout glucose entries as gentle context."""
    return await NightscoutSyncService(session, client).glucose(
        from_datetime,
        to_datetime,
    )


@router.get(
    "/nightscout/insulin",
    response_model=list[NightscoutInsulinEventResponse],
    operation_id="getNightscoutInsulin",
)
async def get_nightscout_insulin(
    session: SessionDep,
    client: NightscoutDep,
    from_datetime: Annotated[datetime, Query(alias="from")],
    to_datetime: Annotated[datetime, Query(alias="to")],
) -> list[NightscoutInsulinEventResponse]:
    """Return read-only Nightscout insulin events without linking to dosing."""
    return await NightscoutSyncService(session, client).insulin(
        from_datetime,
        to_datetime,
    )


@router.get(
    "/nightscout/events",
    response_model=NightscoutEventsResponse,
    operation_id="getNightscoutEvents",
)
async def get_nightscout_events(
    session: SessionDep,
    client: NightscoutDep,
    from_datetime: Annotated[datetime, Query(alias="from")],
    to_datetime: Annotated[datetime, Query(alias="to")],
) -> NightscoutEventsResponse:
    """Return combined read-only Nightscout glucose and insulin context events."""
    return await NightscoutSyncService(session, client).events(
        from_datetime,
        to_datetime,
    )


@router.post(
    "/nightscout/import",
    response_model=NightscoutImportResponse,
    operation_id="importNightscoutContext",
)
async def import_nightscout_context(
    payload: NightscoutImportRequest,
    session: SessionDep,
    client: NightscoutDep,
) -> NightscoutImportResponse:
    """Fetch Nightscout glucose/insulin context and cache it locally."""
    settings = NightscoutSettingsService(session)
    row = settings.get_or_create()
    effective_client = settings.client(client)
    return await NightscoutContextImportService(session, effective_client).import_range(
        payload.from_datetime,
        payload.to_datetime,
        sync_glucose=payload.sync_glucose and row.sync_glucose,
        import_insulin_events=payload.import_insulin_events
        and row.import_insulin_events,
    )


@router.get(
    "/timeline",
    response_model=TimelineResponse,
    operation_id="getTimeline",
)
def get_timeline(
    session: SessionDep,
    from_datetime: Annotated[datetime, Query(alias="from")],
    to_datetime: Annotated[datetime, Query(alias="to")],
) -> TimelineResponse:
    """Return backend-owned food episodes with local Nightscout context."""
    return FoodEpisodeService(session).timeline(from_datetime, to_datetime)
