package com.local.glucotracker.ui.glucose

import com.local.glucotracker.domain.model.InsulinDayContext
import com.local.glucotracker.domain.model.InsulinEvent
import com.local.glucotracker.domain.model.InsulinEventType
import kotlinx.datetime.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class HistoryContextFilterTest {
    @Test
    fun keepsOnlyInsulinAttachedToVisibleMealsAndDropsOrphans() {
        val visible = event("visible-dose")
        val hidden = event("hidden-dose")
        val orphan = event("orphan-dose")
        val context = InsulinDayContext(
            byMealId = mapOf(
                "visible-meal" to listOf(visible),
                "hidden-meal" to listOf(hidden),
            ),
            orphans = listOf(orphan),
            mealEpisodeGroups = listOf(listOf("visible-meal", "hidden-meal")),
        )

        val result = context.onlyMeals(setOf("visible-meal"))

        assertEquals(setOf("visible-meal"), result.byMealId.keys)
        assertEquals(listOf(visible.id), result.allEvents.map { it.id })
        assertTrue(result.orphans.isEmpty())
        assertTrue(result.mealEpisodeGroups.isEmpty())
    }

    private fun event(id: String) = InsulinEvent(
        id = id,
        timestamp = Instant.parse("2026-08-08T10:00:00Z"),
        doseUnits = 1.0,
        source = "test",
        sourceEventId = null,
        eventType = InsulinEventType.Bolus,
    )
}
