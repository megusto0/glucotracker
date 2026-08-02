"""Daily retrospective therapy review assembled from episodes and CGM.

The adjusted values are hindsight explanations, never prospective treatment
recommendations. Insulin rows use the observed glucose error divided by ISF.
Carbohydrate-rescue rows use a deliberately explicit coarse conversion so the
UI can show how the actual rescue compared with the later glucose outcome.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.api.schemas import GlucoseDashboardPoint
from glucotracker.application.episode_therapy import (
    EpisodeTherapy,
    TherapyClass,
    classify_episode_therapy,
)
from glucotracker.application.episodes import EpisodeComponent, EpisodeQueryService
from glucotracker.application.glucose_dashboard import GlucoseDashboardService
from glucotracker.application.insulin_recommendation import (
    DEFAULT_CORRECTION_ISF_MMOL_L_PER_UNIT,
    HistoricalInsulinRecommendationService,
    _trusted_isf,
)
from glucotracker.application.time import local_now
from glucotracker.infra.db.models import TherapyReviewCache
from glucotracker.infra.db.repositories.twin import TwinRepository

ReviewUnit = Literal["U", "g"]
AdjustmentStatus = Literal[
    "ready",
    "no_actual",
    "no_outcome",
    "calculation_withheld",
]

POINT_TOLERANCE = timedelta(minutes=15)
DEFAULT_CARB_ADJUSTMENT_G_PER_MMOL_L = 4.0
# v2: the fall gate now judges where a fall lands rather than how fast it
# moves, and follow-up boluses reach the meal training label. Both change
# what a closed day computes, so cached v1 rows must not be served.
THERAPY_REVIEW_MODEL_VERSION = "retrospective-therapy-review-v2"


@dataclass(frozen=True)
class TherapyReviewItem:
    """One episode rendered as a comparable daily review row."""

    key: str
    title: str
    classification: TherapyClass
    confidence: Literal["low", "medium", "high"]
    start_at: datetime
    horizon_minutes: int
    value_unit: ReviewUnit
    glucose_start_raw: float | None
    glucose_start_normalized: float | None
    glucose_after_raw: float | None
    glucose_after_normalized: float | None
    actual_value: float | None
    calculated_value: float | None
    adjusted_actual_value: float | None
    target_mmol_l: float
    isf_mmol_l_per_unit: float | None
    calculation_status: str
    adjustment_status: AdjustmentStatus
    total_carbs_g: float
    total_insulin_units: float
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TherapyReviewDay:
    """Daily collection with the assumptions used by hindsight adjustment."""

    date: date
    target_mmol_l: float
    horizon_minutes: int
    items: list[TherapyReviewItem]
    cached: bool
    computed_at: datetime
    model_version: str


class TherapyReviewService:
    """Build a complete local-day therapy review for one owner."""

    def __init__(self, session: Session, user_id) -> None:
        self.session = session
        self.user_id = user_id
        self.episodes = EpisodeQueryService(session, user_id)
        self.recommendations = HistoricalInsulinRecommendationService(
            session,
            user_id,
        )

    def day(
        self,
        day: date,
        *,
        target_mmol_l: float,
        horizon_minutes: int,
        force_recalculate: bool = False,
    ) -> TherapyReviewDay:
        """Read a saved closed day, or calculate and persist it once."""
        cacheable = day < local_now().date()
        target_tenths = round(target_mmol_l * 10)
        cache = (
            self._cached(day, target_tenths, horizon_minutes)
            if cacheable and not force_recalculate
            else None
        )
        if cache is not None:
            return _day_from_cache(cache)

        review = self._calculate_day(
            day,
            target_mmol_l=target_mmol_l,
            horizon_minutes=horizon_minutes,
        )
        if cacheable:
            self._save(
                review,
                target_tenths=target_tenths,
                horizon_minutes=horizon_minutes,
            )
        return review

    def _calculate_day(
        self,
        day: date,
        *,
        target_mmol_l: float,
        horizon_minutes: int,
    ) -> TherapyReviewDay:
        local_from = datetime.combine(day, time.min)
        local_to = local_from + timedelta(days=1)
        components = self.episodes.components(local_from, local_to)
        points = GlucoseDashboardService(
            self.session,
            self.user_id,
        ).dashboard(
            local_from - timedelta(minutes=30),
            local_to + timedelta(minutes=horizon_minutes),
            "normalized",
        ).points
        self.recommendations.preload_history(local_from, local_to)

        params = TwinRepository(
            self.session,
            self.user_id,
        ).get_or_create_params(persist=False)
        isf = _trusted_isf(params) or DEFAULT_CORRECTION_ISF_MMOL_L_PER_UNIT

        items = [
            self._item(
                component,
                classify_episode_therapy(component, points),
                points,
                target_mmol_l=target_mmol_l,
                horizon_minutes=horizon_minutes,
                isf=isf,
            )
            for component in components
        ]
        return TherapyReviewDay(
            date=day,
            target_mmol_l=round(target_mmol_l, 1),
            horizon_minutes=horizon_minutes,
            items=items,
            cached=False,
            computed_at=datetime.now(UTC),
            model_version=THERAPY_REVIEW_MODEL_VERSION,
        )

    def _cached(
        self,
        day: date,
        target_tenths: int,
        horizon_minutes: int,
    ) -> TherapyReviewCache | None:
        return self.session.scalar(
            select(TherapyReviewCache).where(
                TherapyReviewCache.owner_id == self.user_id,
                TherapyReviewCache.date == day,
                TherapyReviewCache.target_tenths == target_tenths,
                TherapyReviewCache.horizon_minutes == horizon_minutes,
                TherapyReviewCache.model_version
                == THERAPY_REVIEW_MODEL_VERSION,
            )
        )

    def _save(
        self,
        review: TherapyReviewDay,
        *,
        target_tenths: int,
        horizon_minutes: int,
    ) -> None:
        cache = self._cached(review.date, target_tenths, horizon_minutes)
        result_json = {
            "items": [_item_to_json(item) for item in review.items],
        }
        if cache is None:
            cache = TherapyReviewCache(
                owner_id=self.user_id,
                date=review.date,
                target_tenths=target_tenths,
                horizon_minutes=horizon_minutes,
                model_version=THERAPY_REVIEW_MODEL_VERSION,
                result_json=result_json,
                computed_at=review.computed_at,
            )
            self.session.add(cache)
        else:
            cache.result_json = result_json
            cache.computed_at = review.computed_at
        self.session.commit()

    def _item(
        self,
        component: EpisodeComponent,
        therapy: EpisodeTherapy,
        points: list[GlucoseDashboardPoint],
        *,
        target_mmol_l: float,
        horizon_minutes: int,
        isf: float,
    ) -> TherapyReviewItem:
        start = _nearest(points, component.start_at)
        after = _nearest(
            points,
            component.start_at + timedelta(minutes=horizon_minutes),
        )
        start_raw = _raw(start)
        start_normalized = _normalized(start)
        after_raw = _raw(after)
        after_normalized = _normalized(after)
        outcome = after_normalized

        total_carbs = round(
            sum(float(meal.total_carbs_g or 0) for meal in component.meals),
            1,
        )
        total_insulin = round(
            sum(float(event.insulin_units or 0) for event in component.insulin),
            2,
        )
        notes = list(therapy.reasons)

        if therapy.classification == "carb_correction":
            unit: ReviewUnit = "g"
            actual = total_carbs if total_carbs > 0 else None
            calculated = therapy.suggested_carbs_g
            calculation_status = (
                "ready" if calculated is not None else "calculation_withheld"
            )
            adjusted = (
                max(
                    0.0,
                    actual
                    + (target_mmol_l - outcome)
                    * DEFAULT_CARB_ADJUSTMENT_G_PER_MMOL_L,
                )
                if actual is not None and outcome is not None
                else None
            )
            if adjusted is not None:
                adjusted = round(min(adjusted, 100.0), 1)
                notes.append(
                    "ретроспективная поправка углеводов: 4 г на 1 ммоль/л"
                )
        else:
            unit = "U"
            actual = total_insulin if total_insulin > 0 else None
            calculated: float | None = None
            calculation_status = "calculation_withheld"
            if component.meals:
                calculation = self.recommendations.estimate(
                    [meal.id for meal in component.meals],
                    target_mmol_l,
                )
                if calculation is not None:
                    calculated = calculation.total_recommended_units
                    calculation_status = calculation.meal.status
            elif component.insulin:
                correction = self.recommendations.correction_at(
                    component.start_at,
                    target_mmol_l,
                    excluded_insulin_ids={event.id for event in component.insulin},
                )
                if correction.status in {"ready", "not_needed"}:
                    calculated = correction.units or 0.0
                calculation_status = correction.status

            adjusted = (
                max(0.0, actual + (outcome - target_mmol_l) / isf)
                if actual is not None and outcome is not None
                else None
            )
            if adjusted is not None:
                adjusted = round(min(adjusted, 100.0), 1)
                notes.append(
                    "ретроспективная поправка инсулина по ошибке глюкозы и ISF"
                )

        adjustment_status: AdjustmentStatus = (
            "no_actual"
            if actual is None
            else "no_outcome"
            if outcome is None
            else "calculation_withheld"
            if calculated is None
            else "ready"
        )
        return TherapyReviewItem(
            key="|".join(
                sorted(
                    [f"m:{meal.id}" for meal in component.meals]
                    + [f"i:{event.id}" for event in component.insulin]
                )
            ),
            title=_title(component, therapy.classification),
            classification=therapy.classification,
            confidence=therapy.confidence,
            start_at=component.start_at,
            horizon_minutes=horizon_minutes,
            value_unit=unit,
            glucose_start_raw=_rounded(start_raw),
            glucose_start_normalized=_rounded(start_normalized),
            glucose_after_raw=_rounded(after_raw),
            glucose_after_normalized=_rounded(after_normalized),
            actual_value=_rounded(actual),
            calculated_value=_rounded(calculated),
            adjusted_actual_value=_rounded(adjusted),
            target_mmol_l=round(target_mmol_l, 1),
            isf_mmol_l_per_unit=round(isf, 2) if unit == "U" else None,
            calculation_status=calculation_status,
            adjustment_status=adjustment_status,
            total_carbs_g=total_carbs,
            total_insulin_units=total_insulin,
            notes=notes,
        )


def _nearest(
    points: list[GlucoseDashboardPoint],
    target: datetime,
) -> GlucoseDashboardPoint | None:
    if not points:
        return None
    point = min(points, key=lambda candidate: abs(candidate.timestamp - target))
    return point if abs(point.timestamp - target) <= POINT_TOLERANCE else None


def _raw(point: GlucoseDashboardPoint | None) -> float | None:
    return float(point.raw_value) if point is not None else None


def _normalized(point: GlucoseDashboardPoint | None) -> float | None:
    if point is None:
        return None
    return float(
        point.normalized_value
        if point.normalized_value is not None
        else point.raw_value
    )


def _rounded(value: float | None) -> float | None:
    return round(value, 1) if value is not None else None


def _title(component: EpisodeComponent, classification: TherapyClass) -> str:
    titles = [meal.title for meal in component.meals if meal.title]
    if titles:
        return " + ".join(titles)
    if classification == "insulin_correction":
        return "Коррекция инсулином"
    if component.insulin:
        return "Инсулин"
    return "Эпизод"


def _item_to_json(item: TherapyReviewItem) -> dict[str, Any]:
    return {
        **vars(item),
        "start_at": item.start_at.isoformat(),
    }


def _day_from_cache(cache: TherapyReviewCache) -> TherapyReviewDay:
    raw_items = cache.result_json.get("items", [])
    items = [
        TherapyReviewItem(
            **{
                **raw,
                "start_at": datetime.fromisoformat(str(raw["start_at"])),
            }
        )
        for raw in raw_items
        if isinstance(raw, dict) and raw.get("start_at")
    ]
    computed_at = cache.computed_at
    if computed_at.tzinfo is None:
        computed_at = computed_at.replace(tzinfo=UTC)
    return TherapyReviewDay(
        date=cache.date,
        target_mmol_l=cache.target_tenths / 10,
        horizon_minutes=cache.horizon_minutes,
        items=items,
        cached=True,
        computed_at=computed_at,
        model_version=cache.model_version,
    )
