"""Pydantic request and response schemas for the REST API."""

from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as date_type
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from glucotracker.domain.entities import (
    ItemSourceKind,
    MealSource,
    MealStatus,
    PhotoReferenceKind,
    PhotoScenario,
)


def now_utc() -> datetime:
    """Return the default eaten-at timestamp for API-created meals."""
    return datetime.now(UTC)


class HealthResponse(BaseModel):
    """Service health response."""

    status: str = Field(examples=["ok"])
    version: str = Field(examples=["0.1.0"])
    db: str = Field(examples=["ok"])


class DeleteResponse(BaseModel):
    """Generic delete response."""

    deleted: bool = Field(examples=[True])


class NutrientInput(BaseModel):
    """Optional nutrient input attached to a meal item or seed record."""

    amount: float | None = Field(default=None, ge=0, examples=[120])
    unit: str | None = Field(default=None, examples=["mg"])
    source_kind: str | None = Field(default=None, examples=["manual"])
    confidence: float | None = Field(default=None, ge=0, le=1, examples=[0.95])
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    assumptions_json: list[Any] = Field(default_factory=list)


class NutrientDefinitionResponse(BaseModel):
    """Nutrient catalog entry response."""

    code: str
    display_name: str
    unit: str
    category: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MealItemNutrientResponse(BaseModel):
    """Stored optional nutrient amount for a meal item."""

    id: UUID
    meal_item_id: UUID
    nutrient_code: str
    amount: float | None = None
    unit: str
    source_kind: str
    confidence: float | None = None
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    assumptions_json: list[Any] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MealItemBase(BaseModel):
    """Shared meal item fields."""

    name: str = Field(examples=["Greek yogurt"])
    brand: str | None = Field(default=None, examples=["Local Dairy"])
    grams: float | None = Field(default=None, ge=0, examples=[150])
    serving_text: str | None = Field(default=None, examples=["1 cup"])
    carbs_g: float = Field(default=0, ge=0, examples=[8])
    protein_g: float = Field(default=0, ge=0, examples=[15])
    fat_g: float = Field(default=0, ge=0, examples=[4])
    fiber_g: float = Field(default=0, ge=0, examples=[0])
    kcal: float = Field(default=0, ge=0, examples=[128])
    confidence: float | None = Field(default=None, ge=0, le=1, examples=[0.9])
    confidence_reason: str | None = Field(default=None, examples=["Label values"])
    source_kind: ItemSourceKind = Field(default=ItemSourceKind.manual)
    calculation_method: str | None = Field(default=None, examples=["manual"])
    assumptions: list[Any] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    warnings: list[Any] = Field(default_factory=list)
    pattern_id: UUID | None = None
    product_id: UUID | None = None
    photo_id: UUID | None = None
    position: int = Field(default=0, ge=0, examples=[0])
    nutrients: dict[str, NutrientInput | float | None] = Field(default_factory=dict)


class MealItemCreate(MealItemBase):
    """Create a meal item."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Greek yogurt",
                    "brand": "Local Dairy",
                    "grams": 150,
                    "carbs_g": 8,
                    "protein_g": 15,
                    "fat_g": 4,
                    "fiber_g": 0,
                    "kcal": 128,
                    "source_kind": "manual",
                    "calculation_method": "manual",
                    "assumptions": [],
                    "evidence": {},
                    "warnings": [],
                    "position": 0,
                }
            ]
        }
    )


class MealItemPatch(BaseModel):
    """Patch a meal item."""

    name: str | None = None
    brand: str | None = None
    grams: float | None = Field(default=None, ge=0)
    serving_text: str | None = None
    carbs_g: float | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)
    fiber_g: float | None = Field(default=None, ge=0)
    kcal: float | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    confidence_reason: str | None = None
    source_kind: ItemSourceKind | None = None
    calculation_method: str | None = None
    assumptions: list[Any] | None = None
    evidence: dict[str, Any] | None = None
    warnings: list[Any] | None = None
    pattern_id: UUID | None = None
    product_id: UUID | None = None
    photo_id: UUID | None = None
    position: int | None = Field(default=None, ge=0)
    nutrients: dict[str, NutrientInput | float | None] | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "grams": 180,
                    "carbs_g": 9.6,
                    "protein_g": 18,
                    "fat_g": 4.8,
                    "kcal": 154,
                }
            ]
        }
    )


class MealItemResponse(MealItemBase):
    """Meal item response."""

    id: UUID
    meal_id: UUID
    image_url: str | None = None
    image_cache_path: str | None = None
    source_image_url: str | None = None
    created_at: datetime
    updated_at: datetime
    nutrients: list[MealItemNutrientResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PhotoResponse(BaseModel):
    """Photo response embedded in meal detail responses."""

    id: UUID
    meal_id: UUID
    path: str
    original_filename: str | None = None
    content_type: str | None = None
    taken_at: datetime | None = None
    scenario: PhotoScenario
    has_reference_object: bool
    reference_kind: PhotoReferenceKind
    gemini_response_raw: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MealBase(BaseModel):
    """Shared meal fields."""

    eaten_at: datetime = Field(default_factory=now_utc)
    title: str | None = Field(default=None, examples=["Breakfast"])
    note: str | None = Field(default=None, examples=["Post-run meal"])
    status: MealStatus | None = None
    source: MealSource = Field(examples=["manual"])


class MealCreate(MealBase):
    """Create a meal with optional inline items."""

    items: list[MealItemCreate] = Field(default_factory=list)

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "eaten_at": "2026-04-28T08:30:00Z",
                    "title": "Breakfast",
                    "note": "Manual entry",
                    "source": "manual",
                    "items": [
                        {
                            "name": "Greek yogurt",
                            "grams": 150,
                            "carbs_g": 8,
                            "protein_g": 15,
                            "fat_g": 4,
                            "fiber_g": 0,
                            "kcal": 128,
                            "source_kind": "manual",
                        }
                    ],
                }
            ]
        }
    )


class MealPatch(BaseModel):
    """Patch editable meal fields."""

    eaten_at: datetime | None = None
    title: str | None = None
    note: str | None = None
    status: MealStatus | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"title": "Updated breakfast", "note": "Corrected note"}]
        }
    )


class MealAcceptRequest(BaseModel):
    """Accept a draft by replacing its items atomically."""

    items: list[MealItemCreate] = Field(default_factory=list)

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "name": "Pasta",
                            "grams": 220,
                            "carbs_g": 68,
                            "protein_g": 12,
                            "fat_g": 5,
                            "fiber_g": 4,
                            "kcal": 365,
                            "source_kind": "photo_estimate",
                            "confidence": 0.72,
                        }
                    ]
                }
            ]
        }
    )


class EstimateMealRequest(BaseModel):
    """Optional local context to include in a photo estimation request."""

    use_patterns: list[UUID] = Field(default_factory=list)
    use_products: list[UUID] = Field(default_factory=list)
    context_note: str | None = Field(
        default=None,
        max_length=1200,
        description=(
            "User-provided context for the photos, such as known component "
            "weights or corrections. This is evidence for Gemini, not "
            "authoritative macro math."
        ),
    )
    model: Literal[
        "default",
        "gemini-3-flash-preview",
        "gemini-2.5-flash",
        "gemini-3.1-flash-lite-preview",
    ] = Field(default="default")
    scenario_hint: (
        Literal[
            "LABEL_FULL",
            "LABEL_PARTIAL",
            "PLATED",
            "BARCODE",
            "UNKNOWN",
        ]
        | None
    ) = Field(default=None)

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "use_patterns": [],
                    "use_products": [],
                    "context_note": "100 г варёного риса на тарелке",
                    "model": "default",
                    "scenario_hint": "PLATED",
                }
            ]
        }
    )


class MealTotalsResponse(BaseModel):
    """Backend-calculated meal totals."""

    total_carbs_g: float = Field(examples=[42])
    total_protein_g: float = Field(examples=[18])
    total_fat_g: float = Field(examples=[12])
    total_fiber_g: float = Field(examples=[5])
    total_kcal: float = Field(examples=[348])


class EstimateSourcePhotoResponse(BaseModel):
    """Source photo reference for an estimation response."""

    id: UUID
    index: int
    url: str
    thumbnail_url: str
    original_filename: str | None = None


class EstimateMacroBreakdown(BaseModel):
    """Macro/kcal values used in an estimation calculation breakdown."""

    carbs_g: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    kcal: float | None = None


class EstimateCalculationBreakdown(BaseModel):
    """Readable backend-prepared calculation evidence for one suggested item."""

    position: int
    name: str
    count_detected: int | None = None
    net_weight_per_unit_g: float | None = None
    total_weight_g: float | None = None
    nutrition_per_100g: EstimateMacroBreakdown | None = None
    calculated_per_unit: EstimateMacroBreakdown | None = None
    calculated_total: EstimateMacroBreakdown
    calculation_steps: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class EstimateCreatedDraftResponse(BaseModel):
    """One draft journal row created from an estimated item."""

    meal_id: UUID
    title: str
    source_photo_id: UUID | None = None
    thumbnail_url: str | None = None
    item: MealItemCreate
    totals: MealTotalsResponse


class EstimateMealResponse(BaseModel):
    """Photo estimation response containing draft item suggestions."""

    meal_id: UUID
    source_photos: list[EstimateSourcePhotoResponse] = Field(default_factory=list)
    suggested_items: list[MealItemCreate]
    suggested_totals: MealTotalsResponse
    calculation_breakdowns: list[EstimateCalculationBreakdown] = Field(
        default_factory=list
    )
    gemini_notes: str
    image_quality_warnings: list[str]
    reference_detected: PhotoReferenceKind
    ai_run_id: UUID
    raw_gemini_response: dict[str, Any] | None = None
    created_drafts: list[EstimateCreatedDraftResponse] = Field(default_factory=list)

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "meal_id": "11111111-1111-1111-1111-111111111111",
                    "suggested_items": [
                        {
                            "name": "Chocolate bar",
                            "brand": "Example",
                            "grams": 50,
                            "carbs_g": 28,
                            "protein_g": 3,
                            "fat_g": 12,
                            "fiber_g": 2,
                            "kcal": 232,
                            "confidence": 0.92,
                            "confidence_reason": "Full label and weight are visible.",
                            "source_kind": "label_calc",
                            "calculation_method": ("label_visible_weight_backend_calc"),
                            "assumptions": [],
                            "evidence": {"scenario": "LABEL_FULL"},
                            "warnings": [],
                        }
                    ],
                    "suggested_totals": {
                        "total_carbs_g": 28,
                        "total_protein_g": 3,
                        "total_fat_g": 12,
                        "total_fiber_g": 2,
                        "total_kcal": 232,
                    },
                    "gemini_notes": "Nutrition label is readable.",
                    "image_quality_warnings": [],
                    "reference_detected": "none",
                    "ai_run_id": "22222222-2222-2222-2222-222222222222",
                }
            ]
        }
    )


class ReestimateMealRequest(BaseModel):
    """Request a comparison estimate for an existing photo meal."""

    model: Literal[
        "default",
        "gemini-3-flash-preview",
        "gemini-2.5-flash",
        "gemini-3.1-flash-lite-preview",
    ] = Field(default="default")
    mode: Literal["compare"] = Field(default="compare")


class ApplyEstimationRunRequest(BaseModel):
    """Apply a stored re-estimation proposal."""

    apply_mode: Literal["replace_current", "save_as_draft"]


class EstimateDiffTotals(BaseModel):
    """Macro/kcal delta between current and proposed estimates."""

    carbs_delta: float
    protein_delta: float
    fat_delta: float
    fiber_delta: float
    kcal_delta: float


class EstimateItemChange(BaseModel):
    """Item-level change in an estimate comparison."""

    name: str
    current: MealItemCreate | None = None
    proposed: MealItemCreate | None = None


class EstimateComparisonDiff(BaseModel):
    """Structured comparison between current and proposed item lists."""

    totals: EstimateDiffTotals
    added_items: list[EstimateItemChange] = Field(default_factory=list)
    removed_items: list[EstimateItemChange] = Field(default_factory=list)
    changed_items: list[EstimateItemChange] = Field(default_factory=list)
    current_model: str | None = None
    proposed_model: str | None = None
    confidence_delta: float | None = None
    warnings: list[str] = Field(default_factory=list)


class ReestimateMealResponse(BaseModel):
    """Comparison proposal returned by meal re-estimation."""

    meal_id: UUID
    current_items: list[MealItemCreate]
    proposed_items: list[MealItemCreate]
    current_totals: MealTotalsResponse
    proposed_totals: MealTotalsResponse
    diff: EstimateComparisonDiff
    ai_run_id: UUID
    model_used: str
    fallback_used: bool
    image_quality_warnings: list[str] = Field(default_factory=list)


class ApplyEstimationRunResponse(BaseModel):
    """Result of applying a re-estimation proposal."""

    apply_mode: Literal["replace_current", "save_as_draft"]
    meal: MealResponse
    ai_run_id: UUID


class AIRunResponse(BaseModel):
    """AI estimation run audit row."""

    id: UUID
    meal_id: UUID
    provider: str
    model: str
    model_requested: str | None = None
    model_used: str | None = None
    fallback_used: bool = False
    status: str
    request_type: str
    source_photo_ids: list[Any] = Field(default_factory=list)
    request_summary: dict[str, Any] | None = None
    response_raw: dict[str, Any] | None = None
    normalized_items_json: list[Any] | None = None
    error_history_json: list[Any] = Field(default_factory=list)
    promoted_at: datetime | None = None
    promoted_by_action: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MealResponse(BaseModel):
    """Meal response including backend-calculated totals."""

    id: UUID
    eaten_at: datetime
    title: str | None = None
    note: str | None = None
    status: MealStatus
    source: MealSource
    total_carbs_g: float
    total_protein_g: float
    total_fat_g: float
    total_fiber_g: float
    total_kcal: float
    confidence: float | None = None
    nightscout_synced_at: datetime | None = None
    nightscout_id: str | None = None
    nightscout_sync_status: str = "not_synced"
    nightscout_sync_error: str | None = None
    nightscout_last_attempt_at: datetime | None = None
    thumbnail_url: str | None = None
    created_at: datetime
    updated_at: datetime
    items: list[MealItemResponse] = Field(default_factory=list)
    photos: list[PhotoResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class MealPageResponse(BaseModel):
    """Paginated meal list response."""

    items: list[MealResponse]
    total: int
    limit: int
    offset: int


class ProductBase(BaseModel):
    """Shared product fields."""

    barcode: str | None = Field(default=None, examples=["4601234567890"])
    brand: str | None = Field(default=None, examples=["Example Foods"])
    name: str = Field(examples=["Whole grain crackers"])
    default_grams: float | None = Field(default=None, ge=0, examples=[30])
    default_serving_text: str | None = Field(default=None, examples=["6 crackers"])
    carbs_per_100g: float | None = Field(default=None, ge=0, examples=[62])
    protein_per_100g: float | None = Field(default=None, ge=0, examples=[11])
    fat_per_100g: float | None = Field(default=None, ge=0, examples=[9])
    fiber_per_100g: float | None = Field(default=None, ge=0, examples=[7])
    kcal_per_100g: float | None = Field(default=None, ge=0, examples=[410])
    carbs_per_serving: float | None = Field(default=None, ge=0, examples=[18.6])
    protein_per_serving: float | None = Field(default=None, ge=0, examples=[3.3])
    fat_per_serving: float | None = Field(default=None, ge=0, examples=[2.7])
    fiber_per_serving: float | None = Field(default=None, ge=0, examples=[2.1])
    kcal_per_serving: float | None = Field(default=None, ge=0, examples=[123])
    source_kind: str = Field(default="manual", examples=["manual"])
    source_url: str | None = Field(default=None, examples=["https://example.test"])
    image_url: str | None = Field(
        default=None, examples=["https://example.test/item.png"]
    )
    nutrients_json: dict[str, NutrientInput | float | None] = Field(
        default_factory=dict,
        examples=[{"sodium_mg": {"amount": 220, "unit": "mg"}}],
    )


class ProductCreate(ProductBase):
    """Create a saved packaged food product."""

    aliases: list[str] = Field(default_factory=list, examples=[["crackers"]])

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "barcode": "4601234567890",
                    "brand": "Example Foods",
                    "name": "Whole grain crackers",
                    "default_grams": 30,
                    "default_serving_text": "6 crackers",
                    "carbs_per_100g": 62,
                    "protein_per_100g": 11,
                    "fat_per_100g": 9,
                    "fiber_per_100g": 7,
                    "kcal_per_100g": 410,
                    "source_kind": "manual",
                    "aliases": ["crackers"],
                }
            ]
        }
    )


class ProductPatch(BaseModel):
    """Patch a saved product."""

    barcode: str | None = None
    brand: str | None = None
    name: str | None = None
    default_grams: float | None = Field(default=None, ge=0)
    default_serving_text: str | None = None
    carbs_per_100g: float | None = Field(default=None, ge=0)
    protein_per_100g: float | None = Field(default=None, ge=0)
    fat_per_100g: float | None = Field(default=None, ge=0)
    fiber_per_100g: float | None = Field(default=None, ge=0)
    kcal_per_100g: float | None = Field(default=None, ge=0)
    carbs_per_serving: float | None = Field(default=None, ge=0)
    protein_per_serving: float | None = Field(default=None, ge=0)
    fat_per_serving: float | None = Field(default=None, ge=0)
    fiber_per_serving: float | None = Field(default=None, ge=0)
    kcal_per_serving: float | None = Field(default=None, ge=0)
    source_kind: str | None = None
    source_url: str | None = None
    image_url: str | None = None
    nutrients_json: dict[str, NutrientInput | float | None] | None = None
    aliases: list[str] | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"brand": "Example Foods", "aliases": ["crackers"]}]
        }
    )


class ProductResponse(ProductBase):
    """Product response."""

    id: UUID
    usage_count: int
    last_used_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    aliases: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class RememberProductRequest(BaseModel):
    """Persist an accepted label item into the product database."""

    aliases: list[str] = Field(default_factory=list, examples=[["сырок"]])


class ProductPageResponse(BaseModel):
    """Paginated product list response."""

    items: list[ProductResponse]
    total: int
    limit: int
    offset: int


class ProductFromLabelRequest(ProductCreate):
    """Create or update a product from manually confirmed label facts."""

    source_kind: str = Field(default="label_manual", examples=["label_manual"])

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "barcode": "4601234567890",
                    "brand": "Burn",
                    "name": "Peach Mango Zero Sugar",
                    "default_grams": 500,
                    "default_serving_text": "500 ml",
                    "carbs_per_100g": 0,
                    "protein_per_100g": 0,
                    "fat_per_100g": 0,
                    "fiber_per_100g": 0,
                    "kcal_per_100g": 1,
                    "source_kind": "label_manual",
                    "aliases": ["burn zero peach mango"],
                }
            ]
        }
    )


class PatternBase(BaseModel):
    """Shared pattern fields."""

    prefix: str = Field(examples=["bk"])
    key: str = Field(examples=["whopper"])
    display_name: str = Field(examples=["Whopper"])
    default_grams: float | None = Field(default=None, ge=0, examples=[270])
    default_carbs_g: float = Field(default=0, ge=0, examples=[51])
    default_protein_g: float = Field(default=0, ge=0, examples=[28])
    default_fat_g: float = Field(default=0, ge=0, examples=[35])
    default_fiber_g: float = Field(default=0, ge=0, examples=[3])
    default_kcal: float = Field(default=0, ge=0, examples=[635])
    per_100g_kcal: float | None = Field(default=None, ge=0, examples=[260])
    per_100g_carbs_g: float | None = Field(default=None, ge=0, examples=[19])
    per_100g_protein_g: float | None = Field(default=None, ge=0, examples=[10])
    per_100g_fat_g: float | None = Field(default=None, ge=0, examples=[16])
    source_url: str | None = Field(default=None, examples=["https://example.test"])
    source_name: str | None = Field(default=None, examples=["Burger King official PDF"])
    source_file: str | None = Field(default=None, examples=["bk.generated.pdf"])
    source_page: int | None = Field(default=None, ge=1, examples=[1])
    source_confidence: str | None = Field(default=None, examples=["official_pdf"])
    is_verified: bool = Field(default=False)
    image_url: str | None = Field(
        default=None, examples=["https://example.test/item.png"]
    )
    nutrients_json: dict[str, NutrientInput | float | None] = Field(
        default_factory=dict,
        examples=[{"sodium_mg": {"amount": 980, "unit": "mg"}}],
    )


class PatternCreate(PatternBase):
    """Create a reusable meal item pattern."""

    aliases: list[str] = Field(default_factory=list, examples=[["воппер"]])

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "prefix": "bk",
                    "key": "whopper",
                    "display_name": "Whopper",
                    "default_grams": 270,
                    "default_carbs_g": 51,
                    "default_protein_g": 28,
                    "default_fat_g": 35,
                    "default_fiber_g": 3,
                    "default_kcal": 635,
                    "source_url": "https://origin.bk.com/pdfs/nutrition.pdf",
                    "aliases": ["воппер", "вопер", "whopper"],
                }
            ]
        }
    )


class PatternPatch(BaseModel):
    """Patch a reusable meal item pattern."""

    prefix: str | None = None
    key: str | None = None
    display_name: str | None = None
    default_grams: float | None = Field(default=None, ge=0)
    default_carbs_g: float | None = Field(default=None, ge=0)
    default_protein_g: float | None = Field(default=None, ge=0)
    default_fat_g: float | None = Field(default=None, ge=0)
    default_fiber_g: float | None = Field(default=None, ge=0)
    default_kcal: float | None = Field(default=None, ge=0)
    per_100g_kcal: float | None = Field(default=None, ge=0)
    per_100g_carbs_g: float | None = Field(default=None, ge=0)
    per_100g_protein_g: float | None = Field(default=None, ge=0)
    per_100g_fat_g: float | None = Field(default=None, ge=0)
    source_url: str | None = None
    source_name: str | None = None
    source_file: str | None = None
    source_page: int | None = Field(default=None, ge=1)
    source_confidence: str | None = None
    is_verified: bool | None = None
    image_url: str | None = None
    nutrients_json: dict[str, NutrientInput | float | None] | None = None
    aliases: list[str] | None = None
    is_archived: bool | None = None


class PatternResponse(PatternBase):
    """Pattern response."""

    id: UUID
    usage_count: int
    last_used_at: datetime | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    aliases: list[str] = Field(default_factory=list)
    matched_alias: str | None = None

    model_config = ConfigDict(from_attributes=True)


class PatternPageResponse(BaseModel):
    """Paginated pattern list response."""

    items: list[PatternResponse]
    total: int
    limit: int
    offset: int


class DatabaseItemResponse(BaseModel):
    """Unified food database row for desktop database management."""

    id: UUID
    kind: Literal["pattern", "product", "restaurant"]
    prefix: str | None = None
    key: str | None = None
    token: str | None = None
    display_name: str
    subtitle: str | None = None
    image_url: str | None = None
    image_cache_path: str | None = None
    carbs_g: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    kcal: float | None = None
    default_grams: float | None = None
    usage_count: int = 0
    last_used_at: datetime | None = None
    source_name: str | None = None
    source_url: str | None = None
    source_file: str | None = None
    source_page: int | None = None
    source_confidence: str | None = None
    is_verified: bool = False
    aliases: list[str] = Field(default_factory=list)
    nutrients_json: dict[str, Any] = Field(default_factory=dict)
    quality_warnings: list[str] = Field(default_factory=list)


class DatabaseItemPageResponse(BaseModel):
    """Paginated food database response."""

    items: list[DatabaseItemResponse]
    total: int
    limit: int
    offset: int


class AutocompleteSuggestion(BaseModel):
    """Unified autocomplete suggestion for frontend command palettes."""

    kind: Literal["pattern", "product", "command"]
    id: UUID | None = None
    token: str
    display_name: str
    subtitle: str | None = None
    carbs_g: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    kcal: float | None = None
    image_url: str | None = None
    usage_count: int = 0
    matched_alias: str | None = None


class NightscoutSettingsPatch(BaseModel):
    """Update server-side Nightscout settings."""

    nightscout_enabled: bool | None = None
    nightscout_url: str | None = None
    nightscout_api_secret: str | None = None
    sync_glucose: bool | None = None
    show_glucose_in_journal: bool | None = None
    import_insulin_events: bool | None = None
    allow_meal_send: bool | None = None
    confirm_before_send: bool | None = None
    autosend_meals: bool | None = None


class NightscoutSettingsResponse(BaseModel):
    """Masked server-side Nightscout settings response."""

    enabled: bool
    configured: bool
    connected: bool
    url: str | None = None
    secret_is_set: bool
    last_status_check_at: datetime | None = None
    last_error: str | None = None
    sync_glucose: bool
    show_glucose_in_journal: bool
    import_insulin_events: bool
    allow_meal_send: bool
    confirm_before_send: bool
    autosend_meals: bool


class NightscoutStatusResponse(BaseModel):
    """Nightscout optional integration status."""

    configured: bool
    status: dict[str, Any] | None = None


class NightscoutTestResponse(BaseModel):
    """Nightscout connection test result."""

    ok: bool
    status: dict[str, Any] | None = None
    server_name: str | None = None
    version: str | None = None
    error: str | None = None


class NightscoutSyncResponse(BaseModel):
    """Nightscout meal sync response."""

    synced: bool
    nightscout_id: str | None = None
    nightscout_synced_at: datetime | None = None
    nightscout_sync_status: str | None = None
    nightscout_sync_error: str | None = None
    response: dict[str, Any] | None = None


class NightscoutSyncTodayRequest(BaseModel):
    """Request to manually sync one diary day to Nightscout."""

    date: date_type
    confirm: bool = True


class NightscoutSyncTodayMealResult(BaseModel):
    """Result for one meal in a day sync run."""

    meal_id: UUID
    title: str | None = None
    status: Literal["sent", "skipped", "failed"]
    nightscout_id: str | None = None
    error: str | None = None


class NightscoutSyncTodayResponse(BaseModel):
    """Manual day sync summary."""

    date: date_type
    total_candidates: int
    sent_count: int
    skipped_count: int
    failed_count: int
    results: list[NightscoutSyncTodayMealResult]


class NightscoutDayStatusResponse(BaseModel):
    """Nightscout sync status for one diary day."""

    date: date_type
    connected: bool
    configured: bool
    accepted_meals_count: int
    unsynced_meals_count: int
    synced_meals_count: int
    failed_meals_count: int
    last_sync_at: datetime | None = None


class NightscoutGlucoseEntryResponse(BaseModel):
    """Read-only Nightscout glucose entry normalized for UI context."""

    timestamp: datetime
    value: float
    unit: str = "mmol/L"
    trend: str | None = None
    source: str | None = None


class NightscoutInsulinEventResponse(BaseModel):
    """Read-only Nightscout insulin event."""

    timestamp: datetime
    insulin_units: float | None = None
    eventType: str | None = None
    insulin_type: str | None = None
    enteredBy: str | None = None
    notes: str | None = None
    nightscout_id: str | None = None


class NightscoutEventsResponse(BaseModel):
    """Combined read-only Nightscout context events."""

    glucose: list[NightscoutGlucoseEntryResponse]
    insulin: list[NightscoutInsulinEventResponse]


class NightscoutImportRequest(BaseModel):
    """Import Nightscout context into the local read-only cache."""

    from_datetime: datetime
    to_datetime: datetime
    sync_glucose: bool = True
    import_insulin_events: bool = True


class NightscoutImportResponse(BaseModel):
    """Nightscout local cache import summary."""

    from_datetime: datetime
    to_datetime: datetime
    glucose_imported: int
    insulin_imported: int
    glucose_total: int
    insulin_total: int
    last_error: str | None = None


class TimelineGlucoseSummary(BaseModel):
    """Small CGM summary for a computed food episode."""

    before_value: float | None = None
    peak_value: float | None = None
    latest_value: float | None = None
    min_value: float | None = None
    max_value: float | None = None
    unit: str = "mmol/L"


class FoodEpisodeResponse(BaseModel):
    """Computed grouping of meal, insulin, and local CGM context."""

    id: str
    start_at: datetime
    end_at: datetime
    title: str
    meals: list[MealResponse]
    insulin: list[NightscoutInsulinEventResponse] = Field(default_factory=list)
    glucose: list[NightscoutGlucoseEntryResponse] = Field(default_factory=list)
    glucose_summary: TimelineGlucoseSummary
    total_carbs_g: float
    total_kcal: float


class TimelineInsulinEventResponse(NightscoutInsulinEventResponse):
    """Read-only insulin event not grouped into a food episode."""

    linked_episode_id: str | None = None


class TimelineResponse(BaseModel):
    """History timeline response with backend-owned computed food episodes."""

    from_datetime: datetime
    to_datetime: datetime
    episodes: list[FoodEpisodeResponse]
    ungrouped_insulin: list[TimelineInsulinEventResponse] = Field(default_factory=list)


class ReportChipResponse(BaseModel):
    """Compact report metadata chip."""

    label: str


class EndocrinologistReportKpi(BaseModel):
    """Top report KPI tile."""

    label: str
    value: str
    unit: str
    caption: str


class EndocrinologistMealProfileRow(BaseModel):
    """Meal profile report table row."""

    key: str
    label: str
    episodes: str
    carbs: str
    insulin: str
    glucose_before: str
    glucose_after: str
    observed_ratio: str


class EndocrinologistDailySummaryRow(BaseModel):
    """Daily report table row."""

    date: str
    date_label: str
    carbs: str
    insulin: str
    tir: str
    hypo: str
    breakfast: str
    lunch: str
    dinner: str
    flagged: bool


class EndocrinologistBottomMetric(BaseModel):
    """Bottom strip report metric."""

    label: str
    value: str
    unit: str | None = None


class EndocrinologistReportResponse(BaseModel):
    """Presentation-ready endocrinologist report data."""

    app_name: str
    title: str
    period_label: str
    generated_label: str
    chips: list[ReportChipResponse]
    warning: str | None = None
    notes: list[str] = Field(default_factory=list)
    kpis: list[EndocrinologistReportKpi]
    meal_profile_rows: list[EndocrinologistMealProfileRow]
    daily_rows: list[EndocrinologistDailySummaryRow]
    shown_daily_rows: list[EndocrinologistDailySummaryRow]
    daily_median_row: EndocrinologistDailySummaryRow
    daily_rows_note: str | None = None
    bottom_metrics: list[EndocrinologistBottomMetric]
    footer: str


class AdminRecalculateResponse(BaseModel):
    """Daily total backfill response."""

    from_date: date_type
    to_date: date_type
    days_recalculated: int


class DashboardNutrientTotal(BaseModel):
    """Daily or range nutrient total with known-value coverage."""

    nutrient_code: str
    display_name: str
    unit: str
    amount: float | None = None
    known_item_count: int
    total_item_count: int
    coverage: float


class DashboardTodayResponse(BaseModel):
    """Dashboard summary for today."""

    date: date_type
    kcal: float
    carbs_g: float
    protein_g: float
    fat_g: float
    fiber_g: float
    meal_count: int
    last_meal_at: datetime | None = None
    hours_since_last_meal: float | None = None
    week_avg_carbs: float
    week_avg_kcal: float
    prev_week_avg_carbs: float
    prev_week_avg_kcal: float
    nutrients: list[DashboardNutrientTotal] = Field(default_factory=list)


class DashboardDayResponse(BaseModel):
    """Daily dashboard row."""

    date: date_type
    kcal: float
    carbs_g: float
    protein_g: float
    fat_g: float
    fiber_g: float
    meal_count: int
    nutrients: list[DashboardNutrientTotal] = Field(default_factory=list)


class DashboardRangeSummary(BaseModel):
    """Dashboard range aggregate summary."""

    avg_kcal: float
    avg_carbs_g: float
    avg_protein_g: float
    avg_fat_g: float
    avg_fiber_g: float
    total_meals: int
    total_kcal: float
    total_carbs_g: float
    total_protein_g: float
    total_fat_g: float
    total_fiber_g: float
    nutrients: list[DashboardNutrientTotal] = Field(default_factory=list)


class DashboardRangeResponse(BaseModel):
    """Dashboard range response."""

    days: list[DashboardDayResponse]
    summary: DashboardRangeSummary


class DashboardHeatmapCell(BaseModel):
    """Meal heatmap aggregate cell."""

    day_of_week: int
    hour: int
    avg_carbs_g: float
    meal_count: int


class DashboardHeatmapResponse(BaseModel):
    """Dashboard meal heatmap response."""

    cells: list[DashboardHeatmapCell]


class DashboardTopPatternResponse(BaseModel):
    """Top used pattern response row."""

    pattern_id: UUID
    token: str
    display_name: str
    count: int


class DashboardSourceBreakdownRow(BaseModel):
    """Source kind count row."""

    source_kind: ItemSourceKind
    count: int


class DashboardSourceBreakdownResponse(BaseModel):
    """Dashboard source kind breakdown."""

    days: int
    items: list[DashboardSourceBreakdownRow]


class LowConfidenceItemResponse(BaseModel):
    """Low-confidence item row."""

    meal_id: UUID
    item_id: UUID
    name: str
    confidence: float | None = None
    reason: str | None = None


class DashboardDataQualityResponse(BaseModel):
    """Dashboard data quality response."""

    exact_label_count: int
    assumed_label_count: int
    restaurant_db_count: int
    product_db_count: int
    pattern_count: int
    visual_estimate_count: int
    manual_count: int
    low_confidence_count: int
    total_item_count: int
    low_confidence_items: list[LowConfidenceItemResponse]
