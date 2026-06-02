package com.local.glucotracker.data.sync

import com.local.glucotracker.data.local.OutboxDao
import com.local.glucotracker.data.local.OutboxEntity
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.generated.model.MealItemResponse
import com.local.glucotracker.generated.model.MealResponse
import java.math.BigDecimal
import javax.inject.Inject
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime
import kotlin.math.abs

class MealReconciler @Inject constructor(
    private val outboxDao: OutboxDao,
) {
    suspend fun reconcileBatch(meals: List<MealResponse>) {
        if (meals.isEmpty()) return
        val pending = pendingItems()
        if (pending.isEmpty()) return

        loop@ for (item in pending) {
            val kind = item.decodeKind() ?: continue@loop
            when (kind) {
                is OutboxKind.CapturedMeal -> {
                    val key = kind.idempotencyKey ?: continue@loop
                    val meal = meals.firstOrNull { meal -> meal.photoIdempotencyKey == key } ?: continue@loop
                    markReconciled(item, meal.id.toString())
                }
                is OutboxKind.CreateMeal -> {
                    val key = kind.idempotencyKey
                    val meal = if (key != null) {
                        meals.firstOrNull { meal -> meal.photoIdempotencyKey == key }
                    } else {
                        if (item.attempts <= 0) continue@loop
                        meals.firstOrNull { meal -> meal.matchesCreateMeal(kind) }
                    } ?: continue@loop
                    markReconciled(item, meal.id.toString())
                }
                else -> Unit
            }
        }
    }

    suspend fun reconcileByKey(idempotencyKey: String, mealId: String) {
        val pending = pendingItems()
        loop@ for (item in pending) {
            val kind = item.decodeKind() ?: continue@loop
            val itemKey = kind.reconciliationKey ?: continue@loop
            if (itemKey != idempotencyKey) continue@loop
            markReconciled(item, mealId)
        }
    }

    private suspend fun pendingItems(): List<OutboxEntity> =
        outboxDao.findInStates(
            listOf(
                OutboxState.Queued,
                OutboxState.Uploading,
                OutboxState.Stuck,
            ),
        )

    private fun OutboxEntity.decodeKind(): OutboxKind? =
        runCatching {
            com.local.glucotracker.data.api.OpenApiJson.json
                .decodeFromString<OutboxKind>(kindJson)
        }.getOrNull()

    private suspend fun markReconciled(item: OutboxEntity, mealId: String) {
        outboxDao.markReconciled(
            id = item.id,
            linkedMealId = mealId,
            reconciledAt = Clock.System.now(),
        )
    }
}

private val OutboxKind.reconciliationKey: String?
    get() = when (this) {
        is OutboxKind.CapturedMeal -> this.idempotencyKey
        is OutboxKind.CreateMeal -> this.idempotencyKey
        else -> null
    }

private fun MealResponse.matchesCreateMeal(createMeal: OutboxKind.CreateMeal): Boolean {
    createMeal.idempotencyKey?.let { key ->
        return photoIdempotencyKey == key
    }
    if (status?.value?.equals("accepted", ignoreCase = true) == false) return false
    if (!source.value.equals(createMeal.source, ignoreCase = true)) return false
    if (!eatenAt.sameLocalMinute(createMeal.eatenAt)) return false
    if (!title.sameText(createMeal.payload.title)) return false

    val expectedRefs = createMeal.items.mapNotNull { item -> item.refKey() }.toSet()
    if (expectedRefs.isNotEmpty()) {
        val actualRefs = items.orEmpty().mapNotNull { item -> item.refKey() }.toSet()
        return expectedRefs.all { ref -> ref in actualRefs }
    }

    return totalKcal.closeTo(createMeal.payload.totalKcal, tolerance = 1.0) &&
        totalCarbsG.closeTo(createMeal.payload.totalCarbsG, tolerance = 0.5) &&
        totalProteinG.closeTo(createMeal.payload.totalProteinG, tolerance = 0.5) &&
        totalFatG.closeTo(createMeal.payload.totalFatG, tolerance = 0.5)
}

private fun com.local.glucotracker.domain.model.MealItemPayload.refKey(): String? =
    patternId?.let { "pattern:$it" } ?: productId?.let { "product:$it" }

private fun MealItemResponse.refKey(): String? =
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

private fun BigDecimal.closeTo(other: Double, tolerance: Double): Boolean =
    abs(toDouble() - other) <= tolerance
