"""Authenticated personal photo-model overview and priority settings."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import IntegrityError

from glucotracker.api.ai_models_schemas import AIModelRoutingUpdate, AIModelsResponse
from glucotracker.api.dependencies import CurrentUserDep, ReadSessionDep, SessionDep
from glucotracker.application.ai_models import overview
from glucotracker.infra.db.repositories.ai_models import (
    AIModelsRepository,
    RoutingConflict,
)

router = APIRouter(prefix="/ai/models", tags=["ai-models"])


@router.get("", response_model=AIModelsResponse, operation_id="getAIModels")
def get_models(
    session: ReadSessionDep,
    current_user: CurrentUserDep,
    days: Annotated[int, Query(ge=1, le=90)] = 30,
    history_offset: Annotated[int, Query(ge=0, le=5000)] = 0,
    history_limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> AIModelsResponse:
    return overview(session, current_user.id, days, history_offset, history_limit)


@router.put("", response_model=AIModelsResponse, operation_id="updateAIModels")
def update_models(
    payload: AIModelRoutingUpdate,
    session: SessionDep,
    current_user: CurrentUserDep,
    days: Annotated[int, Query(ge=1, le=90)] = 30,
    history_offset: Annotated[int, Query(ge=0, le=5000)] = 0,
    history_limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> AIModelsResponse:
    try:
        AIModelsRepository(session, current_user.id).save(
            [m.model_dump() for m in payload.models], payload.revision
        )
        session.commit()
    except (RoutingConflict, IntegrityError) as exc:
        session.rollback()
        raise HTTPException(
            409, "Порядок моделей уже изменён. Обновите страницу и повторите изменение."
        ) from exc
    return overview(session, current_user.id, days, history_offset, history_limit)
