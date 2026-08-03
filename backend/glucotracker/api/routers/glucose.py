"""Glucose dashboard, sensor, and fingerstick endpoints."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from glucotracker.api.dependencies import CurrentUserDep, SessionDep
from glucotracker.api.dependencies.feature import require_feature
from glucotracker.api.schemas import (
    CgmCalibrationModelResponse,
    DayEpisodeInsulinResponse,
    DayEpisodeResponse,
    DayEpisodesResponse,
    DayEpisodeTherapyResponse,
    FingerstickReadingCreate,
    FingerstickReadingPatch,
    FingerstickReadingResponse,
    GlucoseDashboardResponse,
    GlucosePredictionResponse,
    GlucoseTirDailyResponse,
    GlucoseTirDayResponse,
    InsulinRecommendationMatchResponse,
    InsulinRecommendationRequest,
    InsulinRecommendationResponse,
    SensorCodeCreate,
    SensorCodePatch,
    SensorCodeResponse,
    SensorQualityResponse,
    SensorSessionCreate,
    SensorSessionPatch,
    SensorSessionResponse,
    TherapyAnalysisMetricResponse,
    TherapyAnalysisResponse,
    TherapyAnalysisSlotResponse,
    TherapyBasalProfileResponse,
    TherapyBasalSlotResponse,
    TherapyReviewDayResponse,
    TherapyReviewItemResponse,
    TopUpDoseResponse,
)
from glucotracker.application.episode_therapy import classify_episode_therapy
from glucotracker.application.episodes import (
    EpisodeQueryService,
    anchor_meal_id,
)
from glucotracker.application.glucose_dashboard import GlucoseDashboardService
from glucotracker.application.glucose_prediction import GlucosePredictionService
from glucotracker.application.glucose_prediction_audit import (
    GlucosePredictionAuditService,
)
from glucotracker.application.insulin_recommendation import (
    HistoricalInsulinRecommendationService,
)
from glucotracker.application.sensor_codes import SensorCodeService
from glucotracker.application.stats_insights import (
    InsightPeriod,
    generate_glucose_tir_daily,
)
from glucotracker.application.therapy_analysis import TherapyAnalysisService
from glucotracker.application.therapy_review import TherapyReviewService
from glucotracker.application.top_up_dose import TopUpDoseService

router = APIRouter(
    tags=["glucose"],
    dependencies=[Depends(require_feature("glucose"))],
)


@router.get(
    "/glucose/dashboard",
    response_model=GlucoseDashboardResponse,
    operation_id="getGlucoseDashboard",
)
async def get_glucose_dashboard(
    session: SessionDep,
    current_user: CurrentUserDep,
    from_datetime: Annotated[datetime, Query(alias="from")],
    to_datetime: Annotated[datetime, Query(alias="to")],
    mode: Literal["raw", "smoothed", "normalized"] = "raw",
) -> GlucoseDashboardResponse:
    """Return display-only glucose dashboard data from the local cache."""
    return GlucoseDashboardService(session, current_user.id).dashboard(
        from_datetime,
        to_datetime,
        mode,
    )


@router.get(
    "/glucose/prediction",
    response_model=GlucosePredictionResponse,
    operation_id="getGlucosePrediction",
)
def get_glucose_prediction(
    session: SessionDep,
    current_user: CurrentUserDep,
    mode: Literal["raw", "normalized"] = "normalized",
    horizon_minutes: Annotated[int, Query(ge=5, le=90)] = 90,
    step_minutes: Annotated[int, Query(ge=5, le=30)] = 5,
) -> GlucosePredictionResponse:
    """Return a validated personal forecast for informational display only."""
    prediction = GlucosePredictionService(session, current_user.id).predict(
        mode=mode,
        horizon_minutes=horizon_minutes,
        step_minutes=step_minutes,
    )
    GlucosePredictionAuditService(session, current_user.id).record(prediction)
    session.commit()
    return prediction


@router.get(
    "/glucose/episodes",
    response_model=DayEpisodesResponse,
    operation_id="getGlucoseEpisodes",
)
def get_glucose_episodes(
    session: SessionDep,
    current_user: CurrentUserDep,
    from_datetime: Annotated[datetime, Query(alias="from")],
    to_datetime: Annotated[datetime, Query(alias="to")],
) -> DayEpisodesResponse:
    """Return grouped meal/insulin episodes for the range (attribution only)."""
    components = EpisodeQueryService(session, current_user.id).components(
        from_datetime,
        to_datetime,
    )
    therapy_points = GlucoseDashboardService(
        session,
        current_user.id,
    ).dashboard(
        from_datetime - timedelta(minutes=20),
        to_datetime + timedelta(minutes=150),
        "normalized",
    ).points
    episodes: list[DayEpisodeResponse] = []
    for component in components:
        therapy = classify_episode_therapy(component, therapy_points)
        # Raw UTC timestamps, same as /nightscout/insulin — clients convert.
        insulin = [
            DayEpisodeInsulinResponse(
                id=event.id,
                timestamp=event.timestamp,
                insulin_units=event.insulin_units,
                kind="food" if component.meals else "correction",
                anchor_meal_id=anchor_meal_id(event, component),
                editable=(
                    event.source_key.startswith("manual_insulin:")
                    and event.entered_by == "glucotracker"
                    and bool(event.nightscout_id)
                ),
            )
            for event in component.insulin
        ]
        kind = (
            "food"
            if component.meals and component.insulin
            else "food_only"
            if component.meals
            else "correction"
        )
        episodes.append(
            DayEpisodeResponse(
                key="|".join(
                    sorted(
                        [f"m:{meal.id}" for meal in component.meals]
                        + [f"i:{event.id}" for event in component.insulin]
                    )
                ),
                kind=kind,
                start_at=component.start_at,
                end_at=component.end_at,
                meal_ids=[meal.id for meal in component.meals],
                insulin=insulin,
                total_carbs_g=round(
                    sum(meal.total_carbs_g for meal in component.meals), 1
                ),
                total_kcal=round(sum(meal.total_kcal for meal in component.meals), 1),
                total_insulin_units=round(
                    sum(event.insulin_units or 0 for event in component.insulin), 2
                ),
                therapy=DayEpisodeTherapyResponse(**vars(therapy)),
            )
        )
    return DayEpisodesResponse(
        from_datetime=from_datetime,
        to_datetime=to_datetime,
        episodes=episodes,
    )


@router.get(
    "/glucose/therapy-review",
    response_model=TherapyReviewDayResponse,
    operation_id="getGlucoseTherapyReview",
)
def get_glucose_therapy_review(
    session: SessionDep,
    current_user: CurrentUserDep,
    day: Annotated[date, Query(alias="date")],
    target_mmol_l: Annotated[float, Query(ge=3.9, le=10)] = 6.0,
    horizon_minutes: Annotated[int, Query(ge=60, le=240)] = 120,
    force_recalculate: bool = False,
) -> TherapyReviewDayResponse:
    """Return a read-only daily review with explicitly retrospective values."""
    review = TherapyReviewService(session, current_user.id).day(
        day,
        target_mmol_l=target_mmol_l,
        horizon_minutes=horizon_minutes,
        force_recalculate=force_recalculate,
    )
    return TherapyReviewDayResponse(
        date=review.date,
        target_mmol_l=review.target_mmol_l,
        horizon_minutes=review.horizon_minutes,
        cached=review.cached,
        computed_at=review.computed_at,
        model_version=review.model_version,
        items=[
            TherapyReviewItemResponse(**vars(item))
            for item in review.items
        ],
    )


@router.get(
    "/glucose/therapy-analysis",
    response_model=TherapyAnalysisResponse,
    operation_id="getGlucoseTherapyAnalysis",
)
def get_glucose_therapy_analysis(
    session: SessionDep,
    current_user: CurrentUserDep,
    period_days: Annotated[int, Query()] = 90,
    target_mmol_l: Annotated[float, Query(ge=3.9, le=10)] = 6.0,
    to_date: date | None = None,
) -> TherapyAnalysisResponse:
    """Return long-term retrospective ICR and ISF evidence by local time."""
    if period_days not in {30, 90, 180}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="period_days must be one of: 30, 90, 180",
        )
    analysis = TherapyAnalysisService(session, current_user.id).analyze(
        period_days=period_days,
        target_mmol_l=target_mmol_l,
        to_date=to_date,
    )
    return TherapyAnalysisResponse(
        **{
            **vars(analysis),
            "overall_icr_g_per_unit": TherapyAnalysisMetricResponse(
                **vars(analysis.overall_icr_g_per_unit)
            ),
            "overall_isf_mmol_l_per_unit": TherapyAnalysisMetricResponse(
                **vars(analysis.overall_isf_mmol_l_per_unit)
            ),
            "slots": [
                TherapyAnalysisSlotResponse(
                    start_hour=slot.start_hour,
                    end_hour=slot.end_hour,
                    label=slot.label,
                    icr_g_per_unit=TherapyAnalysisMetricResponse(
                        **vars(slot.icr_g_per_unit)
                    ),
                    isf_mmol_l_per_unit=TherapyAnalysisMetricResponse(
                        **vars(slot.isf_mmol_l_per_unit)
                    ),
                )
                for slot in analysis.slots
            ],
            "basal_profile": TherapyBasalProfileResponse(
                window_minutes=analysis.basal_profile.window_minutes,
                washout_minutes=analysis.basal_profile.washout_minutes,
                resting_reference_bpm=(
                    analysis.basal_profile.resting_reference_bpm
                ),
                elevated_hr_threshold_bpm=(
                    analysis.basal_profile.elevated_hr_threshold_bpm
                ),
                quiet_window_count=(
                    analysis.basal_profile.quiet_window_count
                ),
                elevated_hr_window_count=(
                    analysis.basal_profile.elevated_hr_window_count
                ),
                unknown_hr_window_count=(
                    analysis.basal_profile.unknown_hr_window_count
                ),
                slots=[
                    TherapyBasalSlotResponse(
                        hour=slot.hour,
                        label=slot.label,
                        quiet_drift_mmol_l_per_hour=(
                            TherapyAnalysisMetricResponse(
                                **vars(slot.quiet_drift_mmol_l_per_hour)
                            )
                        ),
                        elevated_hr_drift_mmol_l_per_hour=(
                            TherapyAnalysisMetricResponse(
                                **vars(
                                    slot.elevated_hr_drift_mmol_l_per_hour
                                )
                            )
                        ),
                        unknown_hr_drift_mmol_l_per_hour=(
                            TherapyAnalysisMetricResponse(
                                **vars(slot.unknown_hr_drift_mmol_l_per_hour)
                            )
                        ),
                        signal=slot.signal,
                    )
                    for slot in analysis.basal_profile.slots
                ],
            ),
        }
    )


@router.get(
    "/glucose/top-up-dose",
    response_model=TopUpDoseResponse,
    operation_id="getTopUpDose",
)
def get_top_up_dose(
    session: SessionDep,
    current_user: CurrentUserDep,
    target_mmol_l: Annotated[float | None, Query(ge=3.9, le=10.0)] = None,
) -> TopUpDoseResponse:
    """Return the follow-up bolus implied by carbs left, IOB and the target."""
    suggestion = TopUpDoseService(session, current_user.id).suggest(
        target_mmol_l=target_mmol_l,
    )
    return TopUpDoseResponse(**asdict(suggestion))


@router.post(
    "/glucose/insulin-recommendation",
    response_model=InsulinRecommendationResponse,
    operation_id="getInsulinRecommendation",
)
def get_insulin_recommendation(
    payload: InsulinRecommendationRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> InsulinRecommendationResponse:
    """Return a meal estimate plus a safety-gated correction component."""
    calculation = HistoricalInsulinRecommendationService(
        session,
        current_user.id,
    ).estimate(
        payload.meal_ids,
        payload.correction_target_mmol_l,
    )
    if calculation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more accepted meals were not found.",
        )
    estimate = calculation.meal
    correction = calculation.correction
    return InsulinRecommendationResponse(
        status=estimate.status,
        meal_ids=estimate.meal_ids,
        target_carbs_g=estimate.target_carbs_g,
        target_kcal=estimate.target_kcal,
        recommended_units=estimate.recommended_units,
        range_low_units=estimate.range_low_units,
        range_high_units=estimate.range_high_units,
        correction_status=correction.status,
        correction_units=correction.units,
        correction_target_mmol_l=correction.target_mmol_l,
        correction_glucose_mmol_l=correction.glucose_mmol_l,
        correction_projected_glucose_mmol_l=(correction.projected_glucose_mmol_l),
        correction_trend_mmol_l_per_min=correction.trend_mmol_l_per_min,
        correction_isf_mmol_l_per_unit=correction.isf_mmol_l_per_unit,
        correction_isf_source=correction.isf_source,
        correction_iob_units=correction.iob_units,
        correction_projection_source=correction.projection_source,
        correction_projection_horizon_minutes=(
            correction.projection_horizon_minutes
        ),
        correction_projection_calibration_factor=(
            correction.projection_calibration_factor
        ),
        correction_prior_cob_g=correction.prior_cob_g,
        correction_excess_iob_units=correction.excess_iob_units,
        total_recommended_units=calculation.total_recommended_units,
        total_range_low_units=calculation.total_range_low_units,
        total_range_high_units=calculation.total_range_high_units,
        confidence=estimate.confidence,
        matched_episode_count=len(estimate.matches),
        matches=[
            InsulinRecommendationMatchResponse(
                occurred_at=match.occurred_at,
                meal_ids=match.meal_ids,
                carbs_g=match.carbs_g,
                insulin_units=match.insulin_units,
                scaled_units=match.scaled_units,
                similarity=match.similarity,
                deferred_insulin_units=match.deferred_insulin_units,
                outcome_weight=match.outcome_weight,
                glucose_plus_2h_mmol=match.glucose_plus_2h_mmol,
            )
            for match in estimate.matches
        ],
        method_version=estimate.method_version,
    )


@router.get(
    "/glucose/tir-daily",
    response_model=GlucoseTirDailyResponse,
    operation_id="getGlucoseTirDaily",
)
def get_glucose_tir_daily(
    session: SessionDep,
    current_user: CurrentUserDep,
    period: InsightPeriod = "30d",
) -> GlucoseTirDailyResponse:
    """Return per-day TIR band shares for the period (descriptive only)."""
    return GlucoseTirDailyResponse(
        period=period,
        days=[
            GlucoseTirDayResponse.model_validate(day, from_attributes=True)
            for day in generate_glucose_tir_daily(session, current_user.id, period)
        ],
    )


@router.post(
    "/fingersticks",
    response_model=FingerstickReadingResponse,
    status_code=201,
    operation_id="createFingerstick",
)
def create_fingerstick(
    payload: FingerstickReadingCreate,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> FingerstickReadingResponse:
    """Create a manual capillary glucose reading."""
    return GlucoseDashboardService(session, current_user.id).create_fingerstick(payload)


@router.get(
    "/fingersticks",
    response_model=list[FingerstickReadingResponse],
    operation_id="listFingersticks",
)
def list_fingersticks(
    session: SessionDep,
    current_user: CurrentUserDep,
    from_datetime: Annotated[datetime | None, Query(alias="from")] = None,
    to_datetime: Annotated[datetime | None, Query(alias="to")] = None,
) -> list[FingerstickReadingResponse]:
    """List manual capillary glucose readings."""
    return GlucoseDashboardService(session, current_user.id).list_fingersticks(
        from_datetime,
        to_datetime,
    )


@router.patch(
    "/fingersticks/{fingerstick_id}",
    response_model=FingerstickReadingResponse,
    operation_id="patchFingerstick",
)
def patch_fingerstick(
    fingerstick_id: UUID,
    payload: FingerstickReadingPatch,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> FingerstickReadingResponse:
    """Patch a manual capillary glucose reading."""
    return GlucoseDashboardService(session, current_user.id).patch_fingerstick(
        fingerstick_id,
        payload,
    )


@router.delete(
    "/fingersticks/{fingerstick_id}",
    status_code=204,
    operation_id="deleteFingerstick",
)
def delete_fingerstick(
    fingerstick_id: UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> None:
    """Delete a manual capillary glucose reading."""
    GlucoseDashboardService(session, current_user.id).delete_fingerstick(fingerstick_id)


@router.get(
    "/sensors",
    response_model=list[SensorSessionResponse],
    operation_id="listSensors",
)
def list_sensors(
    session: SessionDep,
    current_user: CurrentUserDep,
) -> list[SensorSessionResponse]:
    """List sensor sessions."""
    return GlucoseDashboardService(session, current_user.id).list_sensors()


@router.post(
    "/sensors",
    response_model=SensorSessionResponse,
    status_code=201,
    operation_id="createSensor",
)
def create_sensor(
    payload: SensorSessionCreate,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> SensorSessionResponse:
    """Create a sensor session."""
    return GlucoseDashboardService(session, current_user.id).create_sensor(payload)


@router.patch(
    "/sensors/{sensor_id}",
    response_model=SensorSessionResponse,
    operation_id="patchSensor",
)
def patch_sensor(
    sensor_id: UUID,
    payload: SensorSessionPatch,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> SensorSessionResponse:
    """Patch a sensor session."""
    return GlucoseDashboardService(session, current_user.id).patch_sensor(
        sensor_id,
        payload,
    )


@router.get(
    "/glucose/sensor-codes",
    response_model=list[SensorCodeResponse],
    operation_id="listSensorCodes",
)
def list_sensor_codes(
    session: SessionDep,
    current_user: CurrentUserDep,
) -> list[SensorCodeResponse]:
    """List scanned sensor Data Matrix codes."""
    return SensorCodeService(session, current_user.id).list_codes()


@router.post(
    "/glucose/sensor-codes",
    response_model=SensorCodeResponse,
    status_code=201,
    operation_id="createSensorCode",
)
def create_sensor_code(
    payload: SensorCodeCreate,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> SensorCodeResponse:
    """Save and parse a sensor Data Matrix scan."""
    return SensorCodeService(session, current_user.id).create(payload)


@router.patch(
    "/glucose/sensor-codes/{code_id}",
    response_model=SensorCodeResponse,
    operation_id="patchSensorCode",
)
def patch_sensor_code(
    code_id: UUID,
    payload: SensorCodePatch,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> SensorCodeResponse:
    """Attach, move, or detach a saved sensor code."""
    return SensorCodeService(session, current_user.id).patch(code_id, payload)


@router.get(
    "/sensors/{sensor_id}/quality",
    response_model=SensorQualityResponse,
    operation_id="getSensorQuality",
)
def get_sensor_quality(
    sensor_id: UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> SensorQualityResponse:
    """Return computed display-only quality metrics for one sensor."""
    return GlucoseDashboardService(session, current_user.id).sensor_quality(sensor_id)


@router.post(
    "/sensors/{sensor_id}/recalculate-calibration",
    response_model=CgmCalibrationModelResponse,
    operation_id="recalculateSensorCalibration",
)
def recalculate_sensor_calibration(
    sensor_id: UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> CgmCalibrationModelResponse:
    """Recompute and store a display-only calibration model."""
    return GlucoseDashboardService(session, current_user.id).recalculate_calibration(
        sensor_id
    )
