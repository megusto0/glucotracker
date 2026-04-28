"""Shared helpers for official restaurant nutrition imports."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class RestaurantItem:
    """Normalized restaurant nutrition row before seed YAML export."""

    source_namespace: str
    key: str
    display_name: str
    default_grams: float | None
    default_kcal: float
    default_carbs_g: float
    default_protein_g: float
    default_fat_g: float
    per_100g_kcal: float | None = None
    per_100g_carbs_g: float | None = None
    per_100g_protein_g: float | None = None
    per_100g_fat_g: float | None = None
    default_fiber_g: float = 0
    image_url: str | None = None
    aliases: list[str] = field(default_factory=list)
    source_name: str | None = None
    source_url: str | None = None
    source_file: str | None = None
    source_page: int | None = None
    source_confidence: str = "official_pdf"
    is_verified: bool = False


_TRANSLIT = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "i",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
)

_KNOWN_KEYS = {
    "воппер": "whopper",
    "воппер с сыром": "whopper_cheese",
    "наггетсы 6 шт": "nuggets_6",
    "наггетсы 9 шт": "nuggets_9",
    "наггетсы 3 шт": "nuggets_3",
}


def normalize_space(value: str) -> str:
    """Collapse whitespace and trim a string."""
    return re.sub(r"\s+", " ", value).strip()


def parse_decimal(value: str | int | float | None) -> float | None:
    """Parse Russian decimal notation into a float."""
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    normalized = str(value).strip().replace(",", ".")
    if not normalized:
        return None
    return float(normalized)


def as_float(value: str | int | float | None, default: float = 0) -> float:
    """Parse a decimal and return a non-null float."""
    parsed = parse_decimal(value)
    return default if parsed is None else parsed


def _transliterate(value: str) -> str:
    """Return a simple ASCII transliteration for tokens and aliases."""
    normalized = unicodedata.normalize("NFKD", value.casefold())
    transliterated = "".join(
        char.translate(_TRANSLIT) if "а" <= char <= "я" or char == "ё" else char
        for char in normalized
        if not unicodedata.combining(char)
    )
    return transliterated


def slugify_key(display_name: str) -> str:
    """Create a stable lowercase key from a restaurant item display name."""
    normalized_ru = normalize_space(display_name.casefold())
    if normalized_ru in _KNOWN_KEYS:
        return _KNOWN_KEYS[normalized_ru]
    value = _transliterate(normalized_ru)
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value or "item"


def aliases_for_name(display_name: str, *, extra: list[str] | None = None) -> list[str]:
    """Generate Russian and transliterated aliases for a display name."""
    aliases: list[str] = []
    lower = normalize_space(display_name.casefold())
    aliases.append(lower)
    aliases.append(_transliterate(lower).replace("_", " "))
    aliases.append(slugify_key(display_name))
    aliases.extend(extra or [])

    seen: set[str] = set()
    result: list[str] = []
    for alias in aliases:
        normalized = normalize_space(alias).strip("_")
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def extract_pdf_pages(path: Path) -> list[str]:
    """Extract text from every page of a PDF using pypdf."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return [page.extract_text() or "" for page in reader.pages]


def item_to_seed(item: RestaurantItem) -> dict[str, Any]:
    """Convert a normalized item into one pattern seed mapping."""
    return {
        "key": item.key,
        "display_name": item.display_name,
        "default_grams": item.default_grams,
        "default_carbs_g": item.default_carbs_g,
        "default_protein_g": item.default_protein_g,
        "default_fat_g": item.default_fat_g,
        "default_fiber_g": item.default_fiber_g,
        "default_kcal": item.default_kcal,
        "per_100g_kcal": item.per_100g_kcal,
        "per_100g_carbs_g": item.per_100g_carbs_g,
        "per_100g_protein_g": item.per_100g_protein_g,
        "per_100g_fat_g": item.per_100g_fat_g,
        "image_url": item.image_url,
        "aliases": item.aliases,
        "source_name": item.source_name,
        "source_url": item.source_url,
        "source_file": item.source_file,
        "source_page": item.source_page,
        "source_confidence": item.source_confidence,
        "is_verified": item.is_verified,
    }


def write_seed_yaml(
    *,
    prefix: str,
    source_name: str,
    source_url: str | None,
    source_file: str | None,
    items: list[RestaurantItem],
    out: Path,
) -> None:
    """Write human-reviewable pattern seed YAML for restaurant items."""
    payload = {
        "prefix": prefix,
        "source_name": source_name,
        "source_url": source_url,
        "source_file": source_file,
        "items": [item_to_seed(item) for item in items],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        yaml.safe_dump(
            payload,
            allow_unicode=True,
            sort_keys=False,
            width=120,
        ),
        encoding="utf-8",
    )


def deduplicate_items(items: list[RestaurantItem]) -> list[RestaurantItem]:
    """Deduplicate by key while preserving the first official row."""
    seen: set[str] = set()
    result: list[RestaurantItem] = []
    for item in items:
        key = item.key
        if key in seen:
            suffix = 2
            while f"{key}_{suffix}" in seen:
                suffix += 1
            item.key = f"{key}_{suffix}"
        seen.add(item.key)
        result.append(item)
    return result
