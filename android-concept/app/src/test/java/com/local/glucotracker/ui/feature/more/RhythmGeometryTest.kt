package com.local.glucotracker.ui.feature.more

import kotlin.test.Test
import kotlin.test.assertEquals

class RhythmGeometryTest {
    @Test
    fun sleepGlyphUsesCenterOfSleepBandNotCenterOfDayWindow() {
        val origin = 11 * 60 + 58
        val sleepStart = 4 * 60 + 20
        val sleepEnd = origin

        val result = sleepMidpointFraction(origin, sleepStart, sleepEnd)

        assertEquals(0.841f, result, 0.001f)
    }
}
