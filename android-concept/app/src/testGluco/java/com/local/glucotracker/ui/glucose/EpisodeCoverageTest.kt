package com.local.glucotracker.ui.glucose

import kotlin.time.Duration.Companion.minutes
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class EpisodeCoverageTest {

    @Test
    fun `splits a real episode into on-time and follow-up units`() {
        // 2026-08-02: 125.6 g covered by 10.1 U at the plate, then 1.8 U after
        // 29 minutes and 1.0 U after an hour.
        val coverage = episodeCoverage(
            doses = listOf(
                EpisodeDose(units = 10.1, lateBy = 3.minutes),
                EpisodeDose(units = 1.8, lateBy = 29.minutes),
                EpisodeDose(units = 1.0, lateBy = 60.minutes),
            ),
            totalCarbs = 125.6,
            totalInsulin = 12.9,
        )

        assertEquals(9.7, coverage!!.gramsPerUnit, 0.05)
        assertEquals(10.1, coverage.onTimeUnits, 1e-9)
        assertEquals(2.8, coverage.lateUnits, 1e-9)
    }

    @Test
    fun `a bolus at the window edge still counts as on time`() {
        val coverage = episodeCoverage(
            doses = listOf(EpisodeDose(units = 4.0, lateBy = OnTimeBolusWindow)),
            totalCarbs = 40.0,
            totalInsulin = 4.0,
        )

        assertEquals(4.0, coverage!!.onTimeUnits, 1e-9)
        assertEquals(0.0, coverage.lateUnits, 1e-9)
    }

    @Test
    fun `a bolus before the meal counts as on time`() {
        val coverage = episodeCoverage(
            doses = listOf(EpisodeDose(units = 5.0, lateBy = (-15).minutes)),
            totalCarbs = 50.0,
            totalInsulin = 5.0,
        )

        assertEquals(5.0, coverage!!.onTimeUnits, 1e-9)
        assertEquals(0.0, coverage.lateUnits, 1e-9)
    }

    @Test
    fun `an entirely late dose reports no on-time units`() {
        val coverage = episodeCoverage(
            doses = listOf(EpisodeDose(units = 2.2, lateBy = 61.minutes)),
            totalCarbs = 35.0,
            totalInsulin = 2.2,
        )

        assertEquals(15.9, coverage!!.gramsPerUnit, 0.05)
        assertEquals(0.0, coverage.onTimeUnits, 1e-9)
        assertEquals(2.2, coverage.lateUnits, 1e-9)
    }

    @Test
    fun `no ratio without insulin or without carbohydrate`() {
        assertNull(episodeCoverage(emptyList(), totalCarbs = 40.0, totalInsulin = 0.0))
        assertNull(
            episodeCoverage(
                doses = listOf(EpisodeDose(units = 1.0, lateBy = 0.minutes)),
                totalCarbs = 0.0,
                totalInsulin = 1.0,
            ),
        )
    }
}
