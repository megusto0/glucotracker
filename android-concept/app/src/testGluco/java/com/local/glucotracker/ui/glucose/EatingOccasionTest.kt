package com.local.glucotracker.ui.glucose

import kotlin.time.Duration.Companion.minutes
import kotlinx.datetime.Instant
import org.junit.Assert.assertEquals
import org.junit.Test

class EatingOccasionTest {

    private val base = Instant.parse("2026-08-02T16:19:00Z")

    @Test
    fun `a snack an hour later is not part of the same sitting`() {
        // Reported 2026-08-02: a bolus at 17:19 sat inside the linking window of
        // both the 16:19 lunch and the 17:21 snack, so the episode engine joined
        // them and a dose was offered for 125.6 g at once.
        val eatenAt = mapOf(
            "drink" to base,
            "quesadilla" to base,
            "cookies" to base,
            "syrok" to base + 62.minutes,
        )
        val episode = listOf("drink", "quesadilla", "cookies", "syrok")

        assertEquals(
            listOf("drink", "quesadilla", "cookies"),
            eatingOccasion(episode, eatenAt, anchorId = "drink"),
        )
        // Tapping the snack asks about the snack, not about lunch as well.
        assertEquals(
            listOf("syrok"),
            eatingOccasion(episode, eatenAt, anchorId = "syrok"),
        )
    }

    @Test
    fun `plates minutes apart stay one sitting`() {
        val eatenAt = mapOf(
            "potato" to base,
            "nuts" to base + 8.minutes,
        )
        val episode = listOf("potato", "nuts")

        assertEquals(episode, eatingOccasion(episode, eatenAt, anchorId = "potato"))
        assertEquals(episode, eatingOccasion(episode, eatenAt, anchorId = "nuts"))
    }

    @Test
    fun `a chain of small gaps stays together`() {
        val eatenAt = mapOf(
            "a" to base,
            "b" to base + 25.minutes,
            "c" to base + 50.minutes,
        )
        val episode = listOf("a", "b", "c")

        // Each step is inside the window even though a to c is nearly an hour.
        assertEquals(episode, eatingOccasion(episode, eatenAt, anchorId = "a"))
    }

    @Test
    fun `the gap boundary counts as the same sitting`() {
        val eatenAt = mapOf("a" to base, "b" to base + EatingOccasionGap)

        assertEquals(
            listOf("a", "b"),
            eatingOccasion(listOf("a", "b"), eatenAt, anchorId = "a"),
        )
    }

    @Test
    fun `meals without a known time are kept rather than silently dropped`() {
        val eatenAt = mapOf("a" to base)

        assertEquals(
            listOf("a", "unknown"),
            eatingOccasion(listOf("a", "unknown"), eatenAt, anchorId = "a"),
        )
    }

    @Test
    fun `an anchor outside the episode falls back to itself`() {
        assertEquals(
            listOf("x"),
            eatingOccasion(listOf("a", "b"), mapOf("a" to base), anchorId = "x"),
        )
    }
}
