package com.local.glucotracker.data.repository

import com.local.glucotracker.domain.model.DayTotals
import com.local.glucotracker.domain.model.HistoryQuery
import com.local.glucotracker.domain.model.Meal
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Test

class HistoryPageBuilderTest {
    @Test
    fun skipsTotalsOnlyDaysWhenMealCountIsZero() {
        val emptyDay = LocalDate(2026, 5, 5)
        val mealDay = LocalDate(2026, 5, 6)

        val page = buildHistoryPage(
            query = HistoryQuery(fromDay = emptyDay, toDay = mealDay),
            meals = listOf(meal(day = mealDay)),
            totals = listOf(
                totals(day = emptyDay, mealCount = 0),
                totals(day = mealDay, mealCount = 1),
            ),
        )

        assertEquals(listOf(mealDay), page.days.map { it.date })
        assertEquals(1, page.totalDays)
        assertEquals(1, page.totalRecords)
    }

    private fun totals(day: LocalDate, mealCount: Int) = DayTotals(
        date = day,
        kcal = if (mealCount > 0) 220.0 else 0.0,
        carbsG = 10.0 * mealCount,
        proteinG = 12.0 * mealCount,
        fatG = 8.0 * mealCount,
        fiberG = 1.0 * mealCount,
        mealCount = mealCount,
    )

    private fun meal(day: LocalDate) = Meal(
        id = "meal-$day",
        eatenAt = Instant.parse("${day}T08:00:00Z"),
        eatenAtDay = day,
        title = "Breakfast",
        status = "accepted",
        source = "manual",
        note = null,
        thumbnailUrl = null,
        totalKcal = 220.0,
        totalCarbsG = 10.0,
        totalProteinG = 12.0,
        totalFatG = 8.0,
        totalFiberG = 1.0,
        updatedAt = Instant.parse("${day}T08:05:00Z"),
    )
}
