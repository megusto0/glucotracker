package com.local.glucotracker.ui.design.primitives

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class FoodDayCurveTest {
    @Test
    fun closeSittingsNeverMakeCurveRunBackwards() {
        val layout = foodCurveLayout(
            meals = listOf(
                FoodCurveMeal(10 * 60 + 55, 255.0, FoodCurveMeal.Kind.Meal, id = "a"),
                FoodCurveMeal(11 * 60, 238.0, FoodCurveMeal.Kind.Meal, id = "b"),
                FoodCurveMeal(11 * 60 + 12, 102.0, FoodCurveMeal.Kind.Snack, id = "c"),
            ),
            totalKcal = 595.0,
        )

        assertTrue(layout.points.zipWithNext().all { (left, right) ->
            left.minutesOfDay <= right.minutesOfDay && left.kcal <= right.kcal
        })
        assertEquals(595.0, layout.points.last().kcal, absoluteTolerance = 0.001)
    }

    @Test
    fun markersKeepTheirRecordIds() {
        val layout = foodCurveLayout(
            meals = listOf(
                FoodCurveMeal(13 * 60, 120.0, FoodCurveMeal.Kind.Snack, id = "meal-42"),
            ),
            totalKcal = 120.0,
        )

        assertEquals("meal-42", layout.markers.single().id)
    }
}
