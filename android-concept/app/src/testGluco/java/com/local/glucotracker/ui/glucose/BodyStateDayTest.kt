package com.local.glucotracker.ui.glucose

import kotlinx.datetime.Instant
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class BodyStateDayTest {
    // 2026-10-02 in Samara (+04:00).
    private val dayStart = Instant.parse("2026-10-01T20:00:00Z")
    private val dayEnd = Instant.parse("2026-10-02T20:00:00Z")
    private fun local(hhmm: String, day: Int = 2) =
        Instant.parse("2026-10-0${day}T${hhmm}:00+04:00")

    private fun state(
        start: Instant,
        end: Instant,
        visible: Int,
        total: Int,
        kind: BodyState.Kind = BodyState.Kind.Sleep,
    ): BodyState {
        val (wholeStart, wholeEnd, continues) = wholeSpan(start, end, visible, total, dayStart, dayEnd)
        return BodyState(
            kind = kind,
            startAt = start,
            endAt = end,
            totalMinutes = total,
            inferred = false,
            label = null,
            meanBpm = null,
            wholeStartAt = wholeStart,
            wholeEndAt = wholeEnd,
            continuesAfterDay = continues,
        )
    }

    /** The night that ended that morning, clipped at 00:00. */
    private val morning = state(local("00:00"), local("04:48"), visible = 288, total = 450)

    /** The next night, begun at 23:25 and clipped at 24:00. */
    private val evening = state(local("23:25"), dayEnd, visible = 35, total = 686)

    @Test
    fun `a night into tomorrow keeps its real end and belongs to tomorrow`() {
        assertEquals(local("10:51", day = 3), evening.wholeEndAt)
        assertEquals(local("23:25"), evening.wholeStartAt)
        assertTrue(evening.continuesAfterDay)
    }

    @Test
    fun `a night from yesterday keeps its real start and belongs to today`() {
        assertEquals(local("21:18", day = 1), morning.wholeStartAt)
        assertEquals(local("04:48"), morning.wholeEndAt)
        assertFalse(morning.continuesAfterDay)
    }

    @Test
    fun `the day counts the night that ended in it, not the next one`() {
        // Was 18:56 = 7:30 + 11:26.
        val activity = state(local("17:00"), local("17:23"), 23, 23, BodyState.Kind.Activity)
        assertEquals(450 to 23, dayBodyStateTotals(listOf(morning, evening, activity)))
    }

    @Test
    fun `a nap inside the day is untouched`() {
        val nap = state(local("14:00"), local("15:30"), visible = 90, total = 90)
        assertEquals(nap.startAt, nap.wholeStartAt)
        assertEquals(nap.endAt, nap.wholeEndAt)
        assertEquals(90 to 0, dayBodyStateTotals(listOf(nap)))
    }
}
