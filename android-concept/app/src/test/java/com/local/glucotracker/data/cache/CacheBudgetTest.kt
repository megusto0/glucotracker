package com.local.glucotracker.data.cache

import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import org.junit.Assert.assertEquals
import org.junit.Test

class CacheBudgetTest {
    @Test
    fun calculatesMealGlucoseAndProductCutoffs() {
        val now = Instant.parse("2026-05-05T12:00:00Z")

        assertEquals(
            LocalDate.parse("2026-04-21"),
            CacheBudget.oldestMealDayToKeep(now, TimeZone.UTC),
        )
        assertEquals(
            Instant.parse("2026-05-05T06:00:00Z"),
            CacheBudget.oldestGlucoseReadingToKeep(now),
        )
        assertEquals(
            Instant.parse("2026-02-04T12:00:00Z"),
            CacheBudget.oldestProductUseToKeep(now),
        )
    }
}
