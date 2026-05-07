"""Nutrient definition endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import select

from glucotracker.api.dependencies import CurrentUserDep, ReadSessionDep
from glucotracker.api.schemas import NutrientDefinitionResponse
from glucotracker.domain.nutrients import DEFAULT_NUTRIENT_DEFINITIONS
from glucotracker.infra.db.models import NutrientDefinition

router = APIRouter(tags=["nutrients"])


@router.get(
    "/nutrients/definitions",
    response_model=list[NutrientDefinitionResponse],
    operation_id="listNutrientDefinitions",
)
def list_nutrient_definitions(
    session: ReadSessionDep,
    current_user: CurrentUserDep,
) -> list[NutrientDefinitionResponse]:
    """Return the built-in nutrient definition catalog."""
    catalog_timestamp = datetime.now(UTC)
    definitions = {
        definition["code"]: {**definition, "created_at": catalog_timestamp}
        for definition in DEFAULT_NUTRIENT_DEFINITIONS
    }
    definitions.update(
        {
            definition.code: {
                "code": definition.code,
                "display_name": definition.display_name,
                "unit": definition.unit,
                "category": definition.category,
                "created_at": definition.created_at,
            }
            for definition in session.scalars(
                select(NutrientDefinition).order_by(NutrientDefinition.code.asc())
            )
        }
    )
    return [
        NutrientDefinitionResponse(**definition)
        for _, definition in sorted(definitions.items())
    ]
