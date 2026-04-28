"""Importer for the official Burger King Russia nutrition PDF."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from glucotracker.infra.importers.restaurant_pdf_importer import (
    RestaurantItem,
    aliases_for_name,
    as_float,
    deduplicate_items,
    extract_pdf_pages,
    normalize_space,
    slugify_key,
    write_seed_yaml,
)

PREFIX = "bk"
SOURCE_NAME = "Burger King official PDF"
SOURCE_URL = "https://burgerkingrus.ru/"

_ROW_RE = re.compile(
    r"(?P<weight>\d+(?:[,.]\d+)?)\s*(?P<unit>г|мл|л)\s+"
    r"(?P<kcal>\d+(?:[,.]\d+)?)\s+(?P<kcal100>\d+(?:[,.]\d+)?)\s+"
    r"(?P<kj>\d+(?:[,.]\d+)?)\s+(?P<kj100>\d+(?:[,.]\d+)?)\s+"
    r"(?P<protein>\d+(?:[,.]\d+)?)\s+(?P<protein100>\d+(?:[,.]\d+)?)\s+"
    r"(?P<fat>\d+(?:[,.]\d+)?)\s+(?P<fat100>\d+(?:[,.]\d+)?)\s+"
    r"(?P<carbs>\d+(?:[,.]\d+)?)\s+(?P<carbs100>\d+(?:[,.]\d+)?)",
    re.IGNORECASE,
)

_IGNORE_NAME_PARTS = {
    "сведения",
    "приложение",
    "наименование",
    "фирменного",
    "готовом",
    "энергетическая",
    "ценность",
    "белки",
    "жиры",
    "углеводы",
    "порцию",
    "продукта",
    "граммовка",
    "количество",
}


def _looks_like_name(line: str) -> bool:
    """Return true for all-caps product-name-like lines."""
    value = normalize_space(line)
    if len(value) < 2 or len(value) > 90:
        return False
    lowered = value.casefold()
    if any(part in lowered for part in _IGNORE_NAME_PARTS):
        return False
    if re.match(r"^[\W_]*е\d+", lowered):
        return False
    letters = [char for char in value if char.isalpha()]
    if len(letters) < 2:
        return False
    return value.upper() == value


def _leading_name_fragment(line: str) -> str | None:
    """Extract an uppercase product heading merged with ingredient text."""
    value = normalize_space(line)
    if not value:
        return None
    words = value.split()
    picked: list[str] = []
    for word in words:
        letters = [char for char in word if char.isalpha()]
        if letters and any(char.islower() for char in letters):
            break
        picked.append(word)
    candidate = normalize_space(" ".join(picked))
    return candidate if _looks_like_name(candidate) else None


def _extract_name(segment: str) -> str | None:
    """Extract the nearest product heading before a numeric row."""
    candidates: list[str] = []
    current: list[str] = []
    for raw_line in segment.splitlines():
        line = normalize_space(raw_line)
        if _looks_like_name(line):
            current.append(line)
            continue
        leading = _leading_name_fragment(line)
        if leading is not None:
            current.append(leading)
            candidates.append(normalize_space(" ".join(current)))
            current = []
            continue
        if current:
            candidates.append(normalize_space(" ".join(current)))
            current = []
    if current:
        candidates.append(normalize_space(" ".join(current)))
    return candidates[-1] if candidates else None


def _weight_to_grams(value: str, unit: str) -> float:
    """Normalize grams/ml/l into the default amount field."""
    amount = as_float(value)
    if unit.casefold() == "л":
        return amount * 1000
    return amount


def _is_plausible_item(item: RestaurantItem) -> bool:
    """Reject PDF extraction artifacts with shifted numeric columns."""
    if item.default_grams is not None and item.default_grams <= 0:
        return False
    macro_values = [
        item.default_carbs_g,
        item.default_protein_g,
        item.default_fat_g,
        item.per_100g_carbs_g,
        item.per_100g_protein_g,
        item.per_100g_fat_g,
    ]
    if any(value is not None and value > 300 for value in macro_values):
        return False
    if item.default_grams is not None and item.default_grams <= 20:
        if max(item.default_carbs_g, item.default_protein_g, item.default_fat_g) > 50:
            return False
        if item.default_kcal > 600:
            return False
    return True


def parse_bk_text_pages(
    pages: list[str],
    *,
    source_file: str | None = None,
) -> list[RestaurantItem]:
    """Parse BK nutrition rows from extracted PDF text pages."""
    items: list[RestaurantItem] = []
    for page_number, text in enumerate(pages, start=1):
        previous_end = 0
        for match in _ROW_RE.finditer(text):
            segment = text[previous_end : match.start()]
            previous_end = match.end()
            name = _extract_name(segment)
            if not name:
                continue
            grams = _weight_to_grams(match.group("weight"), match.group("unit"))
            item = RestaurantItem(
                source_namespace=PREFIX,
                key=slugify_key(name),
                display_name=name.title(),
                default_grams=grams,
                default_kcal=as_float(match.group("kcal")),
                default_carbs_g=as_float(match.group("carbs")),
                default_protein_g=as_float(match.group("protein")),
                default_fat_g=as_float(match.group("fat")),
                per_100g_kcal=as_float(match.group("kcal100")),
                per_100g_carbs_g=as_float(match.group("carbs100")),
                per_100g_protein_g=as_float(match.group("protein100")),
                per_100g_fat_g=as_float(match.group("fat100")),
                aliases=aliases_for_name(name),
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                source_file=source_file,
                source_page=page_number,
                source_confidence="official_pdf",
                is_verified=False,
            )
            if _is_plausible_item(item):
                items.append(item)
    return deduplicate_items(items)


def parse_bk_pdf(path: Path) -> list[RestaurantItem]:
    """Parse BK official PDF into normalized restaurant items."""
    return parse_bk_text_pages(extract_pdf_pages(path), source_file=path.name)


def main() -> None:
    """CLI entry point for BK PDF seed generation."""
    parser = argparse.ArgumentParser(description="Import Burger King nutrition PDF.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    items = parse_bk_pdf(args.pdf)
    write_seed_yaml(
        prefix=PREFIX,
        source_name=SOURCE_NAME,
        source_url=SOURCE_URL,
        source_file=args.pdf.name,
        items=items,
        out=args.out,
    )
    print(f"Extracted {len(items)} Burger King items into {args.out}")


if __name__ == "__main__":
    main()
