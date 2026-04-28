"""Nightscout optional sync endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from glucotracker.api.dependencies import SessionDep, verify_token
from glucotracker.api.routers.meals import _get_meal
from glucotracker.api.schemas import NightscoutStatusResponse, NightscoutSyncResponse
from glucotracker.domain.entities import MealStatus
from glucotracker.infra.db.models import utc_now
from glucotracker.infra.nightscout.client import (
    NIGHTSCOUT_NOT_CONFIGURED,
    NightscoutClient,
    NightscoutHTTPError,
    NightscoutTimeoutError,
    get_nightscout_client,
)

router = APIRouter(
    tags=["nightscout"],
    dependencies=[Depends(verify_token)],
)

NightscoutDep = Annotated[NightscoutClient | None, Depends(get_nightscout_client)]


def _require_nightscout(client: NightscoutClient | None) -> NightscoutClient:
    """Return configured client or raise 503."""
    if client is None or not client.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=NIGHTSCOUT_NOT_CONFIGURED,
        )
    return client


def _map_nightscout_error(exc: Exception) -> HTTPException:
    """Map Nightscout client errors into HTTP responses."""
    if isinstance(exc, NightscoutTimeoutError):
        return HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        )
    if isinstance(exc, NightscoutHTTPError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "Nightscout request failed",
                "status_code": exc.status_code,
                "response": exc.detail,
            },
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=str(exc) or "Nightscout request failed",
    )


def _nightscout_id(response: dict) -> str | None:
    """Extract a Nightscout treatment id from a response."""
    value = response.get("_id") or response.get("id")
    if value is not None:
        return str(value)
    result = response.get("result")
    if isinstance(result, dict):
        nested = result.get("_id") or result.get("id")
        return str(nested) if nested is not None else None
    items = response.get("items")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        item_id = items[0].get("_id") or items[0].get("id")
        return str(item_id) if item_id is not None else None
    return None


@router.get(
    "/nightscout/status",
    response_model=NightscoutStatusResponse,
    operation_id="getNightscoutStatus",
)
async def get_nightscout_status(client: NightscoutDep) -> NightscoutStatusResponse:
    """Return optional Nightscout status without breaking local use."""
    if client is None or not client.configured:
        return NightscoutStatusResponse(configured=False)
    try:
        status_payload = await client.get_status()
    except Exception as exc:
        raise _map_nightscout_error(exc) from exc
    return NightscoutStatusResponse(configured=True, status=status_payload)


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
    nightscout = _require_nightscout(client)
    meal = _get_meal(session, meal_id)
    if meal.status != MealStatus.accepted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only accepted meals can be synced to Nightscout.",
        )
    if meal.nightscout_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Meal already synced.",
                "nightscout_id": meal.nightscout_id,
            },
        )

    try:
        response = await nightscout.post_treatment(meal)
    except Exception as exc:
        raise _map_nightscout_error(exc) from exc

    remote_id = _nightscout_id(response)
    if remote_id is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Nightscout response did not include treatment id.",
        )
    meal.nightscout_id = remote_id
    meal.nightscout_synced_at = utc_now()
    session.commit()
    return NightscoutSyncResponse(
        synced=True,
        nightscout_id=meal.nightscout_id,
        nightscout_synced_at=meal.nightscout_synced_at,
        response=response,
    )


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
    nightscout = _require_nightscout(client)
    meal = _get_meal(session, meal_id)
    if not meal.nightscout_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Meal is not synced to Nightscout.",
        )

    remote_id = meal.nightscout_id
    try:
        response = await nightscout.delete_treatment(remote_id)
    except Exception as exc:
        raise _map_nightscout_error(exc) from exc

    meal.nightscout_id = None
    meal.nightscout_synced_at = None
    session.commit()
    return NightscoutSyncResponse(
        synced=False,
        nightscout_id=None,
        nightscout_synced_at=None,
        response=response,
    )
