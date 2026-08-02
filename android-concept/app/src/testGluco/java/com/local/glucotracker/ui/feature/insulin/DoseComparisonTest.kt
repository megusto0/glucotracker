package com.local.glucotracker.ui.feature.insulin

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class DoseComparisonTest {

    @Test
    fun `nothing to compare before any insulin exists`() {
        assertNull(doseComparison(givenUnits = 0.0, recommendedUnits = 4.1))
    }

    @Test
    fun `reports how much more the calculation asks for`() {
        val verdict = doseComparison(givenUnits = 12.9, recommendedUnits = 13.4)

        assertTrue(verdict is DoseComparison.CalculationHigher)
        assertEquals(0.5, (verdict as DoseComparison.CalculationHigher).byUnits, 1e-9)
    }

    @Test
    fun `reports how much less the calculation asks for`() {
        val verdict = doseComparison(givenUnits = 10.0, recommendedUnits = 8.2)

        assertTrue(verdict is DoseComparison.CalculationLower)
        assertEquals(1.8, (verdict as DoseComparison.CalculationLower).byUnits, 1e-9)
    }

    @Test
    fun `a difference below dose rounding is not a disagreement`() {
        // Doses are entered to a tenth, so 0.04 cannot be acted on either way.
        assertEquals(
            DoseComparison.Match,
            doseComparison(givenUnits = 4.0, recommendedUnits = 4.04),
        )
        assertEquals(
            DoseComparison.Match,
            doseComparison(givenUnits = 4.0, recommendedUnits = 3.96),
        )
    }

    @Test
    fun `a full rounding step is a real difference`() {
        assertTrue(
            doseComparison(givenUnits = 4.0, recommendedUnits = 4.1)
                is DoseComparison.CalculationHigher,
        )
    }
}
