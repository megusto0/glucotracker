"""Domain entities and enum values for meal and nutrition records."""

from dataclasses import dataclass
from enum import StrEnum


class MealStatus(StrEnum):
    """Lifecycle state for a meal journal entry."""

    draft = "draft"
    accepted = "accepted"
    discarded = "discarded"


class MealSource(StrEnum):
    """Origin of a meal journal entry."""

    photo = "photo"
    pattern = "pattern"
    manual = "manual"
    mixed = "mixed"


class ItemSourceKind(StrEnum):
    """Origin of an individual meal item estimate or calculation."""

    photo_estimate = "photo_estimate"
    label_calc = "label_calc"
    restaurant_db = "restaurant_db"
    product_db = "product_db"
    pattern = "pattern"
    manual = "manual"


class PhotoReferenceKind(StrEnum):
    """Reference object detected or supplied for photo scale estimation."""

    coin_5rub = "coin_5rub"
    card = "card"
    hand = "hand"
    fork = "fork"
    plate = "plate"
    none = "none"


class PhotoScenario(StrEnum):
    """Scenario represented by an uploaded meal or label photo."""

    label_full = "label_full"
    label_partial = "label_partial"
    plated = "plated"
    barcode = "barcode"
    reference = "reference"
    unknown = "unknown"


class NightscoutSyncStatus(StrEnum):
    """Local Nightscout synchronization state for one meal."""

    not_synced = "not_synced"
    synced = "synced"
    failed = "failed"
    skipped = "skipped"


class MealWindow(StrEnum):
    """Meal position relative to the user's first-meal-of-day anchor."""

    start = "start"
    mid = "mid"
    late = "late"
    night_cap = "night_cap"


class MealRole(StrEnum):
    """Structural role of a meal based on kcal and protein."""

    main_meal = "main_meal"
    snack = "snack"
    dessert = "dessert"
    drink = "drink"
    composite = "composite"


class Provenance(StrEnum):
    """Origin of the food in a meal (homemade vs packaged vs restaurant)."""

    homemade = "homemade"
    packaged = "packaged"
    restaurant_fastfood = "restaurant_fastfood"
    restaurant_other = "restaurant_other"
    unknown = "unknown"


class TasteProfile(StrEnum):
    """Taste classification determined by Flash Lite."""

    sweet = "sweet"
    savory = "savory"
    neutral = "neutral"
    drink_sweet = "drink_sweet"
    drink_other = "drink_other"


class WeekdayType(StrEnum):
    """Whether a meal falls on a weekday or weekend."""

    weekday = "weekday"
    weekend = "weekend"


class AnchorBasis(StrEnum):
    """Basis used to compute the user's day anchor."""

    weighted_7d = "weighted_7d"
    shift_3d = "shift_3d"
    absolute_fallback = "absolute_fallback"
    user_override = "user_override"


@dataclass(frozen=True)
class ValidationWarning:
    """Pure-domain warning raised by nutrition consistency checks."""

    code: str
    message: str
    field: str | None = None


class PreMealState(StrEnum):
    """CGM-based glucose state just before a meal."""

    low = "low"
    in_range = "in_range"
    high = "high"
    unknown = "unknown"


class GlycemicResponse(StrEnum):
    """Postprandial glucose curve shape classification."""

    gentle = "gentle"
    moderate = "moderate"
    spike = "spike"
    unstable = "unstable"
    unknown = "unknown"
