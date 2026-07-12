"""Owner-scoped orchestration for retrospective IOB/COB timing fits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session

from glucotracker.application.on_board.classification import (
    is_liquid_meal,
    is_rapid_insulin_event,
    meal_category_scope,
    meal_pattern_key,
)
from glucotracker.application.on_board.fitter import (
    MODEL_VERSION,
    CgmSample,
    CobTimingOverride,
    FitterConfig,
    MealEvent,
    OnBoardFitResult,
    OnBoardTimingModel,
    RapidInsulinEvent,
    RetrospectiveDay,
    fit_on_board_timing,
)
from glucotracker.application.time import local_now, local_timezone, local_wall_time
from glucotracker.application.twin.kernels import (
    CarbProfileWeights,
    PersonalizedInsulinKernel,
    carb_profile_prior_weights,
)
from glucotracker.infra.db.models import Meal
from glucotracker.infra.db.repositories.on_board import OnBoardRepository
from glucotracker.infra.db.repositories.twin import TwinRepository

MAX_TRAINING_DAYS = 90
COMPLETION_LAG_MINUTES = 420
RAPID_SCOPE_KEY = "rapid"

PRODUCTION_FITTER_CONFIG = FitterConfig(
    min_day_coverage_fraction=0.85,
    max_cgm_gap_minutes=20,
    min_training_days=7,
    min_holdout_days=3,
    min_rapid_events=30,
    min_rapid_event_days=10,
    min_meal_events=30,
    min_meal_event_days=10,
)


@dataclass(frozen=True, slots=True)
class OnBoardFitRun:
    """Application-level result with persistence counts for logging/tests."""

    result: OnBoardFitResult
    training_from: datetime | None
    training_to: datetime | None
    activated_fit_count: int
    recorded_fit_count: int


class OnBoardFitService:
    """Build a private retrospective dataset, fit it, and cache validation."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.repository = OnBoardRepository(session, user_id)

    def fit_recent(self, *, days: int = MAX_TRAINING_DAYS) -> OnBoardFitRun:
        """Fit a bounded rolling window ending before the incomplete tail."""
        bounded_days = max(1, min(days, MAX_TRAINING_DAYS))
        now = local_now()
        return self.fit_range(now - timedelta(days=bounded_days), now)

    def fit_range(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> OnBoardFitRun:
        """Fit only completed local-wall days inside the requested range."""
        requested_from = local_wall_time(from_datetime)
        requested_to = local_wall_time(to_datetime)
        latest_complete_instant = min(
            requested_to,
            local_now() - timedelta(minutes=COMPLETION_LAG_MINUTES),
        )
        training_to = datetime.combine(latest_complete_instant.date(), time.min)
        lower_bound = max(
            requested_from,
            training_to - timedelta(days=MAX_TRAINING_DAYS),
        )
        training_from = _ceil_to_local_day(lower_bound)

        fallback = self._active_model()
        if training_to <= training_from:
            result = fit_on_board_timing(
                (),
                fallback=fallback,
                config=PRODUCTION_FITTER_CONFIG,
            )
            recorded = self._persist_attempt(
                result,
                training_from=None,
                training_to=None,
                fallback=fallback,
            )
            return OnBoardFitRun(
                result=result,
                training_from=None,
                training_to=None,
                activated_fit_count=0,
                recorded_fit_count=recorded,
            )

        days = self._retrospective_days(training_from, training_to)
        result = fit_on_board_timing(
            days,
            fallback=fallback,
            config=PRODUCTION_FITTER_CONFIG,
        )
        recorded = self._persist_attempt(
            result,
            training_from=training_from,
            training_to=training_to,
            fallback=fallback,
        )
        activated = recorded if result.accepted else 0
        return OnBoardFitRun(
            result=result,
            training_from=training_from,
            training_to=training_to,
            activated_fit_count=activated,
            recorded_fit_count=recorded,
        )

    def _active_model(self) -> OnBoardTimingModel:
        twin_params = TwinRepository(
            self.session,
            self.user_id,
        ).get_or_create_params(persist=False)
        iob_row = self.repository.get_active_fit("iob", RAPID_SCOPE_KEY)
        insulin_kernel: PersonalizedInsulinKernel | None = None
        if iob_row is not None:
            try:
                insulin_kernel = PersonalizedInsulinKernel.from_mapping(
                    iob_row.params_json
                )
            except ValueError:
                insulin_kernel = None

        overrides: list[CobTimingOverride] = []
        seen: set[str] = set()
        for row in self.repository.list_active_fits("cob"):
            if row.scope_key in seen:
                continue
            seen.add(row.scope_key)
            try:
                payload = row.params_json
                weights = CarbProfileWeights.from_mapping(
                    payload.get("weights", payload)
                )
                scope: Literal["exact", "category"] = (
                    "exact" if row.scope_key.startswith("pattern:") else "category"
                )
                overrides.append(
                    CobTimingOverride(
                        scope=scope,
                        scope_key=row.scope_key,
                        weights=weights,
                        event_count=row.sample_count,
                        day_count=row.day_count,
                        # Stored weights are already shrunken by the fitter.
                        learned_weight=1.0,
                    )
                )
            except (AttributeError, TypeError, ValueError):
                continue
        return OnBoardTimingModel(
            insulin_kernel=insulin_kernel,
            legacy_dia_minutes=twin_params.dia_minutes,
            normal_carb_duration_minutes=twin_params.carb_duration_minutes,
            cob_overrides=tuple(overrides),
        )

    def _retrospective_days(
        self,
        training_from: datetime,
        training_to: datetime,
    ) -> tuple[RetrospectiveDay, ...]:
        source_from = training_from - timedelta(
            minutes=max(
                PRODUCTION_FITTER_CONFIG.insulin_lookback_minutes,
                PRODUCTION_FITTER_CONFIG.meal_lookback_minutes,
            )
        )
        glucose_rows = self.repository.list_training_glucose(
            training_from,
            training_to,
        )
        insulin_rows = self.repository.list_training_insulin(
            source_from,
            training_to,
        )
        meal_rows = self.repository.list_training_meals(source_from, training_to)

        glucose = [
            CgmSample(
                timestamp=_nightscout_local(row.timestamp),
                glucose_mmol_l=float(row.value_mmol_l),
            )
            for row in glucose_rows
            if row.value_mmol_l > 0
        ]
        rapid = [
            RapidInsulinEvent(
                timestamp=_nightscout_local(row.timestamp),
                units=float(row.insulin_units or 0.0),
            )
            for row in insulin_rows
            if row.insulin_units is not None
            and row.insulin_units > 0
            and is_rapid_insulin_event(
                insulin_type=row.insulin_type,
                event_type=row.event_type,
            )
        ]
        meals = [self._meal_event(row) for row in meal_rows]

        result: list[RetrospectiveDay] = []
        day_start = training_from
        first = True
        while day_start < training_to:
            day_end = day_start + timedelta(days=1)
            event_start = source_from if first else day_start
            result.append(
                RetrospectiveDay(
                    day_start=day_start,
                    cgm=tuple(
                        sample
                        for sample in glucose
                        if day_start <= sample.timestamp < day_end
                    ),
                    rapid_insulin=tuple(
                        event
                        for event in rapid
                        if event_start <= event.timestamp < day_end
                    ),
                    meals=tuple(
                        meal
                        for meal in meals
                        if event_start <= meal.timestamp < day_end
                    ),
                )
            )
            first = False
            day_start = day_end
        return tuple(result)

    def _meal_event(self, meal: Meal) -> MealEvent:
        carbs = float(meal.total_carbs_g or 0.0)
        protein = float(meal.total_protein_g or 0.0)
        fat = float(meal.total_fat_g or 0.0)
        fiber = float(meal.total_fiber_g or 0.0)
        item_names = [item.name for item in meal.items if item.name]
        liquid = is_liquid_meal(
            ai_categories=meal.ai_categories,
            derived_categories=meal.derived_categories,
            title=meal.title,
            item_names=item_names,
        )
        taste_profile = str(
            (meal.ai_categories or {}).get("taste_profile") or ""
        ).casefold()
        prior = carb_profile_prior_weights(
            carbs_g=carbs,
            protein_g=protein,
            fat_g=fat,
            fiber_g=fiber,
            is_liquid=liquid,
            is_sweetened=taste_profile in {"sweet", "drink_sweet"},
        )
        exact_key: str | None = None
        category_key: str | None = None
        if _eligible_personal_meal(meal):
            identity_keys = [
                f"product:{item.product_id}" if item.product_id else item.name
                for item in meal.items
                if item.product_id or item.name
            ]
            exact_key = "pattern:" + meal_pattern_key(
                item_identity_keys=identity_keys,
                title=meal.title,
                carbs_g=carbs,
                protein_g=protein,
                fat_g=fat,
                fiber_g=fiber,
            )
            category_key = meal_category_scope(
                dominant_profile=prior.dominant_profile,
                is_liquid=liquid,
            )
        return MealEvent(
            timestamp=meal.eaten_at,
            carbs_g=carbs,
            prior_weights=prior,
            exact_key=exact_key,
            category_key=category_key,
        )

    def _persist_attempt(
        self,
        result: OnBoardFitResult,
        *,
        training_from: datetime | None,
        training_to: datetime | None,
        fallback: OnBoardTimingModel,
    ) -> int:
        candidate = result.candidate_model or result.model
        metrics = result.metrics.to_mapping()
        metrics.update({"reason": result.reason, "status": result.status})
        validation_mae = (
            result.metrics.candidate.mae_mmol
            if result.metrics.candidate is not None
            else None
        )
        baseline_mae = (
            result.metrics.baseline.mae_mmol
            if result.metrics.baseline is not None
            else None
        )
        day_count = result.metrics.complete_day_count
        recorded = 0

        iob_changed = candidate.insulin_kernel != fallback.insulin_kernel
        if iob_changed or result.status == "insufficient_data":
            self.repository.add_fit(
                kind="iob",
                scope_key=RAPID_SCOPE_KEY,
                model_version=MODEL_VERSION,
                params_json=_insulin_params(candidate),
                metrics_json=metrics,
                training_from=training_from,
                training_to=training_to,
                sample_count=result.metrics.rapid_insulin_event_count,
                day_count=day_count,
                validation_mae_mmol=validation_mae,
                baseline_mae_mmol=baseline_mae,
                confidence=result.confidence,
                status=result.status,
                activate=result.accepted,
            )
            recorded += 1

        fallback_overrides = {
            (item.scope, item.scope_key): item for item in fallback.cob_overrides
        }
        changed_overrides = [
            item
            for item in candidate.cob_overrides
            if fallback_overrides.get((item.scope, item.scope_key)) != item
        ]
        for override in changed_overrides:
            self.repository.add_fit(
                kind="cob",
                scope_key=override.scope_key,
                model_version=MODEL_VERSION,
                params_json={
                    "weights": override.weights.to_mapping(),
                    # The weights above are the fitter's final shrunken value.
                    "learned_weight": 1.0,
                    "fit_shrinkage": override.learned_weight,
                    "scope": override.scope,
                },
                metrics_json=metrics,
                training_from=training_from,
                training_to=training_to,
                sample_count=override.event_count,
                day_count=override.day_count,
                validation_mae_mmol=validation_mae,
                baseline_mae_mmol=baseline_mae,
                confidence=result.confidence,
                status=result.status,
                activate=result.accepted,
            )
            recorded += 1

        if result.accepted:
            self.repository.deactivate_cob_scopes_except(
                {override.scope_key for override in candidate.cob_overrides},
            )

        if recorded == 0 and result.status == "rejected":
            self.repository.add_fit(
                kind="iob",
                scope_key=RAPID_SCOPE_KEY,
                model_version=MODEL_VERSION,
                params_json=_insulin_params(candidate),
                metrics_json=metrics,
                training_from=training_from,
                training_to=training_to,
                sample_count=result.metrics.rapid_insulin_event_count,
                day_count=day_count,
                validation_mae_mmol=validation_mae,
                baseline_mae_mmol=baseline_mae,
                confidence="none",
                status="rejected",
                activate=False,
            )
            recorded = 1
        return recorded


def _insulin_params(model: OnBoardTimingModel) -> dict[str, object]:
    if model.insulin_kernel is not None:
        return model.insulin_kernel.to_mapping()
    return {
        "source": "legacy_population",
        "legacy_dia_minutes": model.legacy_dia_minutes,
    }


def _eligible_personal_meal(meal: Meal) -> bool:
    response = meal.postprandial_response
    if not isinstance(response, dict):
        return False
    if meal.postprandial_computed_at is None:
        return False
    if _as_utc(meal.postprandial_computed_at) < _as_utc(meal.updated_at):
        return False
    if response.get("is_hypo_recovery") or response.get("is_meal_during_low"):
        return False
    if float(response.get("coverage_180min") or 0.0) < 0.80:
        return False
    if float(response.get("extended_coverage_300min") or 0.0) < 0.80:
        return False
    flags = response.get("quality_flags") or []
    return "low_coverage" not in flags


def _ceil_to_local_day(value: datetime) -> datetime:
    start = datetime.combine(value.date(), time.min)
    return start if value == start else start + timedelta(days=1)


def _nightscout_local(value: datetime) -> datetime:
    utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value
    return utc_value.astimezone(local_timezone()).replace(tzinfo=None)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
