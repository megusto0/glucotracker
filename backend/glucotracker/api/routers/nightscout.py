"""Nightscout context plus owned manual-treatment synchronization endpoints."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from glucotracker.api.dependencies import CurrentUserDep, SessionDep
from glucotracker.api.dependencies.feature import require_feature
from glucotracker.api.schemas import (
    InsulinLinkDayPutRequest,
    InsulinLinkDayResponse,
    NightscoutDayStatusResponse,
    NightscoutEventsResponse,
    NightscoutGlucoseEntryResponse,
    NightscoutImportRequest,
    NightscoutImportResponse,
    NightscoutInsulinDeleteResponse,
    NightscoutInsulinEntryCreate,
    NightscoutInsulinEntryPatch,
    NightscoutInsulinEventResponse,
    NightscoutLatestReadingResponse,
    NightscoutSettingsPatch,
    NightscoutSettingsResponse,
    NightscoutStatusResponse,
    NightscoutSyncResponse,
    NightscoutSyncTodayRequest,
    NightscoutSyncTodayResponse,
    NightscoutTestResponse,
    TimelineFoodResponse,
    TimelineResponse,
)
from glucotracker.application.glucose_visibility import visible_glucose_filter
from glucotracker.application.insulin_links import InsulinLinkDayService
from glucotracker.application.nightscout_context import (
    FoodEpisodeService,
    NightscoutContextImportService,
)
from glucotracker.application.nightscout_sync import (
    NightscoutSettingsService,
    NightscoutSyncService,
)
from glucotracker.domain.auth import UserRole
from glucotracker.infra.nightscout.client import (
    NIGHTSCOUT_NOT_CONFIGURED,
    NightscoutClient,
    get_nightscout_client,
)

router = APIRouter(tags=["nightscout"])

NightscoutDep = Annotated[NightscoutClient | None, Depends(get_nightscout_client)]


@router.get(
    "/settings/nightscout",
    response_model=NightscoutSettingsResponse,
    operation_id="getNightscoutSettings",
    dependencies=[Depends(require_feature("nightscout"))],
)
def get_nightscout_settings(
    session: SessionDep,
    current_user: CurrentUserDep,
) -> NightscoutSettingsResponse:
    """Return masked server-side Nightscout settings."""
    return NightscoutSettingsService(session, current_user.id).response()


@router.put(
    "/settings/nightscout",
    response_model=NightscoutSettingsResponse,
    operation_id="updateNightscoutSettings",
    dependencies=[Depends(require_feature("nightscout"))],
)
def update_nightscout_settings(
    payload: NightscoutSettingsPatch,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> NightscoutSettingsResponse:
    """Update server-side Nightscout settings. Secret is write-only."""
    return NightscoutSettingsService(session, current_user.id).update(payload)


@router.post(
    "/settings/nightscout/test",
    response_model=NightscoutTestResponse,
    operation_id="testNightscoutConnection",
    dependencies=[Depends(require_feature("nightscout"))],
)
async def test_nightscout_connection(
    session: SessionDep,
    current_user: CurrentUserDep,
    client: NightscoutDep,
) -> NightscoutTestResponse:
    """Test Nightscout connection and persist masked status."""
    return await NightscoutSettingsService(session, current_user.id).test_connection(
        client
    )


@router.get(
    "/nightscout/status",
    response_model=NightscoutStatusResponse,
    operation_id="getNightscoutStatus",
    dependencies=[Depends(require_feature("nightscout"))],
)
async def get_nightscout_status(
    session: SessionDep,
    current_user: CurrentUserDep,
    client: NightscoutDep,
) -> NightscoutStatusResponse:
    """Return optional Nightscout status without breaking local use."""
    return await NightscoutSyncService(session, current_user.id, client).status()


@router.post(
    "/meals/{meal_id}/sync_nightscout",
    response_model=NightscoutSyncResponse,
    operation_id="syncMealToNightscout",
    dependencies=[Depends(require_feature("nightscout"))],
)
async def sync_meal_to_nightscout(
    meal_id: UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
    client: NightscoutDep,
) -> NightscoutSyncResponse:
    """Sync an accepted meal as a diary-only Nightscout treatment."""
    return await NightscoutSyncService(session, current_user.id, client).sync_meal(
        meal_id
    )


@router.post(
    "/meals/{meal_id}/unsync_nightscout",
    response_model=NightscoutSyncResponse,
    operation_id="unsyncMealFromNightscout",
    dependencies=[Depends(require_feature("nightscout"))],
)
async def unsync_meal_from_nightscout(
    meal_id: UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
    client: NightscoutDep,
) -> NightscoutSyncResponse:
    """Delete a remote Nightscout treatment and clear local sync fields."""
    return await NightscoutSyncService(session, current_user.id, client).unsync_meal(
        meal_id
    )


@router.post(
    "/nightscout/sync/today",
    response_model=NightscoutSyncTodayResponse,
    operation_id="syncTodayToNightscout",
    dependencies=[Depends(require_feature("nightscout"))],
)
async def sync_today_to_nightscout(
    payload: NightscoutSyncTodayRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
    client: NightscoutDep,
) -> NightscoutSyncTodayResponse:
    """Manually send accepted unsynced meals for a selected day."""
    return await NightscoutSyncService(session, current_user.id, client).sync_today(
        payload.date,
        confirm=payload.confirm,
    )


@router.get(
    "/nightscout/day_status",
    response_model=NightscoutDayStatusResponse,
    operation_id="getNightscoutDayStatus",
    dependencies=[Depends(require_feature("nightscout"))],
)
async def get_nightscout_day_status(
    session: SessionDep,
    current_user: CurrentUserDep,
    client: NightscoutDep,
    date: date_type,
) -> NightscoutDayStatusResponse:
    """Return Nightscout manual-sync counters for a selected day."""
    return await NightscoutSyncService(
        session,
        current_user.id,
        client,
    ).day_status(date)


@router.get(
    "/nightscout/glucose",
    response_model=list[NightscoutGlucoseEntryResponse],
    operation_id="getNightscoutGlucose",
    dependencies=[Depends(require_feature("nightscout"))],
)
async def get_nightscout_glucose(
    session: SessionDep,
    current_user: CurrentUserDep,
    client: NightscoutDep,
    from_datetime: Annotated[datetime, Query(alias="from")],
    to_datetime: Annotated[datetime, Query(alias="to")],
) -> list[NightscoutGlucoseEntryResponse]:
    """Return read-only Nightscout glucose entries as gentle context."""
    return await NightscoutSyncService(session, current_user.id, client).glucose(
        from_datetime,
        to_datetime,
    )


@router.get(
    "/nightscout/insulin",
    response_model=list[NightscoutInsulinEventResponse],
    operation_id="getNightscoutInsulin",
    dependencies=[Depends(require_feature("nightscout"))],
)
async def get_nightscout_insulin(
    session: SessionDep,
    current_user: CurrentUserDep,
    client: NightscoutDep,
    from_datetime: Annotated[datetime, Query(alias="from")],
    to_datetime: Annotated[datetime, Query(alias="to")],
) -> list[NightscoutInsulinEventResponse]:
    """Return read-only Nightscout insulin events without linking to dosing."""
    return await NightscoutSyncService(session, current_user.id, client).insulin(
        from_datetime,
        to_datetime,
    )


@router.post(
    "/nightscout/insulin",
    response_model=NightscoutInsulinEventResponse,
    operation_id="createNightscoutInsulin",
    dependencies=[Depends(require_feature("nightscout"))],
)
async def create_nightscout_insulin(
    payload: NightscoutInsulinEntryCreate,
    session: SessionDep,
    current_user: CurrentUserDep,
    client: NightscoutDep,
) -> NightscoutInsulinEventResponse:
    """Write a user-entered insulin amount to Nightscout."""
    return await NightscoutSyncService(
        session,
        current_user.id,
        client,
    ).create_insulin_entry(payload)


@router.patch(
    "/nightscout/insulin/{event_id}",
    response_model=NightscoutInsulinEventResponse,
    operation_id="updateNightscoutInsulin",
    dependencies=[Depends(require_feature("nightscout"))],
)
async def update_nightscout_insulin(
    event_id: UUID,
    payload: NightscoutInsulinEntryPatch,
    session: SessionDep,
    current_user: CurrentUserDep,
    client: NightscoutDep,
) -> NightscoutInsulinEventResponse:
    """Update an owned insulin treatment originally created by Glucotracker."""
    return await NightscoutSyncService(
        session,
        current_user.id,
        client,
    ).update_insulin_entry(event_id, payload)


@router.delete(
    "/nightscout/insulin/{event_id}",
    response_model=NightscoutInsulinDeleteResponse,
    operation_id="deleteNightscoutInsulin",
    dependencies=[Depends(require_feature("nightscout"))],
)
async def delete_nightscout_insulin(
    event_id: UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
    client: NightscoutDep,
) -> NightscoutInsulinDeleteResponse:
    """Delete an owned insulin treatment originally created by Glucotracker."""
    return await NightscoutSyncService(
        session,
        current_user.id,
        client,
    ).delete_insulin_entry(event_id)


@router.get(
    "/nightscout/events",
    response_model=NightscoutEventsResponse,
    operation_id="getNightscoutEvents",
    dependencies=[Depends(require_feature("nightscout"))],
)
async def get_nightscout_events(
    session: SessionDep,
    current_user: CurrentUserDep,
    client: NightscoutDep,
    from_datetime: Annotated[datetime, Query(alias="from")],
    to_datetime: Annotated[datetime, Query(alias="to")],
) -> NightscoutEventsResponse:
    """Return combined read-only Nightscout glucose and insulin context events."""
    return await NightscoutSyncService(session, current_user.id, client).events(
        from_datetime,
        to_datetime,
    )


@router.get(
    "/nightscout/latest-reading",
    response_model=NightscoutLatestReadingResponse,
    operation_id="getNightscoutLatestReading",
    dependencies=[Depends(require_feature("nightscout"))],
)
def get_nightscout_latest_reading(
    session: SessionDep,
    current_user: CurrentUserDep,
) -> NightscoutLatestReadingResponse:
    """Return the latest glucose reading from the local Nightscout cache."""
    from sqlalchemy import func, select

    from glucotracker.infra.db.models import NightscoutGlucoseEntry, SensorSession

    glucose_stmt = (
        select(NightscoutGlucoseEntry)
        .where(
            NightscoutGlucoseEntry.owner_id == current_user.id,
            visible_glucose_filter(current_user.id),
        )
        .order_by(NightscoutGlucoseEntry.timestamp.desc())
        .limit(1)
    )
    latest = session.execute(glucose_stmt).scalar_one_or_none()

    if not latest:
        return NightscoutLatestReadingResponse()

    count_stmt = (
        select(func.count())
        .select_from(NightscoutGlucoseEntry)
        .where(
            NightscoutGlucoseEntry.owner_id == current_user.id,
            visible_glucose_filter(current_user.id),
        )
    )
    total = session.execute(count_stmt).scalar() or 0

    sensor_stmt = (
        select(SensorSession.id)
        .where(
            SensorSession.started_at <= latest.timestamp,
            SensorSession.owner_id == current_user.id,
            SensorSession.excluded_from_analytics.is_(False),
            (SensorSession.ended_at.is_(None))
            | (SensorSession.ended_at >= latest.timestamp),
        )
        .order_by(SensorSession.started_at.desc())
        .limit(1)
    )
    sensor_row = session.execute(sensor_stmt).scalar_one_or_none()

    return NightscoutLatestReadingResponse(
        timestamp=latest.timestamp,
        value_mmol_l=latest.value_mmol_l,
        trend=latest.trend,
        sensor_id=str(sensor_row) if sensor_row else None,
        total_entries=total,
    )


@router.post(
    "/nightscout/import",
    response_model=NightscoutImportResponse,
    operation_id="importNightscoutContext",
    dependencies=[Depends(require_feature("nightscout"))],
)
async def import_nightscout_context(
    payload: NightscoutImportRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
    client: NightscoutDep,
) -> NightscoutImportResponse:
    """Fetch Nightscout glucose/insulin context and cache it locally."""
    settings_svc = NightscoutSettingsService(session, current_user.id)
    row = settings_svc.get_or_create()
    effective_client = settings_svc.client(client)
    effective_client_obj = effective_client or client

    if not effective_client_obj or not effective_client_obj.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=NIGHTSCOUT_NOT_CONFIGURED,
        )

    do_glucose = payload.sync_glucose and row.sync_glucose
    do_insulin = payload.import_insulin_events and row.import_insulin_events
    session.commit()

    if not do_glucose and not do_insulin:
        svc = NightscoutContextImportService(
            session,
            current_user.id,
            effective_client_obj,
        )
        return await svc.import_range(
            payload.from_datetime,
            payload.to_datetime,
            sync_glucose=False,
            import_insulin_events=False,
        )

    glucose_rows = []
    insulin_rows = []
    sensor_event_rows = []
    if do_glucose:
        try:
            glucose_rows = await effective_client_obj.fetch_glucose_entries(
                payload.from_datetime,
                payload.to_datetime,
            )
            if hasattr(effective_client_obj, "fetch_sensor_events"):
                try:
                    sensor_event_rows = await effective_client_obj.fetch_sensor_events(
                        payload.from_datetime,
                        payload.to_datetime,
                    )
                except Exception:
                    sensor_event_rows = []
        except Exception as exc:
            raise NightscoutSyncService.map_error(exc) from exc
    if do_insulin:
        try:
            insulin_rows = await effective_client_obj.fetch_insulin_events(
                payload.from_datetime,
                payload.to_datetime,
            )
        except Exception as exc:
            raise NightscoutSyncService.map_error(exc) from exc

    return NightscoutContextImportService(
        session,
        current_user.id,
        effective_client_obj,
    ).import_fetched(
        payload.from_datetime,
        payload.to_datetime,
        glucose_rows=glucose_rows,
        insulin_rows=insulin_rows,
        sensor_event_rows=sensor_event_rows,
    )


@router.get(
    "/timeline",
    response_model=TimelineResponse | TimelineFoodResponse,
    operation_id="getTimeline",
)
def get_timeline(
    session: SessionDep,
    current_user: CurrentUserDep,
    from_datetime: Annotated[datetime, Query(alias="from")],
    to_datetime: Annotated[datetime, Query(alias="to")],
) -> TimelineResponse | TimelineFoodResponse:
    """Return backend-owned food episodes with local Nightscout context."""
    if current_user.role == UserRole.food:
        return FoodEpisodeService(session, current_user.id).timeline_food(
            from_datetime,
            to_datetime,
        )
    return FoodEpisodeService(session, current_user.id).timeline(
        from_datetime,
        to_datetime,
    )


@router.get(
    "/timeline/insulin-links",
    response_model=InsulinLinkDayResponse,
    operation_id="getTimelineInsulinLinks",
    dependencies=[Depends(require_feature("glucose"))],
)
def get_timeline_insulin_links(
    session: SessionDep,
    current_user: CurrentUserDep,
    date: Annotated[date_type, Query()],
) -> InsulinLinkDayResponse:
    """Return one-day food/insulin links and backend suggestions."""
    return InsulinLinkDayService(session, current_user.id).get_day(date)


@router.put(
    "/timeline/insulin-links",
    response_model=InsulinLinkDayResponse,
    operation_id="putTimelineInsulinLinks",
    dependencies=[Depends(require_feature("glucose"))],
)
def put_timeline_insulin_links(
    payload: InsulinLinkDayPutRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> InsulinLinkDayResponse:
    """Replace reviewed one-day food/insulin links atomically."""
    return InsulinLinkDayService(session, current_user.id).replace_day(payload)
