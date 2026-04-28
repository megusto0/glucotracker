"""Importer for the official Rostic's nutrition PDF."""

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

PREFIX = "rostics"
SOURCE_NAME = "Rostic's official PDF"
SOURCE_URL = "https://rostics.ru/"

_ROW_RE = re.compile(
    r"^БЛЮДО\s+(?P<name>.+?)\s+ТТК\s+\S+\s+"
    r"(?P<weight>\d+(?:[,.]\d+)?)\s+"
    r"(?P<protein100>\d+(?:[,.]\d+)?)\s+"
    r"(?P<fat100>\d+(?:[,.]\d+)?)\s+"
    r"(?P<carbs100>\d+(?:[,.]\d+)?)\s+"
    r"(?P<kcal100>\d+(?:[,.]\d+)?)\s+"
    r"(?P<kj100>\d+(?:[,.]\d+)?)\s+"
    r"(?P<protein>\d+(?:[,.]\d+)?)\s+"
    r"(?P<fat>\d+(?:[,.]\d+)?)\s+"
    r"(?P<carbs>\d+(?:[,.]\d+)?)\s+"
    r"(?P<kcal>\d+(?:[,.]\d+)?)\s*$",
    re.IGNORECASE,
)


def parse_rostics_text_pages(
    pages: list[str],
    *,
    source_file: str | None = None,
) -> list[RestaurantItem]:
    """Parse Rostic's nutrition rows from extracted PDF text pages."""
    items: list[RestaurantItem] = []
    for page_number, text in enumerate(pages, start=1):
        for raw_line in text.splitlines():
            line = normalize_space(raw_line)
            match = _ROW_RE.match(line)
            if not match:
                continue
            name = normalize_space(match.group("name"))
            items.append(
                RestaurantItem(
                    source_namespace=PREFIX,
                    key=slugify_key(name),
                    display_name=name,
                    default_grams=as_float(match.group("weight")),
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
            )
    return deduplicate_items(items)


def parse_rostics_pdf(path: Path) -> list[RestaurantItem]:
    """Parse Rostic's official PDF into normalized restaurant items."""
    return parse_rostics_text_pages(extract_pdf_pages(path), source_file=path.name)


def main() -> None:
    """CLI entry point for Rostic's PDF seed generation."""
    parser = argparse.ArgumentParser(description="Import Rostic's nutrition PDF.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    items = parse_rostics_pdf(args.pdf)
    write_seed_yaml(
        prefix=PREFIX,
        source_name=SOURCE_NAME,
        source_url=SOURCE_URL,
        source_file=args.pdf.name,
        items=items,
        out=args.out,
    )
    print(f"Extracted {len(items)} Rostic's items into {args.out}")


if __name__ == "__main__":
    main()
