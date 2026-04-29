"""Application service for meal draft lifecycle orchestration."""

from __future__ import annotations

from sqlalchemy.orm import Session

from glucotracker.application.daily_totals import DailyTotalsService
from glucotracker.domain.drafts import accept_meal_draft, discard_meal_draft
from glucotracker.infra.db.models import Meal, MealItem


class MealDraftService:
    """Coordinate draft state transitions with persistence side effects."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.daily_totals = DailyTotalsService(session)

    def accept(self, meal: Meal, final_items: list[MealItem]) -> Meal:
        """Accept a draft with final reviewed items and update affected totals."""
        accept_meal_draft(meal, final_items)
        self.session.flush()
        self.daily_totals.schedule_for_meal_times([meal.eaten_at])
        return meal

    def discard(self, meal: Meal) -> Meal:
        """Discard a draft and update affected totals."""
        eaten_at = meal.eaten_at
        discard_meal_draft(meal)
        self.daily_totals.schedule_for_meal_times([eaten_at])
        return meal

