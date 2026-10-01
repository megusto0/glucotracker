"""Idempotently add the Russian BK Baconizer to the shared product catalogue."""

import argparse
from io import BytesIO
from pathlib import Path

import httpx
from fastapi import UploadFile
from sqlalchemy import select

from glucotracker.infra.db.models import Product, ProductAlias
from glucotracker.infra.db.session import get_session_factory
from glucotracker.infra.storage import product_image_store

IMAGE_SOURCE_URL = (
    "https://burgerkings.ru/image/cache/catalog/photo/739270227-bekonajzer-600x600.jpg"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-file", type=Path)
    args = parser.parse_args()
    with get_session_factory()() as session:
        product = session.scalar(
            select(Product).where(
                Product.owner_id.is_(None),
                Product.brand == "Бургер Кинг",
                Product.name == "Беконайзер",
            )
        )
        if product is None:
            # Russian menu values are consistent across independent catalogues,
            # but no current official Russian nutrition label was available.
            grams = 335.0
            product = Product(
                owner_id=None,
                brand="Бургер Кинг",
                name="Беконайзер",
                default_grams=grams,
                default_serving_text="1 бургер (335 г)",
                carbs_per_serving=50.3,
                protein_per_serving=57.2,
                fat_per_serving=65.7,
                kcal_per_serving=1021.7,
                carbs_per_100g=round(50.3 / grams * 100, 2),
                protein_per_100g=round(57.2 / grams * 100, 2),
                fat_per_100g=round(65.7 / grams * 100, 2),
                kcal_per_100g=round(1021.7 / grams * 100, 2),
                source_kind="manual",  # Displays the verification warning.
                source_url="https://burgerkings.ru/menu/burgery/bekonajzer-47554",
                icon_emoji="🍔",
                category="fast_food",
            )
            product.aliases = [
                ProductAlias(owner_id=None, alias=alias)
                for alias in (
                    "БК Беконайзер",
                    "Беконайзер БК",
                    "Бургер Кинг Беконайзер",
                    "BK Baconizer",
                    "Baconizer",
                )
            ]
            session.add(product)
            session.flush()

        try:
            product_image_store.get_full_path(product.id)
        except product_image_store.ProductImageStorageError:
            if args.image_file is not None:
                image_data = args.image_file.read_bytes()
            else:
                response = httpx.get(
                    IMAGE_SOURCE_URL, follow_redirects=True, timeout=15
                )
                response.raise_for_status()
                image_data = response.content
            if not image_data.startswith(b"\xff\xd8\xff"):
                raise ValueError("Baconizer image is not JPEG") from None
            product_image_store.save_upload(
                product.id,
                UploadFile(file=BytesIO(image_data), filename="baconizer.jpg"),
            )

        product.image_url = f"/products/{product.id}/image/file"
        session.commit()
        print(f"Baconizer with local image: {product.id}")


if __name__ == "__main__":
    main()
