package com.local.glucotracker.data.mapper

import com.local.glucotracker.domain.model.GlucoseRange
import com.local.glucotracker.domain.model.GlucoseReading
import kotlinx.datetime.Instant
import org.junit.Assert.assertEquals
import org.junit.Test

class GlucoseDisplayModeTest {
    @Test
    fun normalizedModeChangesOnlyDisplayValueAndFallsBackToRaw() {
        val at = Instant.parse("2026-07-13T08:00:00Z")
        val range = GlucoseRange(
            from = at,
            to = at,
            readings = listOf(
                reading(at, raw = 6.8, normalized = 6.1),
                reading(at, raw = 7.2, normalized = null),
            ),
        )

        val normalized = range.withNormalizedDisplay(enabled = true)
        val standard = normalized.withNormalizedDisplay(enabled = false)

        assertEquals(listOf(6.1, 7.2), normalized.readings.map { it.displayValueMmolL })
        assertEquals(listOf(6.8, 7.2), standard.readings.map { it.displayValueMmolL })
        assertEquals(listOf(6.8, 7.2), normalized.readings.map { it.rawValueMmolL })
    }
}

private fun reading(
    at: Instant,
    raw: Double,
    normalized: Double?,
): GlucoseReading =
    GlucoseReading(
        readingAt = at,
        rawValueMmolL = raw,
        displayValueMmolL = raw,
        normalizedValueMmolL = normalized,
        smoothedValueMmolL = null,
        flags = emptyList(),
    )
