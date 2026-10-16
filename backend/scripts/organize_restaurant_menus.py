"""Tidy one user's restaurant menus: official sizes, missing dishes, junk archived.

Reads ``catalog_seeds/restaurant_menus_2026_10.json``, built from the official
Rostic's menu API and the Vkusno i tochka nutrition API, and
``restaurant_menus_2026_10_bk.json``, built from Burger King's own menu on
Yandex Eda (weight and KBJU per 100 g supplied by the restaurant). Idempotent and
non-destructive: rows are added, renamed or archived, never deleted, and a
local image is never replaced. Official image URLs are stored for new rows;
``cache_restaurant_images.py`` downloads them afterwards.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from glucotracker.infra.db.models import Pattern, PatternAlias, User, utc_now
from glucotracker.infra.db.session import get_session_factory

CATALOG_DIR = Path(__file__).resolve().parents[1] / "catalog_seeds"
CATALOG_PATH = CATALOG_DIR / "restaurant_menus_2026_10.json"
BK_CATALOG_PATH = CATALOG_DIR / "restaurant_menus_2026_10_bk.json"


@dataclass
class MenuChanges:
    """Counts of what one run changed."""

    added: int = 0
    updated: int = 0
    renamed: int = 0
    archived: int = 0


def _pattern(session: Session, owner_id: UUID, prefix: str, key: str) -> Pattern | None:
    return session.scalar(
        select(Pattern).where(
            Pattern.owner_id == owner_id,
            Pattern.prefix == prefix,
            Pattern.key == key,
        )
    )


def _add_aliases(row: Pattern, aliases: list[str]) -> None:
    present = {alias.alias.casefold() for alias in row.aliases}
    for alias in aliases:
        if alias.casefold() not in present:
            row.aliases.append(PatternAlias(alias=alias))
            present.add(alias.casefold())


def _apply_upsert(
    session: Session,
    owner_id: UUID,
    item: dict[str, Any],
    changes: MenuChanges,
) -> None:
    prefix = item["prefix"]
    row = _pattern(session, owner_id, prefix, item["key"])
    if row is None:
        # The same dish may already exist under an older key.
        row = session.scalar(
            select(Pattern).where(
                Pattern.owner_id == owner_id,
                Pattern.prefix == prefix,
                func.lower(Pattern.display_name) == item["name"].lower(),
                Pattern.is_archived.is_(False),
            )
        )
    if row is None:
        row = Pattern(owner_id=owner_id, prefix=prefix, key=item["key"])
        session.add(row)
        changes.added += 1
    else:
        changes.updated += 1
    grams = item.get("grams")
    kcal = float(item["kcal"])
    carbs = float(item["carbs_g"])
    protein = float(item["protein_g"])
    fat = float(item["fat_g"])
    if min(kcal, carbs, protein, fat) < 0 or (grams is not None and grams <= 0):
        raise ValueError(f"Invalid nutrition for {prefix}:{item['key']}")
    row.display_name = item["name"]
    row.default_grams = float(grams) if grams is not None else None
    row.default_kcal = kcal
    row.default_carbs_g = carbs
    row.default_protein_g = protein
    row.default_fat_g = fat
    row.default_fiber_g = float(item.get("fiber_g") or 0)
    if grams:
        row.per_100g_kcal = round(kcal / grams * 100, 2)
        row.per_100g_carbs_g = round(carbs / grams * 100, 2)
        row.per_100g_protein_g = round(protein / grams * 100, 2)
        row.per_100g_fat_g = round(fat / grams * 100, 2)
    row.source_name = item["source_name"]
    row.source_url = item["source_url"]
    row.source_confidence = item.get("source_confidence", "official_api")
    row.is_archived = False
    image_url = item.get("image_url")
    if image_url and not (row.image_url or "").startswith("/patterns/"):
        row.image_url = image_url
    row.updated_at = utc_now()
    session.flush()
    _add_aliases(row, item.get("aliases", []))


def organize_restaurant_menus(
    session: Session,
    owner_id: UUID,
    catalog: dict[str, Any],
) -> MenuChanges:
    """Apply the catalogue to one owner's patterns and commit."""
    keys = [(item["prefix"], item["key"]) for item in catalog["upserts"]]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate catalogue key")
    changes = MenuChanges()
    for item in catalog["upserts"]:
        _apply_upsert(session, owner_id, item, changes)
    for item in catalog["renames"]:
        row = _pattern(session, owner_id, item["prefix"], item["key"])
        if row is None:
            continue
        if row.display_name != item["name"]:
            row.display_name = item["name"]
            row.updated_at = utc_now()
            changes.renamed += 1
        _add_aliases(row, item.get("aliases", []))
        stale = {alias.casefold() for alias in item.get("remove_aliases", [])}
        for alias in [a for a in row.aliases if a.alias.casefold() in stale]:
            row.aliases.remove(alias)
    for item in catalog["archives"]:
        query = select(Pattern).where(
            Pattern.owner_id == owner_id,
            Pattern.prefix == item["prefix"],
            Pattern.is_archived.is_(False),
        )
        if "key" in item:
            query = query.where(Pattern.key == item["key"])
        else:
            query = query.where(Pattern.key.contains(item["key_contains"]))
        for row in session.scalars(query):
            row.is_archived = True
            row.updated_at = utc_now()
            changes.archived += 1
    session.commit()
    return changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--catalog", default=CATALOG_PATH, type=Path)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    with get_session_factory()() as session:
        owner_id = session.scalar(
            select(User.id).where(User.username == args.username).limit(1)
        )
        if owner_id is None:
            raise RuntimeError(f"No user named {args.username!r}")
        changes = organize_restaurant_menus(session, owner_id, catalog)
    print(
        f"added {changes.added}, updated {changes.updated}, "
        f"renamed {changes.renamed}, archived {changes.archived}"
    )


if __name__ == "__main__":
    main()
