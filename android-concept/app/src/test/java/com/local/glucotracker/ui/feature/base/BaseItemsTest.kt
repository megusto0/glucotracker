package com.local.glucotracker.ui.feature.base

import com.local.glucotracker.domain.model.Product
import com.local.glucotracker.domain.model.Template
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The old suite covered a «Рестораны» filter whose predicate was
 * `kind == "restaurant" || subtitle != null`, and the mapper writes "product"
 * into `kind` on every row — so on real data it matched everything carrying any
 * subtitle at all. It passed because its fixtures set `kind` by hand.
 */
class BaseItemsTest {
    @Test
    fun stockSortsByWhatSpoilsFirstAndUnknownShelfLifeGoesLast() {
        val items = buildItems(
            products = listOf(
                stock(id = "unknown", expiresInDays = null),
                stock(id = "week", expiresInDays = 7),
                stock(id = "tomorrow", expiresInDays = 1),
            ),
            templates = emptyList(),
            query = "",
            filter = BaseFilter.Stock,
        )

        assertEquals(listOf("tomorrow", "week", "unknown"), items.map { it.id() })
    }

    @Test
    fun stockExcludesCatalogueProducts() {
        val items = buildItems(
            products = listOf(stock(id = "milk"), product(id = "typed-in")),
            templates = listOf(template(id = "saved")),
            query = "",
            filter = BaseFilter.Stock,
        )

        assertEquals(listOf("milk"), items.map { it.id() })
    }

    @Test
    fun frequentPutsStockAboveAnyUsageCount() {
        val items = buildItems(
            products = listOf(
                product(id = "often", usageCount = 40),
                stock(id = "lentils", usageCount = 0),
            ),
            templates = emptyList(),
            query = "",
            filter = BaseFilter.Frequent,
        )

        assertEquals(listOf("lentils", "often"), items.map { it.id() })
    }

    @Test
    fun needsReviewFindsRowsWithoutEnergy() {
        val items = buildItems(
            products = listOf(
                product(id = "complete", kcal = 120.0, imageUrl = "http://x/y.png"),
                product(id = "no-kcal", kcal = null, imageUrl = "http://x/y.png"),
            ),
            templates = emptyList(),
            query = "",
            filter = BaseFilter.NeedsReview,
        )

        assertEquals(listOf("no-kcal"), items.map { it.id() })
    }

    private fun BaseItem.id(): String = when (this) {
        is BaseItem.Product -> product.id
        is BaseItem.Template -> template.id
    }

    private fun product(
        id: String,
        usageCount: Int = 0,
        kcal: Double? = null,
        imageUrl: String? = null,
    ) = Product(
        id = id,
        name = id,
        kind = "product",
        subtitle = null,
        brand = null,
        aliases = emptyList(),
        imageUrl = imageUrl,
        kcal = kcal,
        carbsG = null,
        proteinG = null,
        fatG = null,
        fiberG = null,
        defaultGrams = null,
        usageCount = usageCount,
        lastUsedAt = null,
    )

    private fun stock(
        id: String,
        expiresInDays: Int? = null,
        usageCount: Int = 0,
    ) = product(id = id, usageCount = usageCount, kcal = 100.0, imageUrl = "http://x/y.png").copy(
        sourceKind = "fridge",
        stockRemaining = 2.0,
        stockUnit = "шт",
        pieceWeightG = 180.0,
        stockExpiresInDays = expiresInDays,
    )

    private fun template(
        id: String,
        prefix: String = "home",
        name: String = id,
    ) = Template(
        id = id,
        prefix = prefix,
        name = name,
        aliases = emptyList(),
        imageUrl = null,
        defaultKcal = null,
        defaultCarbsG = null,
        defaultProteinG = null,
        defaultFatG = null,
        defaultFiberG = null,
        defaultGrams = null,
        usageCount = 0,
        lastUsedAt = null,
    )
}
