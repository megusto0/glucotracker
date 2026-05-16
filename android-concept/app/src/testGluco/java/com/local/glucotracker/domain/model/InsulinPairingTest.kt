package com.local.glucotracker.domain.model

import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Test

class InsulinPairingTest {
    private val date = LocalDate.parse("2026-05-14")

    @Test
    fun emptyInsulinListKeepsMealsUnpaired() {
        val content = pairInsulinWithMeals(
            date = date,
            meals = listOf(meal("meal", "2026-05-14T11:00:00Z")),
            insulinEvents = emptyList(),
        )

        assertEquals(1, content.mealsWithInsulin.size)
        assertEquals(emptyList<InsulinEvent>(), content.mealsWithInsulin.single().pairedInsulin)
        assertEquals(emptyList<InsulinEvent>(), content.orphanInsulin)
    }

    @Test
    fun pairsSingleInsulinInsideAsymmetricWindow() {
        val content = pairInsulinWithMeals(
            date = date,
            meals = listOf(meal("meal", "2026-05-14T11:00:00Z")),
            insulinEvents = listOf(insulin("i1", "2026-05-14T10:50:00Z")),
        )

        assertEquals(listOf("i1"), content.mealsWithInsulin.single().pairedInsulin.map { it.id })
        assertEquals(emptyList<InsulinEvent>(), content.orphanInsulin)
    }

    @Test
    fun pairsMultipleEventsToOneMealInTimestampOrder() {
        val content = pairInsulinWithMeals(
            date = date,
            meals = listOf(meal("meal", "2026-05-14T11:00:00Z")),
            insulinEvents = listOf(
                insulin("i2", "2026-05-14T11:10:00Z"),
                insulin("i1", "2026-05-14T10:55:00Z"),
            ),
        )

        assertEquals(listOf("i1", "i2"), content.mealsWithInsulin.single().pairedInsulin.map { it.id })
    }

    @Test
    fun closestMealWinsWhenEventFitsTwoMealWindows() {
        val content = pairInsulinWithMeals(
            date = date,
            meals = listOf(
                meal("early", "2026-05-14T11:00:00Z"),
                meal("late", "2026-05-14T11:35:00Z"),
            ),
            insulinEvents = listOf(insulin("i1", "2026-05-14T11:25:00Z")),
        )

        val byMeal = content.mealsWithInsulin.associate { it.meal.id to it.pairedInsulin.map(InsulinEvent::id) }
        assertEquals(emptyList<String>(), byMeal.getValue("early"))
        assertEquals(listOf("i1"), byMeal.getValue("late"))
    }

    @Test
    fun leavesEventsOutsideMealWindowsAsOrphans() {
        val content = pairInsulinWithMeals(
            date = date,
            meals = listOf(meal("meal", "2026-05-14T11:00:00Z")),
            insulinEvents = listOf(insulin("orphan", "2026-05-14T09:00:00Z")),
        )

        assertEquals(emptyList<InsulinEvent>(), content.mealsWithInsulin.single().pairedInsulin)
        assertEquals(listOf("orphan"), content.orphanInsulin.map { it.id })
    }

    @Test
    fun skipsBasalAndZeroDoseEvents() {
        val content = pairInsulinWithMeals(
            date = date,
            meals = listOf(meal("meal", "2026-05-14T11:00:00Z")),
            insulinEvents = listOf(
                insulin("basal", "2026-05-14T11:00:00Z", type = InsulinEventType.Basal),
                insulin("zero", "2026-05-14T11:00:00Z", dose = 0.0),
            ),
        )

        assertEquals(emptyList<InsulinEvent>(), content.mealsWithInsulin.single().pairedInsulin)
        assertEquals(emptyList<InsulinEvent>(), content.orphanInsulin)
    }
}

private data class TestMeal(
    val id: String,
    val eatenAt: Instant,
)

private fun meal(id: String, eatenAt: String): PairableMeal<TestMeal> {
    val instant = Instant.parse(eatenAt)
    return PairableMeal(
        value = TestMeal(id = id, eatenAt = instant),
        id = id,
        eatenAt = instant,
    )
}

private fun insulin(
    id: String,
    timestamp: String,
    dose: Double = 1.0,
    type: InsulinEventType = InsulinEventType.Bolus,
): InsulinEvent =
    InsulinEvent(
        id = id,
        timestamp = Instant.parse(timestamp),
        doseUnits = dose,
        source = "Nightscout",
        sourceEventId = id,
        eventType = type,
    )
