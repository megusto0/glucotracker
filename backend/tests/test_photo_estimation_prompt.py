"""Regression tests for the structured photo-estimation prompt contract."""

from glucotracker.infra.gemini.client import (
    PHOTO_ESTIMATION_PROMPT_V2,
    PHOTO_ESTIMATION_PROMPT_VERSION,
)


def test_packaged_food_fallback_requires_complete_numeric_totals() -> None:
    normalized_prompt = " ".join(PHOTO_ESTIMATION_PROMPT_V2.split())

    assert PHOTO_ESTIMATION_PROMPT_VERSION == "PHOTO_ESTIMATION_PROMPT_V2"
    assert "Mandatory packaged-food fallback" in normalized_prompt
    assert "Never leave any of these fields null" in normalized_prompt
    assert "grams_mid, carbs_g_mid, protein_g_mid, fat_g_mid, fiber_g_mid" in (
        normalized_prompt
    )
    assert "Repair any null packaged-food macro before returning" in (
        normalized_prompt
    )
