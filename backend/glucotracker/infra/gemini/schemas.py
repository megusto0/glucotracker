"""Structured Gemini response schemas for photo nutrition estimation."""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

GeminiScenario = Literal[
    "LABEL_FULL",
    "LABEL_PARTIAL",
    "PLATED",
    "BARCODE",
    "SPLIT_LABEL_IDENTICAL_ITEMS",
    "UNKNOWN",
]
GeminiItemType = Literal[
    "drink",
    "packaged_food",
    "plated_food",
    "restaurant_item",
    "unknown",
]
GeminiComponentType = Literal[
    "carb_base",
    "protein",
    "vegetable",
    "sauce",
    "fat_source",
    "known_component",
    "unknown",
    # Legacy values accepted for old stored/mock Gemini payloads.
    "carb_anchor",
    "fat",
]


class ExtractedNutritionFacts(BaseModel):
    """Visible and assumed package facts extracted from a label image."""

    carbs_per_100g: float | None = None
    carbs_per_100ml: float | None = None
    protein_per_100g: float | None = None
    protein_per_100ml: float | None = None
    fat_per_100g: float | None = None
    fat_per_100ml: float | None = None
    fiber_per_100g: float | None = None
    fiber_per_100ml: float | None = None
    kcal_per_100g: float | None = None
    kcal_per_100ml: float | None = None
    visible_weight_g: float | None = None
    visible_volume_ml: float | None = None
    assumed_weight_g: float | None = None
    assumed_volume_ml: float | None = None
    assumption_reason: str | None = None


class NutritionPer100g(BaseModel):
    """Visible nutrition values normalized to a per-100g basis."""

    kcal: float | None = None
    carbs_g: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    sugar_g: float | None = None
    sodium_mg: float | None = None
    caffeine_mg: float | None = None


class VisibleLabelFact(BaseModel):
    """One visible label fact extracted from a package."""

    label_ru: str
    value: float | None = None
    unit: str
    basis: str
    confidence: float | None = Field(default=None, ge=0, le=1)


class OptionalNutrientFact(BaseModel):
    """Visible optional nutrient fact extracted from a label."""

    code: str = ""
    amount: float | None = None
    amount_per_100g: float | None = None
    amount_per_100ml: float | None = None
    amount_per_serving: float | None = None
    unit: str | None = None
    source_kind: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class EstimatedComponent(BaseModel):
    """Component-level analysis inside one plated visual estimate."""

    name_ru: str
    component_type: GeminiComponentType = "unknown"
    type: GeminiComponentType | None = None
    estimated_grams_low: float | None = None
    estimated_grams_mid: float | None = None
    estimated_grams_high: float | None = None
    carbs_g_mid: float | None = None
    protein_g_mid: float | None = None
    fat_g_mid: float | None = None
    fiber_g_mid: float | None = None
    kcal_mid: float | None = None
    visual_count: float | None = None
    likely_database_match_query: str | None = None
    should_use_database_if_available: bool = False
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sync_component_type(self) -> "EstimatedComponent":
        """Normalize the old `type` field into `component_type`."""
        incoming = self.type or self.component_type
        if incoming == "carb_anchor":
            incoming = "carb_base"
        elif incoming == "fat":
            incoming = "fat_source"
        self.component_type = incoming
        self.type = incoming
        return self


class EstimatedItemEvidence(BaseModel):
    """Structured evidence fields supported by Gemini response schemas."""

    visible_text: list[str] = Field(default_factory=list)
    visible_components: list[str] = Field(default_factory=list)
    nutrition_label_visible: bool | None = None
    package_size_visible: bool | None = None
    barcode_visible: bool | None = None
    portion_notes: str | None = None
    scale_notes: str | None = None
    label_notes: str | None = None
    other_notes: list[str] = Field(default_factory=list)


class EstimatedItem(BaseModel):
    """Gemini-estimated visible item."""

    name: str
    display_name_ru: str | None = None
    brand: str | None = None
    source_photo_ids: list[str] = Field(default_factory=list)
    primary_photo_id: str | None = None
    source_photo_indices: list[int] = Field(default_factory=list)
    item_type: GeminiItemType = "unknown"
    scenario: GeminiScenario
    extracted_facts: ExtractedNutritionFacts | None = None
    visible_label_facts: list[VisibleLabelFact] = Field(default_factory=list)
    nutrition_per_100g: NutritionPer100g | None = None
    count_detected: int | None = Field(default=None, ge=1)
    count_confidence: float | None = Field(default=None, ge=0, le=1)
    net_weight_per_unit_g: float | None = Field(default=None, ge=0)
    total_weight_g: float | None = Field(default=None, ge=0)
    evidence_is_split_across_identical_items: bool = False
    optional_nutrients: list[OptionalNutrientFact] = Field(default_factory=list)
    grams_low: float | None = None
    grams_mid: float | None = None
    grams_high: float | None = None
    carbs_g_low: float | None = None
    carbs_g_mid: float | None = None
    carbs_g_high: float | None = None
    protein_g_mid: float | None = None
    fat_g_mid: float | None = None
    fiber_g_mid: float | None = None
    kcal_mid: float | None = None
    component_estimates: list[EstimatedComponent] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    confidence_reason: str
    confidence_reason_ru: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    identified_barcode: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_payloads(cls, data: Any) -> Any:
        """Keep older Gemini/test payloads compatible with the new schema."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        visible = data.get("visible_label_facts")
        if isinstance(visible, dict):
            data.setdefault("extracted_facts", visible)
            data["visible_label_facts"] = []
        evidence = data.get("evidence")
        if isinstance(evidence, dict):
            legacy_evidence = EstimatedItemEvidence.model_validate(evidence)
            evidence_text: list[str] = []
            evidence_text.extend(legacy_evidence.visible_text)
            evidence_text.extend(legacy_evidence.visible_components)
            evidence_text.extend(legacy_evidence.other_notes)
            if legacy_evidence.label_notes:
                evidence_text.append(legacy_evidence.label_notes)
            if legacy_evidence.portion_notes:
                evidence_text.append(legacy_evidence.portion_notes)
            if legacy_evidence.scale_notes:
                evidence_text.append(legacy_evidence.scale_notes)
            data["evidence"] = evidence_text
        optional_nutrients = data.get("optional_nutrients")
        if isinstance(optional_nutrients, dict):
            migrated_nutrients = []
            for code, value in optional_nutrients.items():
                if isinstance(value, OptionalNutrientFact):
                    nutrient = value.model_dump()
                    nutrient["code"] = code
                elif isinstance(value, dict):
                    nutrient = {"code": code, **value}
                else:
                    nutrient = {"code": code, "amount": value}
                migrated_nutrients.append(nutrient)
            data["optional_nutrients"] = migrated_nutrients
        return data


class EstimationResult(BaseModel):
    """Structured Gemini estimation result for one meal/snack."""

    items: list[EstimatedItem] = Field(default_factory=list)
    overall_notes: str = ""
    reference_object_detected: Literal[
        "coin_5rub",
        "card",
        "hand",
        "fork",
        "plate",
        "none",
    ] = "none"
    image_quality_warnings: list[str] = Field(default_factory=list)
