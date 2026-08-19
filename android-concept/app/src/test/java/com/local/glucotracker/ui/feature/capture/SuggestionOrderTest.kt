package com.local.glucotracker.ui.feature.capture

import com.local.glucotracker.domain.model.Product
import kotlin.test.Test
import kotlin.test.assertEquals

class SuggestionOrderTest {
    @Test
    fun cookedBatchesComeFirstThenTheFridgeThenTheCatalogue() {
        val ordered = listOf(
            suggestion("Творог", sourceKind = null, usageCount = 99),
            suggestion("Йогурт Epica", sourceKind = "fridge"),
            suggestion("Сметанник", sourceKind = "meal_prep"),
        ).rankedFor("")

        assertEquals(
            listOf("Сметанник", "Йогурт Epica", "Творог"),
            ordered.map { it.name },
        )
    }

    @Test
    fun aPopularCatalogueRowStillLosesToStock() {
        // The old comparator led with usageCount, so the thing eaten most often
        // sat above the batch cooling in the fridge — which is the one answer
        // that stops being available if it is not used.
        val ordered = listOf(
            suggestion("Овсянка", sourceKind = null, usageCount = 500),
            suggestion("Азу с чечевицей", sourceKind = "meal_prep", usageCount = 0),
        ).rankedFor("")

        assertEquals("Азу с чечевицей", ordered.first().name)
    }

    @Test
    fun withinOneBlockTheQueryStillLeads() {
        val ordered = listOf(
            suggestion("Гречка с индейкой", sourceKind = "meal_prep", usageCount = 40),
            suggestion("Сметанник", sourceKind = "meal_prep", usageCount = 1),
        ).rankedFor("смет")

        assertEquals(
            listOf("Сметанник", "Гречка с индейкой"),
            ordered.map { it.name },
        )
    }

    @Test
    fun equalRankFallsBackToUseThenName() {
        val ordered = listOf(
            suggestion("Банан", sourceKind = null, usageCount = 2),
            suggestion("Абрикос", sourceKind = null, usageCount = 2),
            suggestion("Яблоко", sourceKind = null, usageCount = 7),
        ).rankedFor("")

        assertEquals(
            listOf("Яблоко", "Абрикос", "Банан"),
            ordered.map { it.name },
        )
    }

    @Test
    fun containersAreCountedInRussian() {
        assertEquals("1 контейнер", countLabel(1, containers = true))
        assertEquals("2 контейнера", countLabel(2, containers = true))
        assertEquals("4 контейнера", countLabel(4, containers = true))
        assertEquals("5 контейнеров", countLabel(5, containers = true))
        assertEquals("11 контейнеров", countLabel(11, containers = true))
        assertEquals("21 контейнер", countLabel(21, containers = true))
        // «шт» is an abbreviation and does not decline.
        assertEquals("2 шт", countLabel(2, containers = false))
    }

    private fun suggestion(
        name: String,
        sourceKind: String?,
        usageCount: Int = 0,
    ): ComposeSuggestion = ComposeSuggestion.ProductSuggestion(
        Product(
            id = name,
            name = name,
            kind = "product",
            subtitle = null,
            brand = null,
            aliases = emptyList(),
            imageUrl = null,
            kcal = 100.0,
            carbsG = 10.0,
            proteinG = 1.0,
            fatG = 1.0,
            fiberG = 0.0,
            defaultGrams = 100.0,
            usageCount = usageCount,
            lastUsedAt = null,
            sourceKind = sourceKind,
        ),
    )
}
