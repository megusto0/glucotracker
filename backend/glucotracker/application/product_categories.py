"""Server-side food category rules for deterministic stats insights."""

from __future__ import annotations

from collections.abc import Iterable

ProductCategory = str

SWEET_KEYWORDS = (
    "шоколад",
    "печенье",
    "торт",
    "конфет",
    "маффин",
    "кекс",
    "десерт",
    "пирож",
    "вафл",
    "морож",
    "слад",
    "cookie",
    "chocolate",
    "cake",
    "candy",
    "muffin",
    "dessert",
)

CATEGORY_RULES: tuple[tuple[ProductCategory, tuple[str, ...]], ...] = (
    ("sweet", SWEET_KEYWORDS),
    (
        "drink",
        (
            "напит",
            "сок",
            "чай",
            "кофе",
            "лимонад",
            "вода",
            "drink",
            "juice",
            "coffee",
            "tea",
        ),
    ),
    (
        "snack",
        (
            "чипс",
            "снэк",
            "снек",
            "орех",
            "snack",
            "chips",
            "nuts",
        ),
    ),
    (
        "savory",
        (
            "сыр",
            "колбас",
            "ветчин",
            "рыба",
            "мяс",
            "cheese",
            "sausage",
            "ham",
            "fish",
            "meat",
        ),
    ),
    (
        "meal",
        (
            "суп",
            "паста",
            "рис",
            "греч",
            "салат",
            "бургер",
            "пицц",
            "soup",
            "pasta",
            "rice",
            "salad",
            "burger",
            "pizza",
        ),
    ),
)


def categorize_text(parts: Iterable[str | None]) -> ProductCategory | None:
    """Return the first matching server-side category for product-like text."""
    text = " ".join(part or "" for part in parts).casefold()
    if not text.strip():
        return None
    for category, keywords in CATEGORY_RULES:
        if any(keyword in text for keyword in keywords):
            return category
    return "other"


def is_sweet_text(parts: Iterable[str | None]) -> bool:
    """Return whether text matches the sweet category rules."""
    return categorize_text(parts) == "sweet"
