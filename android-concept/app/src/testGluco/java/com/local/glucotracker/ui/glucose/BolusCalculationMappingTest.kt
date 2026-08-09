package com.local.glucotracker.ui.glucose

import com.local.glucotracker.generated.model.TopUpDoseResponse
import com.local.glucotracker.generated.model.InsulinRecommendationResponse
import java.math.BigDecimal
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull

class BolusCalculationMappingTest {
    @Test
    fun missingGlucoseIsAnExplicitUnavailableState() {
        val response = TopUpDoseResponse(
            status = TopUpDoseResponse.Status.GLUCOSE_UNAVAILABLE,
            targetMmolL = BigDecimal("6.0"),
        )

        val result = response.toBolusCalcUi()

        assertEquals(BolusUnavailableReason.Glucose, result.unavailableReason)
        assertNull(result.suggestedUnits)
        assertNull(result.state.glucose)
        assertEquals(6.0, result.state.target)
        assertFalse(result.projectionStale)
    }

    @Test
    fun absentForecastOnlyQualifiesARealCalculation() {
        val response = TopUpDoseResponse(
            status = TopUpDoseResponse.Status.READY,
            glucoseMmolL = BigDecimal("8.2"),
            targetMmolL = BigDecimal("6.0"),
            units = BigDecimal("1.0"),
            projectionSource = TopUpDoseResponse.ProjectionSource.NONE,
        )

        val result = response.toBolusCalcUi()

        assertEquals(1.0, result.suggestedUnits)
        assertEquals(true, result.projectionStale)
        assertNull(result.unavailableReason)
    }

    @Test
    fun mealDoseSurvivesMissingGlucoseCorrection() {
        val response = InsulinRecommendationResponse(
            status = InsulinRecommendationResponse.Status.READY,
            mealIds = emptyList(),
            targetCarbsG = BigDecimal("91"),
            targetKcal = BigDecimal("600"),
            recommendedUnits = BigDecimal("9.8"),
            rangeLowUnits = BigDecimal("8.3"),
            rangeHighUnits = BigDecimal("11.3"),
            confidence = InsulinRecommendationResponse.Confidence.LOW,
            matchedEpisodeCount = 0,
            matches = emptyList(),
            methodVersion = "test",
            correctionStatus = InsulinRecommendationResponse.CorrectionStatus.GLUCOSE_UNAVAILABLE,
            correctionTargetMmolL = BigDecimal("6.0"),
            icrGPerUnit = BigDecimal("9.3"),
            icrConfiguredGPerUnit = BigDecimal("11.4"),
            icrAfterSleep = true,
        )

        val result = response.toMealBolusCalcUi()

        assertEquals(9.8, result.suggestedUnits)
        assertEquals(9.8, result.terms.single().value)
        assertEquals(BolusCorrectionGap.Glucose, result.omittedCorrectionReason)
        assertEquals(9.3, result.state.icr)
        assertEquals(11.4, result.configuredIcr)
        assertEquals(true, result.icrAfterSleep)
        assertFalse(result.projectionStale)
    }
}
