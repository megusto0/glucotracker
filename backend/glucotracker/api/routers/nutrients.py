"""Nutrient definition endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select

from glucotracker.api.dependencies import SessionDep, verify_token
from glucotracker.api.schemas import NutrientDefinitionResponse
from glucotracker.infra.db.models import NutrientDefinition
from glucotracker.infra.db.nutrients import ensure_nutrient_definitions

router = APIRouter(
    tags=["nutrients"],
    dependencies=[Depends(verify_token)],
)


@router.get(
    "/nutrients/definitions",
    response_model=list[NutrientDefinitionResponse],
    operation_id="listNutrientDefinitions",
)
def list_nutrient_definitions(session: SessionDep) -> list[NutrientDefinition]:
    """Return the built-in nutrient definition catalog."""
    ensure_nutrient_definitions(session)
    session.commit()
    return list(
        session.scalars(
            select(NutrientDefinition).order_by(NutrientDefinition.code.asc())
        )
    )
