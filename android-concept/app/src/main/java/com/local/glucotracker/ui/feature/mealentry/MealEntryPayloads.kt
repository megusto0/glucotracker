package com.local.glucotracker.ui.feature.mealentry

import com.local.glucotracker.domain.model.MealDraft
import com.local.glucotracker.domain.model.MealItemPayload
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.Product
import com.local.glucotracker.domain.model.Template
import java.util.UUID
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant

internal fun Product.toProductMealKind(
    weightGrams: Double? = null,
    now: Instant = Clock.System.now(),
    source: String = "manual",
): OutboxKind.CreateMeal {
    val grams = weightGrams ?: defaultGrams ?: 100.0
    val ratio = grams / (defaultGrams ?: 100.0)
    val item = MealItemPayload(
        name = name,
        brand = brand,
        grams = grams,
        kcal = kcal?.let { it * ratio },
        carbsG = carbsG?.let { it * ratio },
        proteinG = proteinG?.let { it * ratio },
        fatG = fatG?.let { it * ratio },
        fiberG = fiberG?.let { it * ratio },
        sourceKind = "product_db",
        productId = id,
    )
    return OutboxKind.CreateMeal(
        payload = MealDraft(
            id = UUID.randomUUID().toString(),
            eatenAt = now,
            title = name,
            note = null,
            localPhotoPath = imageUrl,
            totalKcal = item.kcal ?: 0.0,
            totalCarbsG = item.carbsG ?: 0.0,
            totalProteinG = item.proteinG ?: 0.0,
            totalFatG = item.fatG ?: 0.0,
            totalFiberG = item.fiberG ?: 0.0,
            weightGrams = grams,
        ),
        eatenAt = now,
        source = source,
        items = listOf(item),
    )
}

internal fun Template.toTemplateMealKind(
    weightGrams: Double? = null,
    now: Instant = Clock.System.now(),
): OutboxKind.CreateMeal {
    val grams = weightGrams ?: defaultGrams ?: 100.0
    val ratio = grams / (defaultGrams ?: 100.0)
    val item = MealItemPayload(
        name = name,
        grams = grams,
        kcal = defaultKcal?.let { it * ratio },
        carbsG = defaultCarbsG?.let { it * ratio },
        proteinG = defaultProteinG?.let { it * ratio },
        fatG = defaultFatG?.let { it * ratio },
        fiberG = defaultFiberG?.let { it * ratio },
        sourceKind = itemSourceKind(),
        patternId = id,
    )
    return OutboxKind.CreateMeal(
        payload = MealDraft(
            id = UUID.randomUUID().toString(),
            eatenAt = now,
            title = name,
            note = null,
            localPhotoPath = imageUrl,
            totalKcal = item.kcal ?: 0.0,
            totalCarbsG = item.carbsG ?: 0.0,
            totalProteinG = item.proteinG ?: 0.0,
            totalFatG = item.fatG ?: 0.0,
            totalFiberG = item.fiberG ?: 0.0,
            weightGrams = grams,
        ),
        eatenAt = now,
        source = "pattern",
        items = listOf(item),
    )
}

private fun Template.itemSourceKind(): String =
    if (prefix.lowercase() in RestaurantPatternPrefixes) {
        "restaurant_db"
    } else {
        "pattern"
    }

private val RestaurantPatternPrefixes = setOf("bk", "mc", "kfc", "rostics", "vit")
