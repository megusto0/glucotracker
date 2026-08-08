package com.local.glucotracker.ui.feature.more

import kotlin.test.Test
import kotlin.test.assertEquals

class RhythmGeometryTest {
    @Test
    fun sleepBecomesASeparateSegmentAndClipsEndOfDay() {
        val origin = 11 * 60 + 58
        val sleepStart = 4 * 60 + 20
        val windows = listOf(
            window("first", origin, 14 * 60 + 58),
            window("middle", 14 * 60 + 58, 19 * 60 + 58),
            window("second", 19 * 60 + 58, 58),
            window("end", 58, origin),
        )
        val sleep = SleepWindowUi(sleepStart, origin, nights = 7)

        val result = rhythmWindowsForDisplay(windows, sleep)
        val displayedMinutes = result.sumOf { window ->
            duration(window.startMinute, window.endMinute)
        } + duration(sleep.startMinute, sleep.endMinute)

        assertEquals(sleepStart, result.last().endMinute)
        assertEquals(24 * 60, displayedMinutes)
    }

    private fun window(label: String, start: Int, end: Int) =
        RhythmWindowUi(label, start, end)

    private fun duration(start: Int, end: Int): Int =
        if (end >= start) end - start else (24 * 60 - start) + end
}
