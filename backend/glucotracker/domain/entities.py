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


@dataclass(frozen=True)
class ValidationWarning:
    """Pure-domain warning raised by nutrition consistency checks."""

    code: str
    message: str
    field: str | None = None
