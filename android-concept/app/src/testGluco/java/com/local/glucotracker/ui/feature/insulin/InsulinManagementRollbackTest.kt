package com.local.glucotracker.ui.feature.insulin

import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.LocalTime
import kotlinx.datetime.TimeZone
import org.junit.Assert.assertEquals
import org.junit.Test

class InsulinManagementRollbackTest {

    private val zone = TimeZone.of("Europe/Samara")

    private fun instant(iso: String): Instant = Instant.parse(iso)

    @Test
    fun timeJustAfterMidnightRollsBackToPreviousEvening() {
        // Record was created 2026-08-04 00:15 local; user sets 23:55 expecting
        // the evening that just ended (2026-08-03 23:55 local).
        val resolved = resolveRecordedAt(
            date = LocalDate(2026, 8, 4),
            time = LocalTime(23, 55),
            zone = zone,
            now = instant("2026-08-03T20:15:00Z"),
        )
        assertEquals("2026-08-03T19:55:00Z", resolved.toString())
    }

    @Test
    fun pastOrNearNowTimeIsLeftUntouched() {
        val now = instant("2026-08-03T20:15:00Z")
        val nearNow = resolveRecordedAt(
            date = LocalDate(2026, 8, 4),
            time = LocalTime(0, 20),
            zone = zone,
            now = now,
        )
        assertEquals("2026-08-03T20:20:00Z", nearNow.toString())

        val sameDayPast = resolveRecordedAt(
            date = LocalDate(2026, 8, 3),
            time = LocalTime(19, 30),
            zone = zone,
            now = now,
        )
        assertEquals("2026-08-03T15:30:00Z", sameDayPast.toString())
    }

    @Test
    fun middayEditIsNotRolledBack() {
        // Now is midday; a same-day evening time is in the future by only ~11h.
        val resolved = resolveRecordedAt(
            date = LocalDate(2026, 8, 4),
            time = LocalTime(23, 55),
            zone = zone,
            now = instant("2026-08-04T10:00:00Z"),
        )
        assertEquals("2026-08-04T19:55:00Z", resolved.toString())
    }
}
