"""Load reviewed Vkusno i tochka breakfast items and cached photos for one user."""

from __future__ import annotations

import argparse
import json
from io import BytesIO
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.models import Pattern, PatternAlias, User, utc_now
from glucotracker.infra.db.session import get_session_factory
from glucotracker.infra.storage import pattern_image_store

CATALOG_PATH = Path(__file__).resolve().parents[1] / "catalog_seeds/vit_breakfast.json"
IMAGE_DIR = CATALOG_PATH.parents[3] / "runtime/catalog_seeds/vit_breakfast_images"
IMAGE_SUFFIXES = (".webp", ".png", ".jpg")


def _image_path(image_dir: Path, key: str) -> Path:
    matches = [image_dir / f"{key}{suffix}" for suffix in IMAGE_SUFFIXES]
    existing = [path for path in matches if path.is_file()]
    if len(existing) != 1:
        raise ValueError(f"Expected exactly one cached image for {key}")
    return existing[0]


def seed_vit_breakfast(
    session: Session,
    owner_id: UUID,
    image_dir: Path,
    *,
    catalog_path: Path = CATALOG_PATH,
) -> int:
    """Upsert only this breakfast catalogue, preserving all unrelated patterns."""
    items = json.loads(catalog_path.read_text(encoding="utf-8"))["items"]
    if len({item["key"] for item in items}) != len(items):
        raise ValueError("Duplicate breakfast key")
    images = {item["key"]: _image_path(image_dir, item["key"]) for item in items}
    for item in items:
        grams = float(item["grams"])
        values = [
            float(item[field]) for field in ("carbs_g", "protein_g", "fat_g", "kcal")
        ]
        if grams <= 0 or any(value < 0 for value in values):
            raise ValueError(f"Invalid serving nutrition for {item['key']}")

    for item in items:
        key = str(item["key"])
        row = session.scalar(
            select(Pattern).where(
                Pattern.owner_id == owner_id,
                Pattern.prefix == "vit",
                Pattern.key == key,
            )
        )
        if row is None:
            same_named_row = session.scalar(
                select(Pattern).where(
                    Pattern.owner_id == owner_id,
                    Pattern.prefix == "vit",
                    Pattern.display_name == item["name"],
                    Pattern.is_archived.is_(False),
                )
            )
            if same_named_row is not None:
                # Keep a pre-existing entry, especially verified official nutrition.
                same_named_row.updated_at = utc_now()
                continue
            row = Pattern(owner_id=owner_id, prefix="vit", key=key)
            session.add(row)
        else:
            row.aliases.clear()
            session.flush()
        row.display_name = str(item["name"])
        row.default_grams = grams = float(item["grams"])
        row.default_carbs_g = carbs = float(item["carbs_g"])
        row.default_protein_g = protein = float(item["protein_g"])
        row.default_fat_g = fat = float(item["fat_g"])
        row.default_kcal = kcal = float(item["kcal"])
        row.default_fiber_g = 0
        row.per_100g_carbs_g = round(carbs / grams * 100, 2)
        row.per_100g_protein_g = round(protein / grams * 100, 2)
        row.per_100g_fat_g = round(fat / grams * 100, 2)
        row.per_100g_kcal = round(kcal / grams * 100, 2)
        row.source_url = str(item["source_url"])
        row.source_name = (
            "Вкусно — и точка: сторонний каталог"
            if item["source"] == "third_party_catalog"
            else "Вкусно — и точка: зеркало меню"
        )
        row.source_confidence = str(item["source"])
        row.is_verified = False
        row.is_archived = False
        row.updated_at = utc_now()
        session.flush()
        image = images[key]
        pattern_image_store.save_upload(
            row.id,
            UploadFile(file=BytesIO(image.read_bytes()), filename=image.name),
        )
        row.image_url = f"/patterns/{row.id}/image/file"
        row.aliases = [
            PatternAlias(alias=f"ВиТ {row.display_name}"),
            PatternAlias(alias=f"Вкусно и точка {row.display_name}"),
        ]
    session.commit()
    return len(items)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-dir", default=IMAGE_DIR, type=Path)
    parser.add_argument("--username", required=True)
    args = parser.parse_args()
    with get_session_factory()() as session:
        owner_id = session.scalar(
            select(User.id)
            .where(User.role == UserRole.gluco, User.username == args.username)
            .limit(1)
        )
        if owner_id is None:
            raise RuntimeError(f"No glucose user named {args.username!r}")
        count = seed_vit_breakfast(session, owner_id, args.image_dir)
        print(f"Processed {count} VIT breakfast items for {owner_id}")


if __name__ == "__main__":
    main()
