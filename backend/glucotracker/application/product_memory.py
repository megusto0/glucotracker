"""Application service for remembering confirmed label items as products."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from glucotracker.api.schemas import ProductResponse
from glucotracker.domain.entities import ItemSourceKind
from glucotracker.infra.db.models import (
    MealItem,
    Photo,
    Product,
    ProductAlias,
    utc_now,
)
from glucotracker.infra.db.product_merge import merge_duplicate_source_photo_products


class ProductMemoryService:
    """Coordinate product upserts created from accepted label-calculated items."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def remember_items(self, items: list[MealItem]) -> None:
        """Persist all eligible accepted label items into local product memory."""
        for item in items:
            self._remember_label_item_as_product(item)

    def remember_item(
        self,
        item: MealItem,
        aliases: list[str] | None = None,
    ) -> Product:
        """Persist one eligible label item and attach it back to the meal item."""
        product = self._remember_label_item_as_product(item)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Meal item does not contain enough label data to remember.",
            )
        self.merge_aliases(product, aliases or [])
        product.updated_at = utc_now()
        self.session.flush()
        return product

    def merge_aliases(self, product: Product, aliases: list[str]) -> None:
        """Append aliases while preserving existing user-entered aliases."""
        existing = {alias.alias.casefold() for alias in product.aliases}
        for alias in aliases:
            normalized = alias.strip()
            if not normalized or normalized.casefold() in existing:
                continue
            product.aliases.append(ProductAlias(alias=normalized))
            existing.add(normalized.casefold())

    def response(self, product: Product) -> ProductResponse:
        """Convert a product row into an API response."""
        return ProductResponse.model_validate(
            {
                "id": product.id,
                "barcode": product.barcode,
                "brand": product.brand,
                "name": product.name,
                "default_grams": product.default_grams,
                "default_serving_text": product.default_serving_text,
                "carbs_per_100g": product.carbs_per_100g,
                "protein_per_100g": product.protein_per_100g,
                "fat_per_100g": product.fat_per_100g,
                "fiber_per_100g": product.fiber_per_100g,
                "kcal_per_100g": product.kcal_per_100g,
                "carbs_per_serving": product.carbs_per_serving,
                "protein_per_serving": product.protein_per_serving,
                "fat_per_serving": product.fat_per_serving,
                "fiber_per_serving": product.fiber_per_serving,
                "kcal_per_serving": product.kcal_per_serving,
                "source_kind": product.source_kind,
                "source_url": product.source_url,
                "image_url": product.image_url,
                "nutrients_json": product.nutrients_json,
                "usage_count": product.usage_count,
                "last_used_at": product.last_used_at,
                "created_at": product.created_at,
                "updated_at": product.updated_at,
                "aliases": [alias.alias for alias in product.aliases],
            }
        )

    @staticmethod
    def _as_float(value: object) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _item_evidence(item: MealItem) -> dict:
        return item.evidence if isinstance(item.evidence, dict) else {}

    @staticmethod
    def _photo_file_url(photo_id: UUID | None) -> str | None:
        return f"/photos/{photo_id}/file" if photo_id is not None else None

    def _first_meal_photo_url(self, meal_id: UUID) -> str | None:
        photo_id = self.session.scalar(
            select(Photo.id)
            .where(Photo.meal_id == meal_id)
            .order_by(Photo.created_at.asc(), Photo.id.asc())
            .limit(1)
        )
        return self._photo_file_url(photo_id)

    def _nutrition_per_100g_from_evidence(
        self,
        item: MealItem,
    ) -> dict[str, float | None]:
        evidence = self._item_evidence(item)
        nutrition_per_100g = evidence.get("nutrition_per_100g")
        if isinstance(nutrition_per_100g, dict):
            return {
                "carbs_per_100g": self._as_float(nutrition_per_100g.get("carbs_g")),
                "protein_per_100g": self._as_float(
                    nutrition_per_100g.get("protein_g")
                ),
                "fat_per_100g": self._as_float(nutrition_per_100g.get("fat_g")),
                "fiber_per_100g": self._as_float(nutrition_per_100g.get("fiber_g")),
                "kcal_per_100g": self._as_float(nutrition_per_100g.get("kcal")),
            }

        extracted_facts = evidence.get("extracted_facts")
        if isinstance(extracted_facts, dict):
            return {
                "carbs_per_100g": self._as_float(
                    extracted_facts.get("carbs_per_100g")
                ),
                "protein_per_100g": self._as_float(
                    extracted_facts.get("protein_per_100g")
                ),
                "fat_per_100g": self._as_float(extracted_facts.get("fat_per_100g")),
                "fiber_per_100g": self._as_float(
                    extracted_facts.get("fiber_per_100g")
                ),
                "kcal_per_100g": self._as_float(extracted_facts.get("kcal_per_100g")),
            }
        return {}

    def _default_label_serving_size(self, item: MealItem) -> float | None:
        evidence = self._item_evidence(item)
        for key in ("net_weight_per_unit_g", "total_weight_g"):
            value = self._as_float(evidence.get(key))
            if value is not None:
                return value

        extracted_facts = evidence.get("extracted_facts")
        if isinstance(extracted_facts, dict):
            for key in (
                "visible_weight_g",
                "assumed_weight_g",
                "visible_volume_ml",
                "assumed_volume_ml",
            ):
                value = self._as_float(extracted_facts.get(key))
                if value is not None:
                    return value
        return item.grams

    @staticmethod
    def _per_serving_label_values(
        item: MealItem,
        nutrition_per_100g: dict[str, float | None],
        default_grams: float | None,
    ) -> dict[str, float | None]:
        if default_grams is None or not any(
            value is not None for value in nutrition_per_100g.values()
        ):
            return {
                "carbs_per_serving": item.carbs_g,
                "protein_per_serving": item.protein_g,
                "fat_per_serving": item.fat_g,
                "fiber_per_serving": item.fiber_g,
                "kcal_per_serving": item.kcal,
            }

        scale = default_grams / 100
        return {
            "carbs_per_serving": (
                round(nutrition_per_100g["carbs_per_100g"] * scale, 1)
                if nutrition_per_100g.get("carbs_per_100g") is not None
                else None
            ),
            "protein_per_serving": (
                round(nutrition_per_100g["protein_per_100g"] * scale, 1)
                if nutrition_per_100g.get("protein_per_100g") is not None
                else None
            ),
            "fat_per_serving": (
                round(nutrition_per_100g["fat_per_100g"] * scale, 1)
                if nutrition_per_100g.get("fat_per_100g") is not None
                else None
            ),
            "fiber_per_serving": (
                round(nutrition_per_100g["fiber_per_100g"] * scale, 1)
                if nutrition_per_100g.get("fiber_per_100g") is not None
                else None
            ),
            "kcal_per_serving": (
                round(nutrition_per_100g["kcal_per_100g"] * scale)
                if nutrition_per_100g.get("kcal_per_100g") is not None
                else None
            ),
        }

    @staticmethod
    def _label_product_aliases(item: MealItem) -> list[str]:
        aliases = [item.name, item.name.casefold()]
        if item.brand:
            aliases.append(f"{item.brand} {item.name}")
            aliases.append(f"{item.brand} {item.name}".casefold())
        lowered = item.name.casefold()
        if "сырок" in lowered:
            aliases.extend(["сырок", "глазированный сырок", "творожный сырок"])
        if "бисквит" in lowered and (
            "сэндвич" in lowered or "сандвич" in lowered
        ):
            aliases.extend(["бисквит", "бисквит-сэндвич", "сэндвич"])
        return aliases

    @staticmethod
    def _nutrients_json_from_item(item: MealItem) -> dict:
        return {
            nutrient.nutrient_code: {
                "amount": nutrient.amount,
                "unit": nutrient.unit,
                "source_kind": nutrient.source_kind,
                "confidence": nutrient.confidence,
                "evidence_json": nutrient.evidence_json,
                "assumptions_json": nutrient.assumptions_json,
            }
            for nutrient in item.nutrients
        }

    def _find_existing_label_product(self, item: MealItem) -> Product | None:
        if item.product_id is not None:
            product = self.session.scalar(
                select(Product)
                .where(Product.id == item.product_id)
                .options(selectinload(Product.aliases))
            )
            if product is not None:
                return product

        evidence = self._item_evidence(item)
        barcode = evidence.get("identified_barcode")
        if barcode:
            product = self.session.scalar(
                select(Product)
                .where(Product.barcode == str(barcode))
                .options(selectinload(Product.aliases))
            )
            if product is not None:
                return product

        image_url = self._photo_file_url(item.photo_id) or self._first_meal_photo_url(
            item.meal_id
        )
        if image_url:
            product = self.session.scalar(
                select(Product)
                .where(Product.image_url == image_url)
                .options(selectinload(Product.aliases))
            )
            if product is not None:
                return product

        if not item.name.strip():
            return None
        filters = [Product.name == item.name]
        if item.brand is None:
            filters.append(Product.brand.is_(None))
        else:
            filters.append(Product.brand == item.brand)
        return self.session.scalar(
            select(Product).where(*filters).options(selectinload(Product.aliases))
        )

    def _remember_label_item_as_product(self, item: MealItem) -> Product | None:
        is_label_item = item.source_kind == ItemSourceKind.label_calc or (
            item.calculation_method or ""
        ).startswith("label_")
        if not is_label_item or not item.name.strip():
            return None

        nutrition_per_100g = self._nutrition_per_100g_from_evidence(item)
        default_grams = self._default_label_serving_size(item)
        serving_values = self._per_serving_label_values(
            item,
            nutrition_per_100g,
            default_grams,
        )
        evidence = self._item_evidence(item)
        barcode = evidence.get("identified_barcode")
        nutrients_json = self._nutrients_json_from_item(item)
        image_url = self._photo_file_url(item.photo_id) or self._first_meal_photo_url(
            item.meal_id
        )
        product = self._find_existing_label_product(item)

        product_values = {
            "barcode": str(barcode) if barcode else None,
            "brand": item.brand,
            "name": item.name,
            "default_grams": default_grams,
            "default_serving_text": (
                "1 упаковка"
                if evidence.get("net_weight_per_unit_g") is not None
                else item.serving_text
            ),
            **nutrition_per_100g,
            **serving_values,
            "source_kind": "label_calc",
            "image_url": image_url,
            "nutrients_json": nutrients_json,
        }

        if product is None:
            product = Product(
                **{
                    key: value
                    for key, value in product_values.items()
                    if value is not None
                    or key in {"name", "source_kind", "nutrients_json"}
                }
            )
            self.session.add(product)
        else:
            for key, value in product_values.items():
                if value is not None or key in {"name", "source_kind"}:
                    setattr(product, key, value)
            if image_url and not product.image_url:
                product.image_url = image_url
            if nutrients_json:
                product.nutrients_json = nutrients_json
            product.updated_at = utc_now()

        self.merge_aliases(product, self._label_product_aliases(item))
        self.session.flush()
        item.product_id = product.id
        merge_duplicate_source_photo_products(self.session, product)
        return product
