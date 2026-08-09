package com.local.glucotracker.ui.feature.insulin

import com.local.glucotracker.generated.model.InsulinRecommendationResponse
import java.math.BigDecimal
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The total is exactly food plus correction. IOB is context inside the
 * correction and must never become a third, hidden subtraction from food.
 */
class HistoricalInsulinUiStateTest {

    private fun response(
        recommendedUnits: BigDecimal? = BigDecimal("5.2"),
        totalRecommendedUnits: BigDecimal? = BigDecimal("6.3"),
        correctionStatus: InsulinRecommendationResponse.CorrectionStatus =
            InsulinRecommendationResponse.CorrectionStatus.READY,
        correctionUnits: BigDecimal? = BigDecimal("1.1"),
        correctionIobUnits: BigDecimal? = BigDecimal("3.2"),
        correctionPriorCobG: BigDecimal? = BigDecimal("23.0"),
        correctionExcessIobUnits: BigDecimal? = BigDecimal("0.7"),
        icrGPerUnit: BigDecimal? = BigDecimal("9.3"),
        icrConfiguredGPerUnit: BigDecimal? = BigDecimal("9.3"),
        icrAfterSleep: Boolean = false,
        icrDaypart: InsulinRecommendationResponse.IcrDaypart? =
            InsulinRecommendationResponse.IcrDaypart.DAY,
        historyMedianUnits: BigDecimal? = BigDecimal("5.6"),
        historyWeight: BigDecimal? = BigDecimal("0.7"),
    ) = InsulinRecommendationResponse(
        confidence = InsulinRecommendationResponse.Confidence.MEDIUM,
        correctionStatus = correctionStatus,
        matchedEpisodeCount = 6,
        matches = emptyList(),
        mealIds = emptyList(),
        methodVersion = "historical-episode-median-v2",
        status = InsulinRecommendationResponse.Status.READY,
        targetCarbsG = BigDecimal("48"),
        targetKcal = BigDecimal("520"),
        correctionUnits = correctionUnits,
        correctionIobUnits = correctionIobUnits,
        correctionPriorCobG = correctionPriorCobG,
        correctionExcessIobUnits = correctionExcessIobUnits,
        correctionGlucoseMmolL = BigDecimal("9.4"),
        correctionProjectedGlucoseMmolL = BigDecimal("8.1"),
        correctionTargetMmolL = BigDecimal("6.0"),
        correctionIsfMmolLPerUnit = BigDecimal("2.8"),
        correctionIsfSource = InsulinRecommendationResponse.CorrectionIsfSource.FITTED,
        historyMedianUnits = historyMedianUnits,
        historyWeight = historyWeight,
        icrAfterSleep = icrAfterSleep,
        icrConfiguredGPerUnit = icrConfiguredGPerUnit,
        icrDaypart = icrDaypart,
        icrDoseUnits = BigDecimal("5.2"),
        icrGPerUnit = icrGPerUnit,
        impliedIcrGPerUnit = BigDecimal("8.9"),
        rangeLowUnits = BigDecimal("4.6"),
        rangeHighUnits = BigDecimal("6.1"),
        recommendedUnits = recommendedUnits,
        totalRecommendedUnits = totalRecommendedUnits,
    )

    private fun ready(response: InsulinRecommendationResponse) =
        response.toUiState() as HistoricalInsulinUiState.Ready

    @Test
    fun `the headline is the total, not the meal component`() {
        val state = ready(response())

        assertEquals(6.3, state.headlineUnits, 1e-9)
        assertEquals(5.2, state.mealUnits, 1e-9)
        assertTrue(state.includesCorrection)
    }

    @Test
    fun `the correction carries committed and free insulin context`() {
        val state = ready(response())

        assertEquals(1.1, state.correction!!.units, 1e-9)
        assertEquals(3.2, state.correction!!.iobUnits!!, 1e-9)
        assertEquals(23.0, state.correction!!.priorCobG!!, 1e-9)
        assertEquals(0.7, state.correction!!.excessIobUnits!!, 1e-9)
        assertNull(state.correctionGap)
    }

    @Test
    fun `prospective calculation uses the shared bolus state block`() {
        val state = ready(response()).toBolusState()

        assertEquals(9.4, state.glucose!!, 1e-9)
        assertEquals(3.2, state.iob!!, 1e-9)
        assertEquals(23.0, state.cob!!, 1e-9)
        assertEquals(9.3, state.icr!!, 1e-9)
        assertEquals(2.8, state.isf!!, 1e-9)
        assertEquals(6.0, state.target!!, 1e-9)
    }

    @Test
    fun `prospective terms do not subtract iob a second time`() {
        val terms = ready(response()).toBolusTerms()

        assertEquals(listOf("meal", "correction"), terms.map { it.label })
        assertEquals(listOf(5.2, 1.1), terms.map { it.value })
    }

    @Test
    fun `a correction that is simply not needed still counts as included`() {
        val state = ready(
            response(
                correctionStatus = InsulinRecommendationResponse.CorrectionStatus.NOT_NEEDED,
                correctionUnits = BigDecimal.ZERO,
                totalRecommendedUnits = BigDecimal("5.2"),
            ),
        )

        assertTrue(state.includesCorrection)
        assertEquals(5.2, state.headlineUnits, 1e-9)
    }

    @Test
    fun `without a usable correction the meal figure stands but says so`() {
        val state = ready(
            response(
                correctionStatus =
                    InsulinRecommendationResponse.CorrectionStatus.GLUCOSE_UNAVAILABLE,
                correctionUnits = null,
                totalRecommendedUnits = null,
            ),
        )

        assertFalse(state.includesCorrection)
        assertEquals(5.2, state.headlineUnits, 1e-9)
        assertEquals(CorrectionGap.GlucoseUnavailable, state.correctionGap)
    }

    @Test
    fun `the ratio behind the food half reaches the sheet`() {
        val basis = ready(response()).basis

        assertEquals(9.3, basis.icrGPerUnit!!, 1e-9)
        assertEquals(IcrDaypart.Day, basis.icrDaypart)
        assertEquals(5.6, basis.historyMedianUnits!!, 1e-9)
        assertEquals(0.7, basis.historyWeight!!, 1e-9)
        assertEquals(8.9, basis.impliedIcrGPerUnit!!, 1e-9)
        assertEquals(48.0, basis.carbsG, 1e-9)
        assertFalse(basis.icrAfterSleep)
    }

    @Test
    fun `a tightened first-meal ratio keeps the configured one alongside it`() {
        val basis = ready(
            response(
                icrAfterSleep = true,
                icrGPerUnit = BigDecimal("7.59"),
                icrConfiguredGPerUnit = BigDecimal("9.3"),
            ),
        ).basis

        assertTrue(basis.icrAfterSleep)
        assertEquals(7.59, basis.icrGPerUnit!!, 1e-9)
        assertEquals(9.3, basis.icrConfiguredGPerUnit!!, 1e-9)
    }

    @Test
    fun `a withheld dose is not turned into a number`() {
        val state = response(recommendedUnits = null).toUiState()

        assertEquals(HistoricalInsulinUiState.Error, state)
    }
}
