"""Database helpers for nutrient definition seeds."""

from __future__ import annotations

from sqlalchemy.orm import Session

from glucotracker.domain.nutrients import DEFAULT_NUTRIENT_DEFINITIONS
from glucotracker.infra.db.models import NutrientDefinition


def ensure_nutrient_definitions(session: Session) -> None:
    """Insert built-in nutrient definitions if they are missing."""
    for definition in DEFAULT_NUTRIENT_DEFINITIONS:
        existing = session.get(NutrientDefinition, definition["code"])
        if existing is None:
            session.add(NutrientDefinition(**definition))
