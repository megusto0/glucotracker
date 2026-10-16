package com.local.glucotracker.ui.glucose

import com.local.glucotracker.domain.model.InsulinEvent
import com.local.glucotracker.domain.model.InsulinEventType
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.time.Duration.Companion.minutes
import kotlinx.datetime.Instant

class BolusSelectionTest {
    private val meal = Instant.parse("2026-10-04T06:27:00Z")

    private fun dose(
        id: String,
        offsetMinutes: Int,
        kind: InsulinEventType = InsulinEventType.Bolus,
    ) = InsulinEvent(
        id = id,
        timestamp = meal + offsetMinutes.minutes,
        doseUnits = 1.0,
        source = "glucotracker",
        sourceEventId = id,
        eventType = kind,
    )

    /** 2026-10-04: 1,0 / 5,7 / 2,0 for breakfast, then 1,5 fifty minutes later. */
    private val sitting = listOf(
        dose("a", -27),
        dose("b", -20),
        dose("c", 0),
        dose("d", 50, InsulinEventType.CatchUp),
    )

    @Test
    fun theMealDosesAreOneSeriesAndTheCatchUpIsItsOwn() {
        assertEquals(setOf(0, 1, 2), mealDoseIndices(sitting, meal))
    }

    @Test
    fun aBolusMoreThanAnHourAfterTheMealIsNotPartOfIt() {
        val late = sitting + dose("e", 75)
        assertEquals(setOf(0, 1, 2), mealDoseIndices(late, meal))
    }

    @Test
    fun theSheetOpensOnTheMealWhenThereIsOne() {
        assertEquals(BolusSelection.Meal, defaultBolusSelection(sitting, meal, hasMeal = true))
        assertEquals(BolusSelection.Dose(3), defaultBolusSelection(sitting, meal, hasMeal = false))
        assertEquals(BolusSelection.Dose(3), defaultBolusSelection(sitting, null, hasMeal = true))
    }
}
