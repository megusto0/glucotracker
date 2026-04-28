"""Tests for meal draft lifecycle domain functions."""

from types import SimpleNamespace

import pytest

from glucotracker.domain.drafts import (
    accept_meal_draft,
    discard_meal_draft,
    ensure_editable,
)
from glucotracker.domain.entities import MealStatus


def test_accept_meal_draft_sets_status_and_recalculates_totals() -> None:
    """Accepting a draft replaces items and writes backend-calculated totals."""
    meal = SimpleNamespace(
        status=MealStatus.draft,
        items=[SimpleNamespace(name="draft", carbs_g=99, protein_g=0, fat_g=0)],
        total_carbs_g=0,
        total_protein_g=0,
        total_fat_g=0,
        total_fiber_g=0,
        total_kcal=0,
        confidence=None,
    )
    final_items = [
        SimpleNamespace(
            carbs_g=10,
            protein_g=5,
            fat_g=2,
            fiber_g=1,
            kcal=78,
            confidence=0.8,
            position=9,
        ),
        SimpleNamespace(
            carbs_g=4,
            protein_g=2,
            fat_g=1,
            fiber_g=0,
            kcal=33,
            confidence=1.0,
            position=9,
        ),
    ]

    accepted = accept_meal_draft(meal, final_items)

    assert accepted.status == MealStatus.accepted
    assert accepted.items == final_items
    assert accepted.total_carbs_g == 14
    assert accepted.total_protein_g == 7
    assert accepted.total_fat_g == 3
    assert accepted.total_fiber_g == 1
    assert accepted.total_kcal == 111
    assert accepted.confidence == pytest.approx((0.8 * 10 + 1.0 * 4) / 14)
    assert [item.position for item in accepted.items] == [0, 1]


def test_discard_meal_draft_sets_discarded_status() -> None:
    """Discarding a draft moves it to discarded."""
    meal = SimpleNamespace(status=MealStatus.draft)

    discarded = discard_meal_draft(meal)

    assert discarded.status == MealStatus.discarded


def test_ensure_editable_rejects_discarded_meals() -> None:
    """Discarded meals are not editable."""
    with pytest.raises(ValueError, match="discarded meals"):
        ensure_editable(SimpleNamespace(status=MealStatus.discarded))
