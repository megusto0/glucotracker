package com.local.glucotracker.ui.feature.mealentry

import com.local.glucotracker.domain.model.Product
import com.local.glucotracker.domain.model.Template
import java.util.UUID
import kotlinx.datetime.Instant
import org.junit.Assert.assertEquals
import org.junit.Test

class MealEntryPayloadsTest {
    @Test
    fun productMealKeepsProductIdAndMacrosForSelectedWeight() {
        val productId = UUID.randomUUID().toString()
        val kind = product(productId).toProductMealKind(
            weightGrams = 60.0,
            now = Instant.parse("2026-05-07T08:00:00Z"),
        )

        assertEquals("Protein brownie", kind.payload.title)
        assertEquals(198.0, kind.payload.totalKcal, 0.001)
        assertEquals(24.0, kind.payload.totalCarbsG, 0.001)
        assertEquals(12.0, kind.payload.totalProteinG, 0.001)
        assertEquals(6.0, kind.payload.totalFatG, 0.001)

        val item = kind.items.single()
        assertEquals(productId, item.productId)
        assertEquals("product_db", item.sourceKind)
        assertEquals(60.0, item.grams!!, 0.001)
        assertEquals(198.0, item.kcal!!, 0.001)
        assertEquals(24.0, item.carbsG!!, 0.001)
        assertEquals(12.0, item.proteinG!!, 0.001)
        assertEquals(6.0, item.fatG!!, 0.001)
    }

    @Test
    fun productMealScalesOptimisticMacrosWhenWeightChanges() {
        val kind = product(UUID.randomUUID().toString()).toProductMealKind(
            weightGrams = 30.0,
            now = Instant.parse("2026-05-07T08:00:00Z"),
        )

        val item = kind.items.single()
        assertEquals(30.0, item.grams!!, 0.001)
        assertEquals(99.0, item.kcal!!, 0.001)
        assertEquals(12.0, item.carbsG!!, 0.001)
        assertEquals(6.0, item.proteinG!!, 0.001)
        assertEquals(3.0, item.fatG!!, 0.001)
    }

    @Test
    fun templateMealKeepsPatternIdAndMacros() {
        val templateId = UUID.randomUUID().toString()
        val kind = template(templateId).toTemplateMealKind(
            weightGrams = 150.0,
            now = Instant.parse("2026-05-07T08:00:00Z"),
        )

        val item = kind.items.single()
        assertEquals(templateId, item.patternId)
        assertEquals("pattern", item.sourceKind)
        assertEquals(150.0, item.grams!!, 0.001)
        assertEquals(300.0, item.kcal!!, 0.001)
        assertEquals(30.0, item.carbsG!!, 0.001)
        assertEquals(15.0, item.proteinG!!, 0.001)
        assertEquals(9.0, item.fatG!!, 0.001)
    }

    @Test
    fun restaurantTemplateMealUsesRestaurantSourceKind() {
        val templateId = UUID.randomUUID().toString()
        val kind = template(templateId, prefix = "bk").toTemplateMealKind(
            weightGrams = 100.0,
            now = Instant.parse("2026-05-07T08:00:00Z"),
        )

        val item = kind.items.single()
        assertEquals(templateId, item.patternId)
        assertEquals("restaurant_db", item.sourceKind)
        assertEquals("pattern", kind.source)
    }

    private fun product(id: String) = Product(
        id = id,
        name = "Protein brownie",
        kind = "product",
        subtitle = null,
        brand = "Local",
        aliases = emptyList(),
        imageUrl = null,
        kcal = 198.0,
        carbsG = 24.0,
        proteinG = 12.0,
        fatG = 6.0,
        fiberG = 3.0,
        defaultGrams = 60.0,
        usageCount = 0,
        lastUsedAt = null,
    )

    private fun template(id: String, prefix: String = "") = Template(
        id = id,
        prefix = prefix,
        name = "Breakfast bowl",
        aliases = emptyList(),
        imageUrl = null,
        defaultKcal = 200.0,
        defaultCarbsG = 20.0,
        defaultProteinG = 10.0,
        defaultFatG = 6.0,
        defaultFiberG = 4.0,
        defaultGrams = 100.0,
        usageCount = 0,
        lastUsedAt = null,
    )
}
