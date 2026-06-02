package com.local.glucotracker.domain.model

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlinx.datetime.Instant

class MealMatchingTest {
    @Test
    fun createMealMatchesAcceptedMealByPatternReference() {
        val patternId = "9a9470db-0bdb-4b3b-8290-d0e1749c9ad1"
        val createMeal = createMeal(patternId = patternId)
        val meal = acceptedMeal(
            item = MealItem(
                id = "item-1",
                mealId = "meal-1",
                name = "Наггетсы 9 шт",
                sourceKind = "restaurant_db",
                patternId = patternId,
            ),
        )

        assertTrue(meal.matchesCreateMeal(createMeal))
        assertTrue(meal.hasRestaurantSource())
        assertTrue(createMeal.hasRestaurantSource())
    }

    @Test
    fun createMealWithIdempotencyKeyMatchesOnlySameServerKey() {
        val createMeal = createMeal(
            patternId = "9a9470db-0bdb-4b3b-8290-d0e1749c9ad1",
            idempotencyKey = "manual-key-1",
        )
        val matching = acceptedMeal(
            photoIdempotencyKey = "manual-key-1",
            item = MealItem(
                id = "item-1",
                mealId = "meal-1",
                name = "РќР°РіРіРµС‚СЃС‹ 9 С€С‚",
                sourceKind = "restaurant_db",
                patternId = "different-pattern",
            ),
        )
        val sameContentDifferentKey = acceptedMeal(
            photoIdempotencyKey = "manual-key-2",
            item = MealItem(
                id = "item-1",
                mealId = "meal-1",
                name = "РќР°РіРіРµС‚СЃС‹ 9 С€С‚",
                sourceKind = "restaurant_db",
                patternId = "9a9470db-0bdb-4b3b-8290-d0e1749c9ad1",
            ),
        )

        assertTrue(matching.matchesCreateMeal(createMeal))
        assertFalse(sameContentDifferentKey.matchesCreateMeal(createMeal))
    }

    @Test
    fun createMealDoesNotMatchBeforeItWasAttemptedElsewhere() {
        val createMeal = createMeal(patternId = "9a9470db-0bdb-4b3b-8290-d0e1749c9ad1")
        val meal = acceptedMeal(
            item = MealItem(
                id = "item-1",
                mealId = "meal-1",
                name = "Наггетсы 9 шт",
                sourceKind = "restaurant_db",
                patternId = "2b72389b-b3c8-4441-990d-09539f9fc36b",
            ),
        )

        assertFalse(meal.matchesCreateMeal(createMeal))
    }

    private fun createMeal(
        patternId: String,
        idempotencyKey: String? = null,
    ): OutboxKind.CreateMeal =
        OutboxKind.CreateMeal(
            payload = MealDraft(
                id = "draft-1",
                eatenAt = Instant.parse("2026-05-13T18:52:10Z"),
                title = "Наггетсы 9 шт",
                note = null,
                localPhotoPath = null,
                totalKcal = 366.0,
                totalCarbsG = 23.4,
                totalProteinG = 42.0,
                totalFatG = 12.0,
                totalFiberG = 0.0,
                weightGrams = 100.0,
            ),
            eatenAt = Instant.parse("2026-05-13T18:52:10Z"),
            source = "pattern",
            items = listOf(
                MealItemPayload(
                    name = "Наггетсы 9 шт",
                    grams = 100.0,
                    kcal = 366.0,
                    carbsG = 23.4,
                    proteinG = 42.0,
                    fatG = 12.0,
                    sourceKind = "restaurant_db",
                    patternId = patternId,
                ),
            ),
            idempotencyKey = idempotencyKey,
        )

    private fun acceptedMeal(
        item: MealItem,
        photoIdempotencyKey: String? = null,
    ): Meal =
        Meal(
            id = "meal-1",
            eatenAt = Instant.parse("2026-05-13T18:52:30Z"),
            eatenAtDay = kotlinx.datetime.LocalDate(2026, 5, 13),
            title = "Наггетсы 9 шт",
            status = "accepted",
            source = "pattern",
            note = null,
            thumbnailUrl = null,
            totalKcal = 366.0,
            totalCarbsG = 23.4,
            totalProteinG = 42.0,
            totalFatG = 12.0,
            totalFiberG = 0.0,
            updatedAt = Instant.parse("2026-05-13T18:53:00Z"),
            items = listOf(item),
            photoIdempotencyKey = photoIdempotencyKey,
        )
}
