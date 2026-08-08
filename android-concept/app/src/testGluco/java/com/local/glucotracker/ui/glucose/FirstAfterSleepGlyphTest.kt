package com.local.glucotracker.ui.glucose

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class FirstAfterSleepGlyphTest {
    @Test
    fun marker_requires_both_backend_context_and_insulin() {
        val meal = "meal-1"

        assertTrue(shouldShowFirstAfterSleepGlyph(listOf(meal), setOf(meal), 6.0))
        assertFalse(shouldShowFirstAfterSleepGlyph(listOf(meal), setOf(meal), 0.0))
        assertFalse(shouldShowFirstAfterSleepGlyph(listOf(meal), emptySet(), 6.0))
    }

    @Test
    fun any_dish_can_carry_the_context_for_a_grouped_sitting() {
        assertTrue(
            shouldShowFirstAfterSleepGlyph(
                mealIds = listOf("plate", "drink", "yoghurt"),
                firstAfterSleepMealIds = setOf("drink"),
                totalInsulinUnits = 6.0,
            ),
        )
    }
}
