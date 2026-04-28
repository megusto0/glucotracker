"""Pure helpers for optional nutrient tracking and source priority."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DEFAULT_NUTRIENT_DEFINITIONS: tuple[dict[str, str], ...] = (
    {
        "code": "sodium_mg",
        "display_name": "Sodium",
        "unit": "mg",
        "category": "mineral",
    },
    {
        "code": "caffeine_mg",
        "display_name": "Caffeine",
        "unit": "mg",
        "category": "stimulant",
    },
    {
        "code": "sugar_g",
        "display_name": "Sugar",
        "unit": "g",
        "category": "carbohydrate",
    },
    {
        "code": "potassium_mg",
        "display_name": "Potassium",
        "unit": "mg",
        "category": "mineral",
    },
    {
        "code": "iron_mg",
        "display_name": "Iron",
        "unit": "mg",
        "category": "mineral",
    },
    {
        "code": "calcium_mg",
        "display_name": "Calcium",
        "unit": "mg",
        "category": "mineral",
    },
    {
        "code": "magnesium_mg",
        "display_name": "Magnesium",
        "unit": "mg",
        "category": "mineral",
    },
)

NUTRIENT_UNITS = {
    definition["code"]: definition["unit"]
    for definition in DEFAULT_NUTRIENT_DEFINITIONS
}

SOURCE_PRIORITY = {
    "manual": 100,
    "label_calc": 90,
    "label_manual": 90,
    "product_db": 80,
    "restaurant_db": 80,
    "pattern": 70,
    "generic_food_db": 55,
    "photo_estimate": 20,
    "visual_estimate": 20,
}

VISUAL_GUESS_BLOCKLIST = {"sodium_mg", "caffeine_mg"}


def nutrient_unit(code: str) -> str:
    """Return the canonical nutrient unit for a code."""
    if code in NUTRIENT_UNITS:
        return NUTRIENT_UNITS[code]
    if code.endswith("_mg"):
        return "mg"
    if code.endswith("_g"):
        return "g"
    return "unit"


def source_priority(source_kind: str | None) -> int:
    """Return priority for resolving competing nutrient sources."""
    return SOURCE_PRIORITY.get(source_kind or "", 0)


def normalize_nutrient_entry(
    code: str,
    raw: Any,
    *,
    default_source_kind: str,
) -> dict[str, Any]:
    """Normalize a nutrient payload entry into storage fields."""
    if isinstance(raw, (int, float)):
        data: Mapping[str, Any] = {"amount": float(raw)}
    elif raw is None:
        data = {"amount": None}
    elif isinstance(raw, Mapping):
        data = raw
    else:
        msg = f"Nutrient {code} must be a number, null, or object."
        raise TypeError(msg)

    amount = data.get("amount")
    if amount is not None:
        amount = float(amount)

    evidence = data.get("evidence_json", data.get("evidence", {}))
    assumptions = data.get("assumptions_json", data.get("assumptions", []))
    return {
        "nutrient_code": code,
        "amount": amount,
        "unit": str(data.get("unit") or nutrient_unit(code)),
        "source_kind": str(data.get("source_kind") or default_source_kind),
        "confidence": data.get("confidence"),
        "evidence_json": dict(evidence or {}),
        "assumptions_json": list(assumptions or []),
    }


def normalize_nutrients_object(
    nutrients: Mapping[str, Any] | None,
    *,
    default_source_kind: str,
) -> dict[str, dict[str, Any]]:
    """Normalize an API or seed nutrient object by nutrient code."""
    if not nutrients:
        return {}
    return {
        str(code): normalize_nutrient_entry(
            str(code),
            raw,
            default_source_kind=default_source_kind,
        )
        for code, raw in nutrients.items()
    }


def merge_nutrient_maps(
    *nutrient_maps: Mapping[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Merge nutrient maps, keeping the highest-priority source per code."""
    merged: dict[str, dict[str, Any]] = {}
    for nutrient_map in nutrient_maps:
        for code, entry in nutrient_map.items():
            existing = merged.get(code)
            if existing is None or source_priority(entry.get("source_kind")) >= (
                source_priority(existing.get("source_kind"))
            ):
                merged[code] = dict(entry)
    return merged
