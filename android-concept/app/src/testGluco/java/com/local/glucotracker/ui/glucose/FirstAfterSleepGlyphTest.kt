package com.local.glucotracker.ui.glucose

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class FirstAfterSleepGlyphTest {
    @Test
    fun marker_uses_backend_sleep_context_before_insulin_is_added() {
        val meal = "meal-1"

        assertTrue(shouldShowFirstAfterSleepGlyph(listOf(meal), setOf(meal)))
        assertFalse(shouldShowFirstAfterSleepGlyph(listOf(meal), emptySet()))
    }

    @Test
    fun any_dish_can_carry_the_context_for_a_grouped_sitting() {
        assertTrue(
            shouldShowFirstAfterSleepGlyph(
                mealIds = listOf("plate", "drink", "yoghurt"),
                firstAfterSleepMealIds = setOf("drink"),
            ),
        )
    }
}
