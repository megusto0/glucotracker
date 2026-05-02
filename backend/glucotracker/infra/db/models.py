"""SQLAlchemy 2.0 declarative models for the Glucotracker data model."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from glucotracker.domain.entities import (
    ItemSourceKind,
    MealSource,
    MealStatus,
    NightscoutSyncStatus,
    PhotoReferenceKind,
    PhotoScenario,
)
from glucotracker.infra.db.base import Base


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp for ORM-side defaults."""
    return datetime.now(UTC)


def enum_column(enum_type: type, name: str, **kwargs: Any) -> Mapped[Any]:
    """Create an enum column storing enum values for SQLite portability."""
    return mapped_column(
        SAEnum(
            enum_type,
            name=name,
            native_enum=False,
            values_callable=lambda values: [item.value for item in values],
        ),
        **kwargs,
    )


class TimestampMixin:
    """Created and updated timestamps for mutable records."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


class Meal(Base, TimestampMixin):
    """Meal journal entry whose totals are calculated by the backend."""

    __tablename__ = "meals"
    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_meals_confidence_range",
        ),
        Index("ix_meals_eaten_at", "eaten_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    eaten_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[MealStatus] = enum_column(
        MealStatus,
        "meal_status",
        default=MealStatus.draft,
        server_default=MealStatus.draft.value,
        nullable=False,
    )
    source: Mapped[MealSource] = enum_column(MealSource, "meal_source", nullable=False)
    total_carbs_g: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    total_protein_g: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    total_fat_g: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    total_fiber_g: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    total_kcal: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    nightscout_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    nightscout_id: Mapped[str | None] = mapped_column(String, nullable=True)
    nightscout_sync_status: Mapped[NightscoutSyncStatus] = enum_column(
        NightscoutSyncStatus,
        "nightscout_sync_status",
        default=NightscoutSyncStatus.not_synced,
        server_default=NightscoutSyncStatus.not_synced.value,
        nullable=False,
    )
    nightscout_sync_error: Mapped[str | None] = mapped_column(String, nullable=True)
    nightscout_last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    items: Mapped[list[MealItem]] = relationship(
        back_populates="meal",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MealItem.position",
    )
    photos: Mapped[list[Photo]] = relationship(
        back_populates="meal",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    ai_runs: Mapped[list[AIRun]] = relationship(
        back_populates="meal",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def thumbnail_url(self) -> str | None:
        """Return the best image URL for compact meal rows."""
        if self.photos:
            return f"/photos/{self.photos[0].id}/file"

        for item in self.items:
            if item.photo_id:
                return f"/photos/{item.photo_id}/file"
            if item.image_url:
                return item.image_url
            if item.source_image_url:
                return item.source_image_url
        return None


class MealItem(Base, TimestampMixin):
    """Single food item attached to a meal."""

    __tablename__ = "meal_items"
    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_meal_items_confidence_range",
        ),
        Index("ix_meal_items_meal_id", "meal_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    meal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("meals.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    brand: Mapped[str | None] = mapped_column(String, nullable=True)
    grams: Mapped[float | None] = mapped_column(Float, nullable=True)
    serving_text: Mapped[str | None] = mapped_column(String, nullable=True)
    carbs_g: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    protein_g: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    fat_g: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    fiber_g: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    kcal: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    source_kind: Mapped[ItemSourceKind] = enum_column(
        ItemSourceKind,
        "item_source_kind",
        nullable=False,
    )
    calculation_method: Mapped[str | None] = mapped_column(String, nullable=True)
    assumptions: Mapped[list[Any]] = mapped_column(
        JSON,
        default=list,
        server_default=text("'[]'"),
        nullable=False,
    )
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    warnings: Mapped[list[Any]] = mapped_column(
        JSON,
        default=list,
        server_default=text("'[]'"),
        nullable=False,
    )
    pattern_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("patterns.id"),
        nullable=True,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("products.id"),
        nullable=True,
    )
    photo_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("photos.id"),
        nullable=True,
    )
    position: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )

    meal: Mapped[Meal] = relationship(back_populates="items")
    pattern: Mapped[Pattern | None] = relationship(back_populates="items")
    product: Mapped[Product | None] = relationship(back_populates="items")
    photo: Mapped[Photo | None] = relationship(back_populates="items")
    nutrients: Mapped[list[MealItemNutrient]] = relationship(
        back_populates="meal_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MealItemNutrient.nutrient_code",
    )

    @property
    def image_url(self) -> str | None:
        """Return the image inherited from the referenced source item."""
        return self.source_image_url

    @property
    def image_cache_path(self) -> str | None:
        """Reserved for future local cached product/pattern image paths."""
        return None

    @property
    def source_image_url(self) -> str | None:
        """Return the linked pattern or product image URL when available."""
        if self.pattern is not None and self.pattern.image_url:
            return self.pattern.image_url
        if self.product is not None and self.product.image_url:
            return self.product.image_url
        return None


class NutrientDefinition(Base):
    """Extensible nutrient catalog used by optional per-item nutrients."""

    __tablename__ = "nutrient_definitions"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    unit: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )

    item_nutrients: Mapped[list[MealItemNutrient]] = relationship(
        back_populates="definition"
    )


class MealItemNutrient(Base, TimestampMixin):
    """Optional nutrient amount attached to one meal item."""

    __tablename__ = "meal_item_nutrients"
    __table_args__ = (
        UniqueConstraint(
            "meal_item_id",
            "nutrient_code",
            name="uq_meal_item_nutrients_item_code",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_meal_item_nutrients_confidence_range",
        ),
        Index("ix_meal_item_nutrients_meal_item_id", "meal_item_id"),
        Index("ix_meal_item_nutrients_nutrient_code", "nutrient_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    meal_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("meal_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    nutrient_code: Mapped[str] = mapped_column(
        String,
        ForeignKey("nutrient_definitions.code"),
        nullable=False,
    )
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String, nullable=False)
    source_kind: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    assumptions_json: Mapped[list[Any]] = mapped_column(
        JSON,
        default=list,
        server_default=text("'[]'"),
        nullable=False,
    )

    meal_item: Mapped[MealItem] = relationship(back_populates="nutrients")
    definition: Mapped[NutrientDefinition] = relationship(
        back_populates="item_nutrients"
    )


class Photo(Base):
    """Uploaded photo associated with a meal draft or accepted meal."""

    __tablename__ = "photos"
    __table_args__ = (Index("ix_photos_meal_id", "meal_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    meal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("meals.id", ondelete="CASCADE"),
        nullable=False,
    )
    path: Mapped[str] = mapped_column(String, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String, nullable=True)
    taken_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    scenario: Mapped[PhotoScenario] = enum_column(
        PhotoScenario,
        "photo_scenario",
        default=PhotoScenario.unknown,
        server_default=PhotoScenario.unknown.value,
        nullable=False,
    )
    has_reference_object: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False,
    )
    reference_kind: Mapped[PhotoReferenceKind] = enum_column(
        PhotoReferenceKind,
        "photo_reference_kind",
        default=PhotoReferenceKind.none,
        server_default=PhotoReferenceKind.none.value,
        nullable=False,
    )
    gemini_response_raw: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )

    meal: Mapped[Meal] = relationship(back_populates="photos")
    items: Mapped[list[MealItem]] = relationship(back_populates="photo")


class Pattern(Base, TimestampMixin):
    """Reusable meal item pattern keyed by prefix and key."""

    __tablename__ = "patterns"
    __table_args__ = (
        UniqueConstraint("prefix", "key", name="uq_patterns_prefix_key"),
        Index("ix_patterns_prefix", "prefix"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    prefix: Mapped[str] = mapped_column(String, nullable=False)
    key: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    default_grams: Mapped[float | None] = mapped_column(Float, nullable=True)
    default_carbs_g: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    default_protein_g: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    default_fat_g: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    default_fiber_g: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    default_kcal: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    per_100g_kcal: Mapped[float | None] = mapped_column(Float, nullable=True)
    per_100g_carbs_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    per_100g_protein_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    per_100g_fat_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String, nullable=True)
    source_file: Mapped[str | None] = mapped_column(String, nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_confidence: Mapped[str | None] = mapped_column(String, nullable=True)
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False,
    )
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    nutrients_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    usage_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False,
    )

    aliases: Mapped[list[PatternAlias]] = relationship(
        back_populates="pattern",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    items: Mapped[list[MealItem]] = relationship(back_populates="pattern")


class PatternAlias(Base):
    """Alternate lookup text for a meal pattern."""

    __tablename__ = "pattern_aliases"
    __table_args__ = (
        UniqueConstraint(
            "pattern_id",
            "alias",
            name="uq_pattern_aliases_pattern_alias",
        ),
        Index("ix_pattern_aliases_pattern_id", "pattern_id"),
        Index("ix_pattern_aliases_alias", "alias"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    pattern_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("patterns.id", ondelete="CASCADE"),
        nullable=False,
    )
    alias: Mapped[str] = mapped_column(String, nullable=False)

    pattern: Mapped[Pattern] = relationship(back_populates="aliases")


class Product(Base, TimestampMixin):
    """Known packaged or database-backed product."""

    __tablename__ = "products"
    __table_args__ = (Index("ix_products_barcode", "barcode"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    barcode: Mapped[str | None] = mapped_column(String, nullable=True)
    brand: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    default_grams: Mapped[float | None] = mapped_column(Float, nullable=True)
    default_serving_text: Mapped[str | None] = mapped_column(String, nullable=True)
    carbs_per_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    protein_per_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fat_per_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fiber_per_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    kcal_per_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    carbs_per_serving: Mapped[float | None] = mapped_column(Float, nullable=True)
    protein_per_serving: Mapped[float | None] = mapped_column(Float, nullable=True)
    fat_per_serving: Mapped[float | None] = mapped_column(Float, nullable=True)
    fiber_per_serving: Mapped[float | None] = mapped_column(Float, nullable=True)
    kcal_per_serving: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_kind: Mapped[str] = mapped_column(
        String,
        default="manual",
        server_default="manual",
        nullable=False,
    )
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    nutrients_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    usage_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    aliases: Mapped[list[ProductAlias]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    items: Mapped[list[MealItem]] = relationship(back_populates="product")


class ProductAlias(Base):
    """Alternate lookup text for a product."""

    __tablename__ = "product_aliases"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "alias",
            name="uq_product_aliases_product_alias",
        ),
        Index("ix_product_aliases_product_id", "product_id"),
        Index("ix_product_aliases_alias", "alias"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    alias: Mapped[str] = mapped_column(String, nullable=False)

    product: Mapped[Product] = relationship(back_populates="aliases")


class DailyTotal(Base):
    """Daily aggregate maintained from accepted backend meal totals."""

    __tablename__ = "daily_totals"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    kcal: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    carbs_g: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    protein_g: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    fat_g: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    fiber_g: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    meal_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    estimated_item_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    exact_item_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


class NightscoutSettings(Base, TimestampMixin):
    """Server-side Nightscout connection and display settings."""

    __tablename__ = "nightscout_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False,
    )
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    api_secret: Mapped[str | None] = mapped_column(String, nullable=True)
    sync_glucose: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="1",
        nullable=False,
    )
    show_glucose_in_journal: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="1",
        nullable=False,
    )
    import_insulin_events: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="1",
        nullable=False,
    )
    allow_meal_send: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="1",
        nullable=False,
    )
    confirm_before_send: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="1",
        nullable=False,
    )
    autosend_meals: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False,
    )
    last_status_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)


class NightscoutGlucoseEntry(Base, TimestampMixin):
    """Locally cached read-only CGM entry imported from Nightscout."""

    __tablename__ = "nightscout_glucose_entries"
    __table_args__ = (
        UniqueConstraint("source_key", name="uq_nightscout_glucose_source_key"),
        Index("ix_nightscout_glucose_timestamp", "timestamp"),
        Index("ix_nightscout_glucose_nightscout_id", "nightscout_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_key: Mapped[str] = mapped_column(String, nullable=False)
    nightscout_id: Mapped[str | None] = mapped_column(String, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value_mmol_l: Mapped[float] = mapped_column(Float, nullable=False)
    value_mg_dl: Mapped[float | None] = mapped_column(Float, nullable=True)
    trend: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


class NightscoutInsulinEvent(Base, TimestampMixin):
    """Locally cached read-only insulin treatment imported from Nightscout."""

    __tablename__ = "nightscout_insulin_events"
    __table_args__ = (
        UniqueConstraint("source_key", name="uq_nightscout_insulin_source_key"),
        Index("ix_nightscout_insulin_timestamp", "timestamp"),
        Index("ix_nightscout_insulin_nightscout_id", "nightscout_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_key: Mapped[str] = mapped_column(String, nullable=False)
    nightscout_id: Mapped[str | None] = mapped_column(String, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    insulin_units: Mapped[float | None] = mapped_column(Float, nullable=True)
    event_type: Mapped[str | None] = mapped_column(String, nullable=True)
    insulin_type: Mapped[str | None] = mapped_column(String, nullable=True)
    entered_by: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


class NightscoutImportState(Base):
    """Singleton import watermark for local Nightscout context cache."""

    __tablename__ = "nightscout_import_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_glucose_import_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_insulin_import_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


class SensorSession(Base, TimestampMixin):
    """A user-defined CGM sensor wear session for display analytics."""

    __tablename__ = "sensor_sessions"
    __table_args__ = (
        Index("ix_sensor_sessions_started_at", "started_at"),
        Index("ix_sensor_sessions_ended_at", "ended_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(
        String,
        default="manual",
        server_default="manual",
        nullable=False,
    )
    vendor: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expected_life_days: Mapped[float] = mapped_column(
        Float,
        default=15,
        server_default="15",
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    calibration_models: Mapped[list[CgmCalibrationModel]] = relationship(
        back_populates="sensor_session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CgmCalibrationModel.created_at.desc()",
    )


class FingerstickReading(Base):
    """Manual capillary glucose reading used for display calibration analytics."""

    __tablename__ = "fingerstick_readings"
    __table_args__ = (Index("ix_fingerstick_readings_measured_at", "measured_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    glucose_mmol_l: Mapped[float] = mapped_column(Float, nullable=False)
    meter_name: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


class CgmCalibrationModel(Base):
    """Persisted display-only calibration model for a sensor session."""

    __tablename__ = "cgm_calibration_models"
    __table_args__ = (
        Index("ix_cgm_calibration_models_sensor", "sensor_session_id"),
        Index("ix_cgm_calibration_models_active", "active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    sensor_session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("sensor_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_version: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    params_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    metrics_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    confidence: Mapped[str] = mapped_column(
        String,
        default="low",
        server_default="low",
        nullable=False,
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="1",
        nullable=False,
    )

    sensor_session: Mapped[SensorSession] = relationship(
        back_populates="calibration_models"
    )


class AIRun(Base):
    """Recorded AI request and response payload for a meal."""

    __tablename__ = "ai_runs"
    __table_args__ = (Index("ix_ai_runs_meal_id", "meal_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    meal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("meals.id", ondelete="CASCADE"),
        nullable=False,
    )
    model: Mapped[str] = mapped_column(String, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String, nullable=False)
    request_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    response_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    provider: Mapped[str] = mapped_column(
        String,
        default="gemini",
        server_default="gemini",
        nullable=False,
    )
    model_requested: Mapped[str | None] = mapped_column(String, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String, nullable=True)
    fallback_used: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String,
        default="success",
        server_default="success",
        nullable=False,
    )
    request_type: Mapped[str] = mapped_column(
        String,
        default="initial_estimate",
        server_default="initial_estimate",
        nullable=False,
    )
    source_photo_ids: Mapped[list[Any]] = mapped_column(
        JSON,
        default=list,
        server_default=text("'[]'"),
        nullable=False,
    )
    normalized_items_json: Mapped[list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    error_history_json: Mapped[list[Any]] = mapped_column(
        JSON,
        default=list,
        server_default=text("'[]'"),
        nullable=False,
    )
    promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    promoted_by_action: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )

    meal: Mapped[Meal] = relationship(back_populates="ai_runs")


class UserProfile(Base, TimestampMixin):
    """Singleton row with user body metrics for BMR/TDEE calculation."""

    __tablename__ = "user_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    age_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sex: Mapped[str | None] = mapped_column(String(6), nullable=True)
    activity_level: Mapped[str] = mapped_column(
        String(16),
        default="moderate",
        server_default="moderate",
        nullable=False,
    )


class DailyActivity(Base):
    """Daily activity data synced from wearable (Gadgetbridge)."""

    __tablename__ = "daily_activity"
    __table_args__ = (Index("ix_daily_activity_date", "date"),)

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    steps: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    active_minutes: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    kcal_burned: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    heart_rate_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    heart_rate_rest: Mapped[float | None] = mapped_column(Float, nullable=True)
    hr_samples: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    hr_active_minutes: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    kcal_hr_active: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    kcal_steps: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    kcal_no_move_hr: Mapped[float] = mapped_column(
        Float,
        default=0,
        server_default="0",
        nullable=False,
    )
    calorie_confidence: Mapped[str] = mapped_column(
        String(16),
        default="none",
        server_default="none",
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(32),
        default="gadgetbridge",
        server_default="gadgetbridge",
        nullable=False,
    )
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
