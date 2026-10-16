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
            methodVersion = "historical-episode-median-v3",
            correctionStatus = InsulinRecommendationResponse.CorrectionStatus.GLUCOSE_UNAVAILABLE,
            correctionTargetMmolL = BigDecimal("6.0"),
            icrGPerUnit = BigDecimal("9.3"),
            icrConfiguredGPerUnit = BigDecimal("11.4"),
            icrAfterSleep = true,
        )

        val result = response.toMealBolusCalcUi()

        assertEquals(9.8, result.suggestedUnits)
        assertEquals(9.8, result.terms.single().value)
        assertEquals("91 г / 9,3", result.terms.single().formula)
        assertEquals(BolusCorrectionGap.Glucose, result.omittedCorrectionReason)
        assertEquals(9.3, result.state.icr)
        assertEquals(11.4, result.configuredIcr)
        assertEquals(true, result.icrAfterSleep)
        assertFalse(result.projectionStale)
    }

    @Test
    fun aFollowUpFromTheHistoryModelDoesNotListBalanceTerms() {
        val response = TopUpDoseResponse(
            status = TopUpDoseResponse.Status.READY,
            glucoseMmolL = BigDecimal("9.8"),
            targetMmolL = BigDecimal("6.0"),
            units = BigDecimal("1.1"),
            carbUnits = BigDecimal("6.0"),
            correctionUnits = BigDecimal("1.46"),
            iobUnits = BigDecimal("3.2"),
            cobG = BigDecimal("56"),
            icrGPerUnit = BigDecimal("9.3"),
            isfMmolLPerUnit = BigDecimal("2.6"),
            balanceUnits = BigDecimal("4.26"),
            modelUnits = BigDecimal("1.1"),
            limitedBy = TopUpDoseResponse.LimitedBy.MODEL,
            projectionSource = TopUpDoseResponse.ProjectionSource.LINEAR_TREND,
        )

        val calc = response.toBolusCalcUi()
        assertEquals(emptyList(), calc.terms)
        assertEquals(4.26, calc.modelBalanceUnits)
        assertEquals(1.1, calc.suggestedUnits)

        val panel = response.toTopUpUi()
        assertEquals(TopUpStatusUi.Ready, panel.status)
        assertNull(panel.carbUnits)
        assertEquals(4.26, panel.modelBalanceUnits)
    }

    @Test
    fun aFollowUpFromTheBalanceKeepsItsTerms() {
        val response = TopUpDoseResponse(
            status = TopUpDoseResponse.Status.READY,
            units = BigDecimal("1.5"),
            carbUnits = BigDecimal("5.6"),
            correctionUnits = BigDecimal("1.6"),
            iobUnits = BigDecimal("5.7"),
            glucoseMmolL = BigDecimal("10.3"),
            targetMmolL = BigDecimal("6.0"),
            isfMmolLPerUnit = BigDecimal("2.6"),
            cobG = BigDecimal("52"),
            icrGPerUnit = BigDecimal("9.3"),
            limitedBy = TopUpDoseResponse.LimitedBy.BALANCE,
        )

        assertEquals(3, response.toBolusCalcUi().terms.size)
        assertNull(response.toBolusCalcUi().modelBalanceUnits)
        assertEquals(5.6, response.toTopUpUi().carbUnits)
    }

    @Test
    fun mealCalculationReadsCarbohydrateFromEarlierMealsOnly() {
        val response = InsulinRecommendationResponse(
            status = InsulinRecommendationResponse.Status.READY,
            mealIds = emptyList(),
            targetCarbsG = BigDecimal("82"),
            targetKcal = BigDecimal("600"),
            recommendedUnits = BigDecimal("12.6"),
            rangeLowUnits = BigDecimal("11"),
            rangeHighUnits = BigDecimal("14"),
            confidence = InsulinRecommendationResponse.Confidence.LOW,
            matchedEpisodeCount = 0,
            matches = emptyList(),
            methodVersion = "historical-episode-median-v3",
            correctionStatus = InsulinRecommendationResponse.CorrectionStatus.READY,
            correctionPriorCobG = BigDecimal("0"),
        )

        assertEquals(true, response.toMealBolusCalcUi().state.cobIsPrior)
    }
}
