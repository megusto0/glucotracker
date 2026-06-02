package com.local.glucotracker.domain.model

import kotlin.math.abs
import kotlinx.datetime.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

fun Meal.hasRestaurantSource(): Boolean =
    items.any { item -> item.sourceKind.equals("restaurant_db", ignoreCase = true) }

fun OutboxKind.CreateMeal.hasRestaurantSource(): Boolean =
    items.any { item -> item.sourceKind.equals("restaurant_db", ignoreCase = true) }

fun Meal.matchesCreateMeal(createMeal: OutboxKind.CreateMeal): Boolean {
    createMeal.idempotencyKey?.let { key ->
        return photoIdempotencyKey == key
    }
    if (!source.equals(createMeal.source, ignoreCase = true)) return false
    if (!eatenAt.sameLocalMinute(createMeal.eatenAt)) return false
    if (!title.sameText(createMeal.payload.title)) return false

    val expectedRefs = createMeal.items.mapNotNull { item -> item.refKey() }.toSet()
    if (expectedRefs.isNotEmpty()) {
        val actualRefs = items.mapNotNull { item -> item.refKey() }.toSet()
        return expectedRefs.all { ref -> ref in actualRefs }
    }

    return totalKcal.closeTo(createMeal.payload.totalKcal, tolerance = 1.0) &&
        totalCarbsG.closeTo(createMeal.payload.totalCarbsG, tolerance = 0.5) &&
        totalProteinG.closeTo(createMeal.payload.totalProteinG, tolerance = 0.5) &&
        totalFatG.closeTo(createMeal.payload.totalFatG, tolerance = 0.5)
}

private fun MealItemPayload.refKey(): String? =
    patternId?.let { "pattern:$it" } ?: productId?.let { "product:$it" }

private fun MealItem.refKey(): String? =
    patternId?.let { "pattern:$it" } ?: productId?.let { "product:$it" }

private fun Instant.sameLocalMinute(other: Instant): Boolean {
    val zone = TimeZone.currentSystemDefault()
    val left = toLocalDateTime(zone)
    val right = other.toLocalDateTime(zone)
    return left.date == right.date &&
        left.hour == right.hour &&
        left.minute == right.minute
}

private fun String?.sameText(other: String?): Boolean =
    orEmpty().trim().equals(other.orEmpty().trim(), ignoreCase = true)

private fun Double.closeTo(other: Double, tolerance: Double): Boolean =
    abs(this - other) <= tolerance
