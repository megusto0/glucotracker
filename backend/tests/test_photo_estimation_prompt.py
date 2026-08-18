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


def test_kitchen_scales_readout_instruction_in_prompt() -> None:
    normalized_prompt = " ".join(PHOTO_ESTIMATION_PROMPT_V2.split())

    assert "Kitchen scales and weight display readouts" in normalized_prompt
    assert "Always inspect the photo for kitchen scales" in normalized_prompt
    assert "Tare is ALWAYS zeroed" in normalized_prompt
    assert "The visible scale reading is ALWAYS the 100% NET food weight" in (
        normalized_prompt
    )
    assert "Do NOT deduct container, plate, or bowl tare weight" in (
        normalized_prompt
    )
    assert "Put the scale reading into evidence" in normalized_prompt

