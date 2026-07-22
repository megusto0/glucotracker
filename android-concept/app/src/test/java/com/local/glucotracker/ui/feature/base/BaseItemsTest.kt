package com.local.glucotracker.ui.feature.base

import com.local.glucotracker.domain.model.Product
import com.local.glucotracker.domain.model.Template
import org.junit.Assert.assertEquals
import org.junit.Test

class BaseItemsTest {
    @Test
    fun restaurantsIncludeRestaurantPatternsAndExcludeRegularTemplates() {
        val restaurantProduct = product(id = "product", kind = "restaurant")
        val rostics = template(id = "rostics", prefix = "rostics")
        val regular = template(id = "regular", prefix = "home")

        val items = buildItems(
            products = listOf(restaurantProduct),
            templates = listOf(rostics, regular),
            query = "",
            filter = BaseFilter.Restaurants,
        )

        assertEquals(
            listOf("product", "rostics"),
            items.map { item ->
                when (item) {
                    is BaseItem.Product -> item.product.id
                    is BaseItem.Template -> item.template.id
                }
            },
        )
    }

    @Test
    fun restaurantPatternCanBeFoundByName() {
        val rostmaster = template(
            id = "rostmaster",
            prefix = "rostics",
            name = "Ростмастер оригинальный",
        )

        val items = buildItems(
            products = emptyList(),
            templates = listOf(rostmaster),
            query = "ростмастер",
            filter = BaseFilter.Restaurants,
        )

        assertEquals(
            listOf("rostmaster"),
            items.map { (it as BaseItem.Template).template.id },
        )
    }

    private fun product(id: String, kind: String) = Product(
        id = id,
        name = id,
        kind = kind,
        subtitle = null,
        brand = null,
        aliases = emptyList(),
        imageUrl = null,
        kcal = null,
        carbsG = null,
        proteinG = null,
        fatG = null,
        fiberG = null,
        defaultGrams = null,
        usageCount = 0,
        lastUsedAt = null,
    )

    private fun template(
        id: String,
        prefix: String,
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
