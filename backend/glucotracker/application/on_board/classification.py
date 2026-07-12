"""Deterministic event classification and privacy-preserving meal identities."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable

_LONG_ACTING_TERMS = (
    "basal",
    "temp basal",
    "temporary basal",
    "long acting",
    "long-acting",
    "glargine",
    "detemir",
    "degludec",
    "lantus",
    "levemir",
    "tresiba",
    "toujeo",
    "basaglar",
    "semglee",
    "nph",
)
_UNMODELED_DELIVERY_TERMS = (
    "combo bolus",
    "dual wave",
    "square wave",
    "extended bolus",
)
_NON_INSULIN_EVENT_TERMS = (
    "sensor",
    "site change",
    "bg check",
    "carb correction",
)
_RAPID_INSULIN_TERMS = (
    "rapid",
    "lispro",
    "aspart",
    "glulisine",
    "humalog",
    "novolog",
    "novorapid",
    "fiasp",
    "apidra",
    "lyumjev",
)
_DRINK_TERMS = (
    "drink",
    "juice",
    "soda",
    "cola",
    "energy",
    "beverage",
    "напит",
    "сок",
    "кола",
    "лимонад",
    "энергет",
)


def normalized_text(value: str | None) -> str:
    """Normalize imported free text for classification, never for display."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[\w]+", normalized, flags=re.UNICODE))


def is_rapid_insulin_event(
    *,
    insulin_type: str | None,
    event_type: str | None,
) -> bool:
    """Return whether an imported event can use the rapid-bolus IOB model.

    Unknown legacy ``Insulin``/bolus rows remain eligible so historical data is
    not silently lost.  Explicit basal, long-acting, or extended deliveries are
    excluded until a delivery-specific model exists.
    """
    insulin_name = normalized_text(insulin_type)
    event_name = normalized_text(event_type)
    combined = f"{insulin_name} {event_name}".strip()
    if any(term in combined for term in _LONG_ACTING_TERMS):
        return False
    if any(term in event_name for term in _UNMODELED_DELIVERY_TERMS):
        return False
    if any(term in event_name for term in _NON_INSULIN_EVENT_TERMS):
        return False
    if insulin_name:
        return any(term in insulin_name for term in _RAPID_INSULIN_TERMS)
    return (
        not event_name
        or "bolus" in event_name
        or event_name == "insulin"
        or "correction" in event_name
    )


def is_liquid_meal(
    *,
    ai_categories: dict[str, object] | None,
    derived_categories: dict[str, object] | None,
    title: str | None,
    item_names: Iterable[str],
) -> bool:
    """Infer liquid form from stored meal metadata and identity text."""
    ai = ai_categories or {}
    derived = derived_categories or {}
    taste = normalized_text(str(ai.get("taste_profile") or ""))
    role = normalized_text(str(derived.get("meal_role") or ""))
    if "drink" in taste or role == "drink":
        return True
    identity = " ".join(
        [normalized_text(title), *(normalized_text(name) for name in item_names)]
    )
    return any(term in identity for term in _DRINK_TERMS)


def meal_pattern_key(
    *,
    item_identity_keys: Iterable[str],
    title: str | None,
    carbs_g: float,
    protein_g: float,
    fat_g: float,
    fiber_g: float,
) -> str:
    """Return a stable hash; never persist a private meal/product name as key."""
    identities = sorted(
        key for key in (normalized_text(value) for value in item_identity_keys) if key
    )
    if not identities:
        identities = [normalized_text(title) or "unnamed"]
    carbs = max(float(carbs_g or 0.0), 1.0)
    ratio_bins = (
        _ratio_bin(float(protein_g or 0.0) / carbs),
        _ratio_bin(float(fat_g or 0.0) / carbs),
        _ratio_bin(float(fiber_g or 0.0) / carbs),
    )
    canonical = "|".join([*identities, *(str(value) for value in ratio_bins)])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def meal_category_scope(*, dominant_profile: str, is_liquid: bool) -> str:
    """Return the personal class fallback key used below exact fingerprints."""
    suffix = "liquid" if is_liquid else "solid"
    profile = (
        dominant_profile if dominant_profile in {"fast", "normal", "slow"} else "normal"
    )
    return f"category:{profile}:{suffix}"


def _ratio_bin(value: float) -> int:
    return max(0, min(20, int(round(max(0.0, value) / 0.25))))
