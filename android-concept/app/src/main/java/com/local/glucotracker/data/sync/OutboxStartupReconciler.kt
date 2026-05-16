package com.local.glucotracker.data.sync

import android.content.Context
import android.util.Log
import androidx.startup.Initializer
import com.local.glucotracker.data.api.OpenApiJson
import com.local.glucotracker.data.di.DatabaseModule
import com.local.glucotracker.data.mapper.toDomain
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.domain.model.matchesCreateMeal
import kotlinx.coroutines.runBlocking
import kotlinx.datetime.Clock
import kotlin.time.Duration.Companion.minutes

class OutboxStartupReconciler : Initializer<Unit> {
    override fun create(context: Context) {
        val database = try {
            DatabaseModule.createDatabase(context.applicationContext)
        } catch (t: Throwable) {
            Log.w(Tag, "Skipping outbox startup reconciliation: database unavailable.", t)
            return
        }
        try {
            runBlocking {
                val now = Clock.System.now()
                database.outboxDao().revertStaleUploadingToQueued(
                    staleBefore = now - 5.minutes,
                    queuedAt = now,
                )
                reconcileLocal(database)
            }
        } finally {
            database.close()
        }
    }

    private suspend fun reconcileLocal(database: com.local.glucotracker.data.local.GlucotrackerDatabase) {
        val pending = database.outboxDao().findInStates(
            listOf(OutboxState.Queued, OutboxState.Uploading, OutboxState.Stuck),
        )
        if (pending.isEmpty()) return
        val mealsByKey = database.cachedMealDao().allWithIdempotencyKey()
            .mapNotNull { meal -> meal.photoIdempotencyKey?.let { it to meal.id } }
            .toMap()
        val acceptedMeals = database.cachedMealDao().allAccepted().map { meal -> meal.toDomain() }
        if (mealsByKey.isEmpty() && acceptedMeals.isEmpty()) return
        val now = Clock.System.now()
        loop@ for (item in pending) {
            val kind = runCatching {
                OpenApiJson.json.decodeFromString<OutboxKind>(item.kindJson)
            }.getOrNull() ?: continue@loop
            val mealId = when (kind) {
                is OutboxKind.CapturedMeal -> {
                    val key = kind.idempotencyKey ?: continue@loop
                    mealsByKey[key]
                }
                is OutboxKind.CreateMeal -> {
                    if (item.attempts <= 0) continue@loop
                    acceptedMeals.firstOrNull { meal -> meal.matchesCreateMeal(kind) }?.id
                }
                else -> null
            } ?: continue@loop
            database.outboxDao().markReconciled(
                id = item.id,
                linkedMealId = mealId,
                reconciledAt = now,
            )
            Log.i(Tag, "Reconciled outbox item ${item.id} -> meal $mealId on startup.")
        }
    }

    override fun dependencies(): List<Class<out Initializer<*>>> = emptyList()

    private companion object {
        const val Tag = "OutboxStartup"
    }
}
