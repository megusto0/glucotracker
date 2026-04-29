"""Known-component matching and macro replacement for visual meal estimates."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from glucotracker.infra.gemini.schemas import EstimatedComponent, EstimatedItem

MACRO_FIELDS = ("carbs_g", "protein_g", "fat_g", "fiber_g", "kcal")
MODEL_ITEM_FIELDS = {
    "carbs_g": "carbs_g_mid",
    "protein_g": "protein_g_mid",
    "fat_g": "fat_g_mid",
    "fiber_g": "fiber_g_mid",
    "kcal": "kcal_mid",
}
COMPONENT_FIELDS = MODEL_ITEM_FIELDS

KNOWN_COMPONENT_TERMS = {
    "tortilla",
    "wrap",
    "wrap base",
    "лаваш",
    "тортилья",
    "основа ролла",
    "булка",
    "bread",
    "хлеб",
    "rice",
    "рис",
    "pasta",
    "паста",
    "макароны",
    "potato",
    "картофель",
    "сладкий напиток",
    "candy",
    "bar",
    "батончик",
    "cereal",
    "granola",
    "bakery",
    "выпечка",
}

MATCH_STOPWORDS = {
    "and",
    "base",
    "component",
    "for",
    "from",
    "the",
    "with",
    "без",
    "для",
    "или",
    "как",
    "мл",
    "на",
    "по",
    "при",
    "со",
    "тип",
    "г",
    "гр",
    "из",
    "компонент",
    "к",
    "основа",
    "с",
    "у",
    "в",
    "и",
}


@dataclass(frozen=True)
class KnownComponent:
    """Known local component values from products or patterns."""

    id: UUID
    kind: str
    display_name: str
    aliases: list[str]
    grams: float | None
    carbs_g: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    kcal: float | None = None
    nutrients_json: dict[str, Any] | None = None
    token: str | None = None
    source_kind: str = "personal_component"
    source_label: str = "сохранённый компонент"


@dataclass(frozen=True)
class MatchedKnownComponent:
    """A Gemini component matched to a known local component."""

    component: EstimatedComponent
    known_component: KnownComponent
    matched_query: str


@dataclass(frozen=True)
class KnownComponentAdjustment:
    """Backend macro adjustment derived from known components."""

    matches: list[MatchedKnownComponent] = field(default_factory=list)
    raw_model_totals: dict[str, float | None] = field(default_factory=dict)
    adjusted_totals: dict[str, float | None] = field(default_factory=dict)
    field_sources: dict[str, str] = field(default_factory=dict)
    component_rows: list[dict[str, Any]] = field(default_factory=list)
    warning: str | None = None

    @property
    def used_known_component(self) -> bool:
        """Return whether at least one known component was applied."""
        return bool(self.matches) and any(
            source in {"personal_component", "product_db", "pattern"}
            for source in self.field_sources.values()
        )


def normalized_text(value: str | None) -> str:
    """Return a simple normalized search string."""
    return (value or "").casefold().replace("ё", "е").strip()


def _match_tokens(value: str | None) -> set[str]:
    """Return specific tokens that are safe for component matching."""
    tokens = re.split(r"[^0-9a-zа-яё]+", normalized_text(value))
    return {
        token
        for token in tokens
        if len(token) >= 3 and not token.isdigit() and token not in MATCH_STOPWORDS
    }


def _component_query_values(component: EstimatedComponent) -> list[str]:
    """Return explicit Gemini lookup values for one component."""
    values = [component.name_ru, component.likely_database_match_query]
    return [normalized_text(value) for value in values if normalized_text(value)]


def _match_rank(query: str, value: str) -> int | None:
    """Return a conservative match rank for one component/query pair."""
    if value == query:
        return 0
    value_tokens = _match_tokens(value)
    query_tokens = _match_tokens(query)
    if not value_tokens or not query_tokens:
        return None
    if value in query:
        return 1
    if query in value:
        return 2
    if value_tokens & query_tokens:
        return 3
    return None


def is_known_component_name(value: str | None) -> bool:
    """Return whether a component/name looks like a reusable macro component."""
    text = normalized_text(value)
    if not text:
        return False
    return any(term in text for term in KNOWN_COMPONENT_TERMS)


def normalize_component_type(value: str | None) -> str:
    """Normalize current and legacy Gemini component types."""
    normalized = normalized_text(value)
    if normalized in {"carb_anchor", "carb_base", "known_component"}:
        return "carb_base"
    if normalized in {"fat", "fat_source"}:
        return "fat_source"
    if normalized in {"protein", "vegetable", "sauce", "unknown"}:
        return normalized
    return "unknown"


def infer_component_type(name: str | None) -> str:
    """Infer a component type for legacy models that returned split items."""
    text = normalized_text(name)
    if is_known_component_name(text):
        return "carb_base"
    if any(term in text for term in ["курица", "chicken", "мясо", "beef", "рыба"]):
        return "protein"
    if any(term in text for term in ["соус", "sauce", "майонез", "mayo"]):
        return "sauce"
    if any(term in text for term in ["масло", "oil", "сливоч"]):
        return "fat_source"
    if any(term in text for term in ["томат", "помид", "салат", "овощ", "greens"]):
        return "vegetable"
    return "unknown"


def component_type(component: EstimatedComponent) -> str:
    """Return the normalized component type."""
    return normalize_component_type(component.component_type or component.type)


def component_search_text(component: EstimatedComponent) -> str:
    """Return combined lookup text for one Gemini component."""
    values = [component.name_ru, component.likely_database_match_query]
    return normalized_text(" ".join(value for value in values if value))


def _known_component_values(component: KnownComponent) -> list[str]:
    """Return normalized searchable values for a known component."""
    values = [component.display_name, component.token or "", *component.aliases]
    return [normalized_text(value) for value in values if normalized_text(value)]


def _component_should_use_database(component: EstimatedComponent) -> bool:
    """Return whether this Gemini component should be matched against the DB."""
    return component.should_use_database_if_available or component_type(component) in {
        "carb_base",
        "known_component",
    }


def match_known_component(
    component: EstimatedComponent,
    known_components: list[KnownComponent],
) -> MatchedKnownComponent | None:
    """Return the best known component for a Gemini component."""
    if not _component_should_use_database(component):
        return None
    queries = _component_query_values(component)
    if not queries:
        return None

    best: tuple[int, KnownComponent, str] | None = None
    for known_component in known_components:
        for value in _known_component_values(known_component):
            if not value:
                continue
            for query in queries:
                rank = _match_rank(query, value)
                if rank is None:
                    continue
                candidate = (rank, known_component, value)
                if best is None or candidate[0] < best[0]:
                    best = candidate
    if best is None:
        return None
    return MatchedKnownComponent(
        component=component,
        known_component=best[1],
        matched_query=best[2],
    )


def _raw_item_totals(item: EstimatedItem) -> dict[str, float | None]:
    """Return raw model item totals."""
    return {
        field: _round_or_none(getattr(item, model_field))
        for field, model_field in MODEL_ITEM_FIELDS.items()
    }


def _component_raw_value(component: EstimatedComponent, field: str) -> float | None:
    """Return a component raw model macro value."""
    return _round_or_none(getattr(component, COMPONENT_FIELDS[field], None))


def _known_value(component: KnownComponent, field: str) -> float | None:
    """Return a known component macro value."""
    return _round_or_none(getattr(component, field))


def _round_or_none(value: float | None) -> float | None:
    """Round a value while preserving unknown as None."""
    if value is None:
        return None
    return round(float(value), 1)


def _component_has_any_macro(component: EstimatedComponent) -> bool:
    """Return whether component-level macros are available."""
    return any(
        _component_raw_value(component, macro_field) is not None
        for macro_field in MACRO_FIELDS
    )


def adjust_item_with_known_components(
    item: EstimatedItem,
    known_components: list[KnownComponent],
) -> KnownComponentAdjustment:
    """Return known-component macro adjustment for a visual estimate."""
    raw_totals = _raw_item_totals(item)
    components = item.component_estimates
    matches = [
        match
        for component in components
        if (match := match_known_component(component, known_components)) is not None
    ]
    component_rows = _component_rows(components, matches)
    field_sources = {
        macro_field: "gemini_visual_estimate" for macro_field in MACRO_FIELDS
    }

    if not matches:
        return KnownComponentAdjustment(
            matches=[],
            raw_model_totals=raw_totals,
            adjusted_totals=raw_totals,
            field_sources=field_sources,
            component_rows=component_rows,
            warning=_missing_component_warning(item),
        )

    component_level_available = any(_component_has_any_macro(row) for row in components)
    adjusted_totals: dict[str, float | None] = {}
    for macro_field in MACRO_FIELDS:
        known_sources = [
            match
            for match in matches
            if _known_value(match.known_component, macro_field) is not None
        ]
        if component_level_available:
            adjusted_totals[macro_field] = _sum_component_field(
                components,
                matches,
                macro_field,
            )
            field_sources[macro_field] = (
                "mixed_known_component_and_visual_estimate"
                if known_sources
                else "gemini_visual_estimate"
            )
            continue

        adjusted_totals[macro_field] = _replacement_total_from_raw(
            item,
            matches,
            macro_field,
        )
        field_sources[macro_field] = (
            "mixed_known_component_and_visual_estimate"
            if known_sources
            and adjusted_totals[macro_field] != raw_totals[macro_field]
            else "gemini_visual_estimate"
        )

    warning = None
    if not component_level_available and _has_known_values_without_component_raw(
        matches
    ):
        warning = (
            "Сохранённый компонент найден, но модель не дала компонентную оценку "
            "для части полей. Эти поля оставлены по общей визуальной оценке."
        )

    return KnownComponentAdjustment(
        matches=matches,
        raw_model_totals=raw_totals,
        adjusted_totals=adjusted_totals,
        field_sources=field_sources,
        component_rows=_component_rows(components, matches, adjusted=True),
        warning=warning,
    )


def _has_known_values_without_component_raw(
    matches: list[MatchedKnownComponent],
) -> bool:
    """Return whether known fields could not safely replace raw component fields."""
    return any(
        _known_value(match.known_component, macro_field) is not None
        and _component_raw_value(match.component, macro_field) is None
        for match in matches
        for macro_field in MACRO_FIELDS
    )


def _sum_component_field(
    components: list[EstimatedComponent],
    matches: list[MatchedKnownComponent],
    field: str,
) -> float | None:
    """Sum component-level values, replacing matched known fields when available."""
    total = 0.0
    has_value = False
    match_by_id = {id(match.component): match for match in matches}
    for component in components:
        match = match_by_id.get(id(component))
        value = (
            _known_value(match.known_component, field)
            if match is not None
            else None
        )
        if value is None:
            value = _component_raw_value(component, field)
        if value is None:
            continue
        total += value
        has_value = True
    return round(total, 1) if has_value else None


def _replacement_total_from_raw(
    item: EstimatedItem,
    matches: list[MatchedKnownComponent],
    field: str,
) -> float | None:
    """Adjust raw full-item total by replacing raw matched component values."""
    raw_total = _raw_item_totals(item)[field]
    if raw_total is None:
        return None
    adjusted = raw_total
    changed = False
    for match in matches:
        known_value = _known_value(match.known_component, field)
        component_raw = _component_raw_value(match.component, field)
        if known_value is None or component_raw is None:
            continue
        adjusted = adjusted - component_raw + known_value
        changed = True
    return round(adjusted, 1) if changed else raw_total


def _component_rows(
    components: list[EstimatedComponent],
    matches: list[MatchedKnownComponent],
    *,
    adjusted: bool = False,
) -> list[dict[str, Any]]:
    """Serialize component-level estimates and known-component replacements."""
    match_by_id = {id(match.component): match for match in matches}
    rows: list[dict[str, Any]] = []
    for component in components:
        match = match_by_id.get(id(component))
        source = (
            match.known_component.source_kind
            if match is not None
            else "gemini_visual_estimate"
        )
        raw_values = {
            field: _component_raw_value(component, field) for field in MACRO_FIELDS
        }
        final_values: dict[str, float | None] = {}
        field_sources: dict[str, str] = {}
        for macro_field, raw_value in raw_values.items():
            known_value = (
                _known_value(match.known_component, macro_field)
                if match is not None
                else None
            )
            final_values[macro_field] = (
                known_value if known_value is not None else raw_value
            )
            field_sources[macro_field] = (
                source if known_value is not None else "gemini_visual_estimate"
            )
        rows.append(
            {
                "name_ru": component.name_ru,
                "component_type": component_type(component),
                "estimated_grams_mid": component.estimated_grams_mid,
                "visual_count": component.visual_count,
                "raw_model_values": raw_values,
                "final_values": final_values if adjusted else raw_values,
                "field_sources": field_sources,
                "source": source,
                "source_label": (
                    match.known_component.source_label
                    if match is not None
                    else "фото-оценка"
                ),
                "matched_component_id": (
                    str(match.known_component.id) if match is not None else None
                ),
                "matched_component_name": (
                    match.known_component.display_name if match is not None else None
                ),
                "matched_query": match.matched_query if match is not None else None,
                "evidence": list(component.evidence),
                "assumptions": list(component.assumptions),
            }
        )
    return rows


def known_component_evidence_payload(
    adjustment: KnownComponentAdjustment,
) -> dict[str, Any] | None:
    """Serialize an adjustment for item evidence JSON."""
    if not adjustment.matches:
        return None
    return {
        "raw_model_estimate": adjustment.raw_model_totals,
        "final_backend_adjusted_values": adjustment.adjusted_totals,
        "field_sources": adjustment.field_sources,
        "components": adjustment.component_rows,
        "source": "known_component",
        "source_label": "значения из базы компонентов",
        "matches": [
            {
                "component_name": match.component.name_ru,
                "component_type": component_type(match.component),
                "estimated_grams_mid": match.component.estimated_grams_mid,
                "visual_count": match.component.visual_count,
                "likely_database_match_query": (
                    match.component.likely_database_match_query
                ),
                "matched_query": match.matched_query,
                "known_component_id": str(match.known_component.id),
                "known_component_kind": match.known_component.kind,
                "known_component_token": match.known_component.token,
                "known_component_display_name": match.known_component.display_name,
                "known_component_grams": match.known_component.grams,
                "known_component_carbs_g": match.known_component.carbs_g,
                "known_component_protein_g": match.known_component.protein_g,
                "known_component_fat_g": match.known_component.fat_g,
                "known_component_fiber_g": match.known_component.fiber_g,
                "known_component_kcal": match.known_component.kcal,
            }
            for match in adjustment.matches
        ],
    }


def _missing_component_warning(item: EstimatedItem) -> str | None:
    """Return a warning when a requested known component could not be matched."""
    if any(
        _component_should_use_database(component)
        for component in item.component_estimates
    ):
        return "Углеводная основа не найдена в базе. Значение оценено визуально."
    return None


def known_component_warning(adjustment: KnownComponentAdjustment) -> str | None:
    """Return the public warning for the adjustment."""
    return adjustment.warning


def item_to_component(item: EstimatedItem) -> EstimatedComponent:
    """Convert a legacy split Gemini item into a component estimate."""
    inferred = infer_component_type(item.display_name_ru or item.name)
    return EstimatedComponent(
        name_ru=item.display_name_ru or item.name,
        component_type=inferred,  # type: ignore[arg-type]
        estimated_grams_low=item.grams_low,
        estimated_grams_mid=item.grams_mid,
        estimated_grams_high=item.grams_high,
        visual_count=item.count_detected,
        carbs_g_mid=item.carbs_g_mid,
        protein_g_mid=item.protein_g_mid,
        fat_g_mid=item.fat_g_mid,
        fiber_g_mid=item.fiber_g_mid,
        kcal_mid=item.kcal_mid,
        likely_database_match_query=item.display_name_ru or item.name,
        should_use_database_if_available=inferred in {"carb_base", "known_component"},
        confidence=item.confidence,
        evidence=list(item.evidence),
        assumptions=list(item.assumptions),
    )


def can_collapse_plated_items(items: list[EstimatedItem]) -> bool:
    """Return whether split plated items look like one coherent wrap/sandwich."""
    if len(items) <= 1:
        return False
    if any(item.scenario != "PLATED" for item in items):
        return False

    primary_keys = {
        item.primary_photo_id
        or ",".join(item.source_photo_ids)
        or str(item.source_photo_indices)
        for item in items
    }
    if len(primary_keys) > 1:
        return False
    components = [item_to_component(item) for item in items]
    known_types = {"carb_base", "known_component"}
    has_anchor = any(
        component_type(component) in known_types for component in components
    )
    has_non_anchor = any(
        component_type(component) not in known_types for component in components
    )
    return has_anchor and has_non_anchor


def collapse_plated_items(items: list[EstimatedItem]) -> list[EstimatedItem]:
    """Collapse one over-split plated wrap into a single item with components."""
    if not can_collapse_plated_items(items):
        return items

    components = [item_to_component(item) for item in items]
    evidence: list[str] = []
    assumptions: list[str] = [
        (
            "Позиции модели объединены в один ролл/лаваш, потому что относятся "
            "к одному блюду на одном фото."
        )
    ]
    for item in items:
        evidence.extend(str(entry) for entry in item.evidence)
        assumptions.extend(str(entry) for entry in item.assumptions)

    anchor = next(
        (
            component
            for component in components
            if component_type(component) in {"carb_base", "known_component"}
        ),
        None,
    )
    has_chicken = any(
        "кур" in normalized_text(component.name_ru)
        or "chicken" in normalized_text(component.name_ru)
        for component in components
    )
    display_name = (
        "Лаваш с курицей"
        if anchor is not None and has_chicken
        else f"{anchor.name_ru} с начинкой"
        if anchor is not None
        else "Блюдо по фото"
    )

    return [
        EstimatedItem(
            name=display_name,
            display_name_ru=display_name,
            brand=None,
            source_photo_ids=list(dict.fromkeys(items[0].source_photo_ids)),
            primary_photo_id=items[0].primary_photo_id,
            source_photo_indices=list(dict.fromkeys(items[0].source_photo_indices)),
            item_type="plated_food",
            scenario="PLATED",
            component_estimates=components,
            grams_low=_sum_optional(item.grams_low for item in items),
            grams_mid=_sum_optional(item.grams_mid for item in items),
            grams_high=_sum_optional(item.grams_high for item in items),
            carbs_g_low=_sum_optional(item.carbs_g_low for item in items),
            carbs_g_mid=_sum_optional(item.carbs_g_mid for item in items),
            carbs_g_high=_sum_optional(item.carbs_g_high for item in items),
            protein_g_mid=_sum_optional(item.protein_g_mid for item in items),
            fat_g_mid=_sum_optional(item.fat_g_mid for item in items),
            fiber_g_mid=_sum_optional(item.fiber_g_mid for item in items),
            kcal_mid=_sum_optional(item.kcal_mid for item in items),
            confidence=min(item.confidence for item in items),
            confidence_reason=(
                "Модель разложила одно блюдо на компоненты; backend сохранил "
                "один черновик с компонентами."
            ),
            confidence_reason_ru=(
                "Модель разложила одно блюдо на компоненты; backend сохранил "
                "один черновик с компонентами."
            ),
            assumptions=list(dict.fromkeys(assumptions)),
            evidence=list(dict.fromkeys(evidence)),
        )
    ]


def _sum_optional(values: Any) -> float | None:
    """Sum optional numeric values, returning None when no values are known."""
    known = [float(value) for value in values if value is not None]
    return round(sum(known), 2) if known else None
