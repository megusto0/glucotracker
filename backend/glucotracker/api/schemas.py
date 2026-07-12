"""Pydantic request and response schemas for the REST API."""

from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as date_type
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    db: str = Field(examples=["not_checked"])


class StatsInsightResponse(BaseModel):
    """Server-rendered stats observation."""

    id: str
    kind: Literal[
        "consistent",
        "weekday_pattern_sweet",
        "time_of_day_eating",
        "top_repeat_products",
        "late_meal_share",
        "today_morning",
        "meal_predictability",
        "evening_lows",
        "hypo_recovery_pattern",
        "late_meal_glucose_footprint",
    ]
    text: str
    weight: Literal["primary", "secondary"]
    computed_at: datetime
    supporting_numbers: dict[str, str] | None = None

    model_config = ConfigDict(from_attributes=True)


class StatsInsightsResponse(BaseModel):
    """Stats observation list."""

    insights: list[StatsInsightResponse]


class StatsOverviewLeadResponse(BaseModel):
    """Backend-rendered editorial lead for mobile stats."""

    kicker: str
    descriptor: str
    detail: str

    model_config = ConfigDict(from_attributes=True)


class StatsOverviewDayResponse(BaseModel):
    """One day in the mobile stats kcal chart."""

    date: date_type
    kcal: float | None = None
    meal_count: int

    model_config = ConfigDict(from_attributes=True)


class StatsOverviewMacroResponse(BaseModel):
    """Average macro row for the selected stats period."""

    key: Literal["protein", "fat", "carbs"]
    label: str
    grams: float | None = None
    percent: float | None = None
    target_percent: float | None = None

    model_config = ConfigDict(from_attributes=True)


class StatsOverviewHourlyBucketResponse(BaseModel):
    """One 24-hour meal-density bucket."""

    hour: int
    meal_count: int
    share: float

    model_config = ConfigDict(from_attributes=True)


class StatsOverviewTopProductResponse(BaseModel):
    """Frequently repeated food item or product."""

    rank: int
    name: str
    count: int
    kcal_per_100g: float | None = None
    protein_per_100g: float | None = None
    fat_per_100g: float | None = None
    carbs_per_100g: float | None = None
    image_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class StatsOverviewAnomalyResponse(BaseModel):
    """Day whose kcal total differs strongly from the period rhythm."""

    date: date_type
    direction: Literal["up", "down"]
    reason: str
    kcal: float
    delta_kcal: float

    model_config = ConfigDict(from_attributes=True)


class GlucoseTirDayResponse(BaseModel):
    """Per-day share of CGM points across display TIR bands (gluco only)."""

    date: date_type
    points: int
    very_low_pct: float | None = None
    low_pct: float | None = None
    in_range_pct: float | None = None
    high_pct: float | None = None
    very_high_pct: float | None = None

    model_config = ConfigDict(from_attributes=True)


class GlucoseTirDailyResponse(BaseModel):
    """Daily TIR distribution for a stats period (gluco feature only)."""

    period: Literal["7d", "14d", "30d"]
    days: list[GlucoseTirDayResponse]


class DayEpisodeInsulinResponse(BaseModel):
    """One insulin event inside a grouped episode (gluco feature only)."""

    id: UUID
    timestamp: datetime
    insulin_units: float | None = None
    # "food" when the event is attributed to meals nearby, "correction"
    # when it stands alone. Display attribution only, never advice.
    kind: Literal["food", "correction"]
    anchor_meal_id: UUID | None = None


class DayEpisodeResponse(BaseModel):
    """One grouped meal/insulin episode for client attribution."""

    key: str
    kind: Literal["food", "food_only", "correction"]
    start_at: datetime
    end_at: datetime
    meal_ids: list[UUID]
    insulin: list[DayEpisodeInsulinResponse]
    total_carbs_g: float
    total_kcal: float
    total_insulin_units: float


class DayEpisodesResponse(BaseModel):
    """Grouped episodes for a local wall-clock range."""

    from_datetime: datetime
    to_datetime: datetime
    episodes: list[DayEpisodeResponse]


class StatsOverviewResponse(BaseModel):
    """Structured mobile stats aggregate."""

    period: Literal["7d", "14d", "30d"]
    days: int
    start_date: date_type
    end_date: date_type
    tracked_days: int
    sparse: bool
    average_kcal: float | None = None
    rhythm_delta_kcal: float | None = None
    spread_kcal: float | None = None
    normal_kcal_low: float | None = None
    normal_kcal_high: float | None = None
    lead: StatsOverviewLeadResponse
    daily: list[StatsOverviewDayResponse]
    macros: list[StatsOverviewMacroResponse]
    hourly: list[StatsOverviewHourlyBucketResponse]
    top_products: list[StatsOverviewTopProductResponse]
    anomalies: list[StatsOverviewAnomalyResponse]

    model_config = ConfigDict(from_attributes=True)


class UserGoalsResponse(BaseModel):
    kcal_goal_per_day: int | None = None
    protein_goal_g_per_day: int | None = None
    carb_goal_g_per_day: int | None = None
    fat_goal_g_per_day: int | None = None
    goals_setup_completed: bool = False


class UserGoalsUpdate(BaseModel):
    kcal_goal_per_day: int | None = None
    protein_goal_g_per_day: int | None = None
    carb_goal_g_per_day: int | None = None
    fat_goal_g_per_day: int | None = None
    goals_setup_completed: bool | None = None


class ScheduleWindowResponse(BaseModel):
    """Rendered meal-window boundary for the current day rhythm."""

    key: Literal["start", "mid", "late", "night_cap"]
    label: str
    start_minute: int
    end_minute: int


class DayAnchorHistoryResponse(BaseModel):
    """One effective day-anchor history row."""

    id: UUID
    effective_from: date_type
    effective_to: date_type | None = None
    anchor_weekday_minutes: int | None = None
    anchor_weekend_minutes: int | None = None
    basis: str
    recorded_at: datetime
    duration_days: int | None = None
    shift_from_previous_minutes: int | None = None


class NonTypicalPeriodResponse(BaseModel):
    """Date range excluded from automatic day-anchor learning."""

    id: UUID
    start_date: date_type
    end_date: date_type
    note: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScheduleResponse(BaseModel):
    """Current adaptive day rhythm and override state."""

    anchor_weekday_minutes: int | None = None
    anchor_weekend_minutes: int | None = None
    effective_anchor_minutes: int | None = None
    basis: str | None = None
    user_override_minutes: int | None = None
    last_shift_at: datetime | None = None
    windows: list[ScheduleWindowResponse]
    history: list[DayAnchorHistoryResponse] = Field(default_factory=list)
    non_typical_periods: list[NonTypicalPeriodResponse] = Field(default_factory=list)


class ScheduleOverrideRequest(BaseModel):
    """Manual day-anchor override in minutes from midnight."""

    anchor_minutes: int = Field(ge=0, le=1439)


class NonTypicalPeriodCreate(BaseModel):
    """Create a period excluded from day-anchor learning."""

    start_date: date_type
    end_date: date_type
    note: str | None = None


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
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=64)

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "eaten_at": "2026-04-28T08:30:00",
                    "title": "Breakfast",
                    "note": "Manual entry",
                    "source": "manual",
                    "idempotency_key": "11111111-1111-1111-1111-111111111111",
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


class MealItemWeightReuseRequest(BaseModel):
    """Create a new meal from an existing item scaled to a target weight."""

    grams: float = Field(gt=0, examples=[127])
    eaten_at: datetime | None = None


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


PhotoEstimateStatus = Literal["estimating", "succeeded", "failed", "timeout", "error"]


class PhotoCaptureResponse(BaseModel):
    """Accepted single-call photo capture response."""

    meal_id: UUID
    estimate_status: PhotoEstimateStatus
    captured_at: datetime
    photo_url: str


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
    estimate_status: str | None = None
    estimate_error: str | None = None
    nightscout_synced_at: datetime | None = None
    nightscout_id: str | None = None
    nightscout_sync_status: str = "not_synced"
    nightscout_sync_error: str | None = None
    nightscout_last_attempt_at: datetime | None = None
    thumbnail_url: str | None = None
    postprandial_response: dict[str, Any] | None = None
    photo_idempotency_key: str | None = None
    derived_categories: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    items: list[MealItemResponse] = Field(default_factory=list)
    photos: list[PhotoResponse] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

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


class NightscoutInsulinEntryCreate(BaseModel):
    """Manual insulin amount to write as a Nightscout treatment."""

    insulin_units: float = Field(gt=0, le=100)
    recorded_at: datetime | None = None
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)


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


class NightscoutLatestReadingResponse(BaseModel):
    """Latest glucose reading from the local Nightscout cache."""

    timestamp: datetime | None = None
    value_mmol_l: float | None = None
    trend: str | None = None
    sensor_id: str | None = None
    total_entries: int = 0


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


class FoodEpisodeFoodResponse(BaseModel):
    """Computed food-only episode."""

    id: str
    start_at: datetime
    end_at: datetime
    title: str
    meals: list[MealResponse]
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


class TimelineFoodResponse(BaseModel):
    """Food-only history timeline response."""

    from_datetime: datetime
    to_datetime: datetime
    episodes: list[FoodEpisodeFoodResponse]


class MealInsulinLinkItem(BaseModel):
    """One reviewed many-to-many food/insulin link."""

    meal_id: UUID
    insulin_event_id: UUID
    source: Literal["manual", "auto"] = "manual"
    confidence: float | None = None
    note: str | None = None


class InsulinLinkGlucoseAnchorResponse(BaseModel):
    """CGM value sampled around a food/insulin episode."""

    value: float
    timestamp: datetime
    source: Literal["actual", "interpolated"]


class InsulinLinkMealResponse(BaseModel):
    """Compact food event for one-day insulin review."""

    id: UUID
    eaten_at: datetime
    title: str
    total_carbs_g: float
    total_kcal: float
    glucose_minus_30: InsulinLinkGlucoseAnchorResponse | None = None
    glucose_plus_2h: InsulinLinkGlucoseAnchorResponse | None = None


class InsulinLinkEventResponse(BaseModel):
    """Insulin event with backend-owned contextual label and link hints."""

    id: UUID
    timestamp: datetime
    insulin_units: float | None = None
    raw_event_type: str | None = None
    insulin_type: str | None = None
    enteredBy: str | None = None
    notes: str | None = None
    nightscout_id: str | None = None
    context_label: Literal["food", "correction", "mixed", "unresolved", "manual"]
    link_source: Literal["manual", "auto", "none"]
    linked_meal_ids: list[UUID] = Field(default_factory=list)
    suggested_meal_ids: list[UUID] = Field(default_factory=list)
    confidence: float | None = None
    reason: str
    covers_multiple_food_events: bool = False


class InsulinLinkDayResponse(BaseModel):
    """One-day workspace for reviewing food and insulin event links."""

    date: date_type
    meals: list[InsulinLinkMealResponse]
    insulin_events: list[InsulinLinkEventResponse]
    # Active links are auto-rule results unless the user reviewed an insulin event.
    links: list[MealInsulinLinkItem]
    auto_links: list[MealInsulinLinkItem]
    reviewed_insulin_event_ids: list[UUID] = Field(default_factory=list)


class InsulinLinkDayPutRequest(BaseModel):
    """Replace reviewed food/insulin links for one day atomically."""

    date: date_type
    links: list[MealInsulinLinkItem] = Field(default_factory=list)
    reviewed_insulin_event_ids: list[UUID] = Field(default_factory=list)


class SensorSessionBase(BaseModel):
    """Shared CGM sensor session fields."""

    source: str = Field(default="manual", examples=["manual"])
    vendor: str | None = Field(default=None, examples=["Ottai"])
    model: str | None = Field(default=None, examples=["Ottai"])
    label: str | None = Field(default=None, examples=["Ottai #4"])
    started_at: datetime
    ended_at: datetime | None = None
    expected_life_days: float = Field(default=15, gt=0)
    excluded_from_analytics: bool = False
    exclusion_reason: str | None = None
    notes: str | None = None


class SensorSessionCreate(SensorSessionBase):
    """Create a display analytics sensor session."""


class SensorSessionPatch(BaseModel):
    """Patch a display analytics sensor session."""

    source: str | None = None
    vendor: str | None = None
    model: str | None = None
    label: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    expected_life_days: float | None = Field(default=None, gt=0)
    excluded_from_analytics: bool | None = None
    exclusion_reason: str | None = None
    notes: str | None = None


class SensorSessionResponse(SensorSessionBase):
    """Stored display analytics sensor session."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FingerstickReadingCreate(BaseModel):
    """Create a manual capillary glucose reading."""

    measured_at: datetime
    glucose_mmol_l: float = Field(gt=0, le=40)
    meter_name: str | None = None
    notes: str | None = None


class FingerstickReadingPatch(BaseModel):
    """Patch a manual capillary glucose reading."""

    measured_at: datetime | None = None
    glucose_mmol_l: float | None = Field(default=None, gt=0, le=40)
    meter_name: str | None = None
    notes: str | None = None


class FingerstickReadingResponse(FingerstickReadingCreate):
    """Stored manual capillary glucose reading."""

    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CgmCalibrationModelResponse(BaseModel):
    """Persisted display-only CGM calibration model."""

    id: UUID
    sensor_session_id: UUID
    model_version: str
    created_at: datetime
    params_json: dict[str, Any]
    metrics_json: dict[str, Any]
    confidence: Literal["none", "low", "medium", "high"]
    active: bool

    model_config = ConfigDict(from_attributes=True)


class SensorWarmupMetricsResponse(BaseModel):
    """Warmup-only residual metrics for display analytics."""

    initial_residual_mmol_l: float | None = None
    max_warmup_residual_mmol_l: float | None = None
    plateau_residual_mmol_l: float | None = None
    time_to_stabilize_hours: float | None = None
    warmup_instability_score: float | None = None
    residual_sequence_mmol_l: list[float] = Field(default_factory=list)


class SensorQualityResponse(BaseModel):
    """Computed sensor quality and calibration metrics."""

    sensor: SensorSessionResponse | None = None
    sensor_age_days: float | None = None
    sensor_phase: Literal["warmup", "stable", "end_of_life"] | None = None
    fingerstick_count: int
    valid_calibration_points: int
    matched_calibration_points: int = 0
    stable_calibration_points: int = 0
    warmup_calibration_points: int = 0
    calibration_basis: (
        Literal["stable_after_48h", "warmup_after_12h_fallback", "insufficient"] | None
    ) = None
    warmup_metrics: SensorWarmupMetricsResponse | None = None
    median_bias_mmol_l: float | None = None
    median_delta_mmol_l: float | None = None
    delta_min_mmol_l: float | None = None
    delta_max_mmol_l: float | None = None
    b0_mmol_l: float | None = None
    b1_raw_mmol_l_per_day: float | None = None
    b1_capped_mmol_l_per_day: float | None = None
    correction_now_mmol_l: float | None = None
    calibration_strategy: (
        Literal["median_delta", "warmup_blend", "linear", "insufficient"] | None
    ) = None
    mad_mmol_l: float | None = None
    mard_percent: float | None = None
    drift_mmol_l_per_day: float | None = None
    residual_mad_mmol_l: float | None = None
    missing_data_pct: float | None = None
    suspected_compression_count: int
    noise_score: float
    quality_score: int
    confidence: Literal["none", "low", "medium", "high"]
    notes: list[str] = Field(default_factory=list)
    active_model: CgmCalibrationModelResponse | None = None


class GlucoseDashboardPoint(BaseModel):
    """One glucose dashboard display point."""

    timestamp: datetime
    raw_value: float
    smoothed_value: float | None = None
    normalized_value: float | None = None
    display_value: float
    correction_mmol_l: float | None = None
    bias_confidence: str | None = None
    nearest_fingerstick_distance_min: float | None = None
    contributing_fingerstick_count: int | None = None
    flags: list[str] = Field(default_factory=list)


class GlucoseDashboardFoodEvent(BaseModel):
    """Food marker for glucose dashboard overlays."""

    timestamp: datetime
    title: str
    carbs_g: float
    kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    # Macro-based absorption class: fast | normal | slow
    absorption_profile: str | None = None
    absorption_minutes: int | None = None
    absorption_fast_weight: float | None = None
    absorption_normal_weight: float | None = None
    absorption_slow_weight: float | None = None
    absorption_model_source: (
        Literal[
            "macro_prior",
            "personalized_meal",
            "personalized_category",
        ]
        | None
    ) = None
    absorption_confidence: Literal["none", "low", "medium", "high"] | None = None


class GlucoseDashboardInsulinEvent(BaseModel):
    """Read-only insulin marker for glucose dashboard overlays."""

    timestamp: datetime
    insulin_units: float | None = None
    event_type: str | None = None
    insulin_type: str | None = None
    notes: str | None = None


class GlucoseArtifactInterval(BaseModel):
    """Suspected artifact interval for display shading."""

    start_at: datetime
    end_at: datetime
    kind: Literal[
        "compression_suspected",
        "jump_suspected",
        "gap",
        "low_confidence_calibration",
        "end_of_life_noise",
    ]
    label: str


class GlucoseDashboardSummary(BaseModel):
    """Compact dashboard status values."""

    current_glucose: float | None = None
    current_glucose_at: datetime | None = None
    iob_units: float = 0.0
    iob_minutes_remaining: int = 0
    cob_g: float = 0.0
    cob_minutes_remaining: int = 0
    iob_model_source: Literal["population", "personalized"] = "population"
    iob_model_confidence: Literal["none", "low", "medium", "high"] = "none"
    cob_model_source: Literal["macro_prior", "personalized"] = "macro_prior"
    cob_model_confidence: Literal["none", "low", "medium", "high"] = "none"
    sensor_age_days: float | None = None
    bias_mmol_l: float | None = None
    drift_mmol_l_per_day: float | None = None
    calibration_confidence: Literal["none", "low", "medium", "high"]
    suspected_compression_count: int


class GlucoseDashboardResponse(BaseModel):
    """Nightscout-like glucose dashboard response."""

    from_datetime: datetime
    to_datetime: datetime
    mode: Literal["raw", "smoothed", "normalized"]
    points: list[GlucoseDashboardPoint]
    fingersticks: list[FingerstickReadingResponse]
    food_events: list[GlucoseDashboardFoodEvent]
    insulin_events: list[GlucoseDashboardInsulinEvent]
    artifacts: list[GlucoseArtifactInterval]
    current_sensor: SensorSessionResponse | None = None
    sensors: list[SensorSessionResponse]
    quality: SensorQualityResponse
    summary: GlucoseDashboardSummary
    bias_over_lifetime: BiasOverLifetimeData | None = None
    notes: list[str] = Field(default_factory=list)


class TwinParamsRead(BaseModel):
    """Current per-user digital twin parameters."""

    id: UUID
    icr_morning: float | None = None
    icr_day: float | None = None
    icr_evening: float | None = None
    morning_start_minutes: int
    day_start_minutes: int
    evening_start_minutes: int
    isf: float | None = None
    dia_minutes: int
    carb_duration_minutes: int
    baseline_drift_per_hour: float
    last_fit_at: datetime | None = None
    last_fit_data_from: datetime | None = None
    last_fit_data_to: datetime | None = None
    last_fit_train_window_count: int | None = None
    last_fit_holdout_window_count: int | None = None
    last_fit_train_mae_mmol: float | None = None
    last_fit_holdout_mae_mmol: float | None = None
    last_fit_method: str | None = None
    last_fit_converged: bool | None = None
    updated_at: datetime
    is_fitted: bool
    hint: Literal["not_fitted", "ready", "stale"]


class TwinParamsPatch(BaseModel):
    """Manual digital twin parameter override."""

    icr_morning: float | None = Field(default=None, ge=3, le=40)
    icr_day: float | None = Field(default=None, ge=3, le=40)
    icr_evening: float | None = Field(default=None, ge=3, le=40)
    morning_start_minutes: int | None = Field(default=None, ge=0, le=1439)
    day_start_minutes: int | None = Field(default=None, ge=0, le=1439)
    evening_start_minutes: int | None = Field(default=None, ge=0, le=1439)
    isf: float | None = Field(default=None, ge=0.2, le=8)
    dia_minutes: int | None = Field(default=None, ge=120, le=480)
    carb_duration_minutes: int | None = Field(default=None, ge=60, le=360)
    baseline_drift_per_hour: float | None = Field(default=None, ge=-1, le=1)

    @model_validator(mode="after")
    def validate_patch_slot_order(self) -> TwinParamsPatch:
        """Reject an explicitly invalid slot order."""
        values = [
            self.morning_start_minutes,
            self.day_start_minutes,
            self.evening_start_minutes,
        ]
        if all(value is not None for value in values) and not (
            values[0] < values[1] < values[2]
        ):
            raise ValueError(
                "morning_start_minutes must be less than day_start_minutes "
                "and day_start_minutes must be less than evening_start_minutes"
            )
        return self


class TwinFitRequest(BaseModel):
    """Request an automatic digital twin fitting run."""

    data_from: datetime | None = None
    data_to: datetime | None = None


class TwinFitResultRead(BaseModel):
    """Applied or rejected automatic fit metrics."""

    icr_morning: float
    icr_day: float
    icr_evening: float
    isf: float
    baseline_drift_per_hour: float
    train_mae_mmol: float
    holdout_mae_mmol: float
    train_window_count: int
    holdout_window_count: int
    method: Literal["least_squares", "fallback_to_defaults"]
    converged: bool
    iterations: int
    per_window_train_mae: list[float] = Field(default_factory=list)
    per_window_holdout_mae: list[float] = Field(default_factory=list)
    per_window_train_dates: list[date_type] = Field(default_factory=list)
    per_window_holdout_dates: list[date_type] = Field(default_factory=list)


class TwinFitResponse(BaseModel):
    """Automatic digital twin fitting response."""

    applied: bool
    params: TwinParamsRead
    previous_params: TwinParamsRead | None = None
    result: TwinFitResultRead
    notes: list[str] = Field(default_factory=list)


class TwinDataSummaryResponse(BaseModel):
    """Data availability summary for automatic twin fitting."""

    from_datetime: datetime
    to_datetime: datetime
    cgm_count: int
    fingerstick_count: int
    meal_count: int
    insulin_count: int
    days_with_cgm: int
    first_cgm_at: datetime | None = None
    last_cgm_at: datetime | None = None
    ready_for_fit: bool
    fit_blockers: list[str] = Field(default_factory=list)


class TwinFitLogEntry(BaseModel):
    """One digital twin fit/manual-change history row."""

    id: UUID
    fit_at: datetime
    data_from: datetime | None = None
    data_to: datetime | None = None
    params_snapshot: dict[str, Any]
    train_window_count: int | None = None
    holdout_window_count: int | None = None
    train_mae_mmol: float | None = None
    holdout_mae_mmol: float | None = None
    method: str
    converged: bool | None = None
    iterations: int | None = None
    notes: str | None = None

    model_config = ConfigDict(from_attributes=True)


class TwinCurvePoint(BaseModel):
    """One digital twin curve point."""

    timestamp: datetime
    mmol: float
    ci_low: float
    ci_high: float
    confidence: float
    mode: Literal["interpolation", "forecast", "boundary"]


class TwinCurveAnchor(BaseModel):
    """Known glucose anchor used by the digital twin curve."""

    timestamp: datetime
    mmol: float
    source: Literal["fingerstick", "cgm"] = "fingerstick"


class TwinCurveFoodEvent(BaseModel):
    """Food marker included in the digital twin curve."""

    timestamp: datetime
    title: str
    carbs_g: float
    kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None


class TwinCurveInsulinEvent(BaseModel):
    """Read-only insulin marker included in the digital twin curve."""

    timestamp: datetime
    insulin_units: float
    event_type: str | None = None
    insulin_type: str | None = None
    notes: str | None = None


class TwinCurveResponse(BaseModel):
    """Digital twin reconstruction/forecast response."""

    from_datetime: datetime
    to_datetime: datetime
    points: list[TwinCurvePoint]
    anchors: list[TwinCurveAnchor]
    food_events: list[TwinCurveFoodEvent]
    insulin_events: list[TwinCurveInsulinEvent]
    params: TwinParamsRead
    notes: list[str] = Field(default_factory=list)


class BiasResidualPoint(BaseModel):
    """One fingerstick residual on the bias chart."""

    measured_at: datetime
    sensor_age_hours: float
    fingerstick_value: float
    raw_cgm_value: float
    residual: float
    included: bool
    exclusion_reason: str | None = None


class BiasCurvePoint(BaseModel):
    """One sampled point on the estimated bias curve."""

    timestamp: datetime
    sensor_age_hours: float
    bias: float
    confidence: str
    contributing_fingerstick_count: int
    nearest_fingerstick_distance_min: float | None = None


class BiasPhaseMarker(BaseModel):
    """Phase boundary on the bias chart."""

    sensor_age_hours: float
    label: str


class BiasOverLifetimeData(BaseModel):
    """Data for the bias-over-sensor-lifetime chart."""

    sensor_started_at: datetime
    residuals: list[BiasResidualPoint]
    bias_curve: list[BiasCurvePoint]
    phase_markers: list[BiasPhaseMarker]


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
    spikes: str
    windows: str
    breakfast: str
    lunch: str
    dinner: str
    flagged: bool


class EndocrinologistScheduleWindowResponse(BaseModel):
    """Adaptive report window with rendered wall-clock range."""

    key: str
    label: str
    start_minute: int
    end_minute: int
    start_label: str
    end_label: str


class EndocrinologistAdaptiveScheduleResponse(BaseModel):
    """Adaptive rhythm banner for the report."""

    title: str
    summary: str
    basis: str
    windows: list[EndocrinologistScheduleWindowResponse]
    ribbon: str


class EndocrinologistBottomMetric(BaseModel):
    """Bottom strip report metric."""

    label: str
    value: str
    unit: str | None = None


class EndocrinologistReportResponse(BaseModel):
    """Presentation-ready endocrinologist report data."""

    app_name: str
    title: str
    glucose_mode: Literal["raw", "normalized"] = "raw"
    glucose_mode_label: str = "исходная CGM"
    period_label: str
    generated_label: str
    chips: list[ReportChipResponse]
    warning: str | None = None
    notes: list[str] = Field(default_factory=list)
    kpis: list[EndocrinologistReportKpi]
    glycemic_profile: list[EndocrinologistReportKpi]
    hypo_concentration_line: str
    adaptive_schedule: EndocrinologistAdaptiveScheduleResponse
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


class AdminPostprandialResponse(BaseModel):
    """Postprandial recompute response."""

    meals_total: int
    meals_analyzed: int


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


class DashboardTodayWithGlucoseResponse(DashboardTodayResponse):
    """Dashboard summary for a role with glucose context enabled."""

    current_glucose: float | None
    current_glucose_at: datetime | None


class DashboardDayResponse(BaseModel):
    """Daily dashboard row."""

    date: date_type
    kcal: float
    carbs_g: float
    protein_g: float
    fat_g: float
    fiber_g: float
    meal_count: int
    photo_count: int = 0
    daily_average_kcal_for_period: float | None = None
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
