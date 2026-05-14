package com.local.glucotracker.domain.model

import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

enum class Source {
    Cache,
    Network,
    Empty,
}

data class CachedView<T>(
    val value: T?,
    val fetchedAt: Instant?,
    val isRefreshing: Boolean,
    val source: Source,
)

data class DayState(
    val date: LocalDate,
    val totals: DayTotals,
    val kpis: KpiSnapshot,
    val meals: List<Meal>,
)

data class DayTotals(
    val date: LocalDate,
    val kcal: Double,
    val carbsG: Double,
    val proteinG: Double,
    val fatG: Double,
    val fiberG: Double,
    val mealCount: Int,
    val fetchedAt: Instant? = null,
    val netBalanceKcal: Double? = null,
    val tdeeKcal: Double? = null,
    val photoCount: Int = 0,
    val dailyAverageKcalForPeriod: Double? = null,
)

enum class StatsPeriod(val days: Int, val apiValue: String) {
    Week(days = 7, apiValue = "7d"),
    Fortnight(days = 14, apiValue = "14d"),
    Month(days = 30, apiValue = "30d"),
}

data class StatsInsight(
    val id: String,
    val kind: String,
    val text: String,
    val weight: String = "secondary",
    val supportingNumbers: Map<String, String> = emptyMap(),
)

@Serializable
data class PostprandialPoint(
    val offsetMinutes: Int,
    val valueMmolL: Double,
)

@Serializable
data class PostprandialResponse(
    val deltaMaxMmolL: Double? = null,
    val coverage180: Double? = null,
    val points: List<PostprandialPoint> = emptyList(),
)

data class KpiSnapshot(
    val kcal: Double,
    val weekAvgKcal: Double?,
    val prevWeekAvgKcal: Double?,
    val carbsG: Double,
    val weekAvgCarbsG: Double?,
    val prevWeekAvgCarbsG: Double?,
    val mealCount: Int,
    val hoursSinceLastMeal: Double?,
)

data class Meal(
    val id: String,
    val eatenAt: Instant,
    val eatenAtDay: LocalDate,
    val title: String?,
    val status: String,
    val source: String,
    val note: String?,
    val thumbnailUrl: String?,
    val totalKcal: Double,
    val totalCarbsG: Double,
    val totalProteinG: Double,
    val totalFatG: Double,
    val totalFiberG: Double,
    val updatedAt: Instant,
    val confidence: Double? = null,
    val hasCgm: Boolean = false,
    val hasInsulin: Boolean = false,
    val items: List<MealItem> = emptyList(),
    val nightscoutSyncStatus: String? = null,
    val nightscoutSyncedAt: Instant? = null,
    val nightscoutLastAttemptAt: Instant? = null,
    val nightscoutSyncError: String? = null,
    val tags: Set<String> = emptySet(),
    val mealRole: String? = null,
    val postprandialResponse: PostprandialResponse? = null,
    val estimateStatus: String? = null,
    val estimateError: String? = null,
)

@Serializable
data class MealItem(
    val id: String,
    val mealId: String,
    val name: String,
    val grams: Double? = null,
    val kcal: Double? = null,
    val carbsG: Double? = null,
    val proteinG: Double? = null,
    val fatG: Double? = null,
    val fiberG: Double? = null,
    val sourceKind: String? = null,
    val patternId: String? = null,
    val productId: String? = null,
)

data class HistoryQuery(
    val fromDay: LocalDate,
    val toDay: LocalDate,
    val filters: Set<HistoryFilter> = emptySet(),
    val status: HistoryStatusFilter = HistoryStatusFilter.Active,
    val search: String = "",
)

enum class HistoryFilter {
    Sweet,
    Breakfast,
    LowConfidence,
    PhotoOnly,
}

enum class HistoryStatusFilter {
    Active,
    Accepted,
    Drafts,
    All,
}

data class HistoryPage(
    val days: List<HistoryDay>,
    val totalDays: Int = days.size,
    val totalRecords: Int = days.sumOf { day -> day.meals.size },
)

data class HistoryDay(
    val date: LocalDate,
    val totals: DayTotals?,
    val meals: List<Meal>,
    val dailyAverageKcalForPeriod: Double? = null,
    val photoCount: Int = meals.count { meal -> meal.source == "photo" || meal.thumbnailUrl != null },
)

@Serializable
data class MealDraft(
    val id: String,
    val eatenAt: Instant,
    val title: String?,
    val note: String?,
    val localPhotoPath: String?,
    val totalKcal: Double,
    val totalCarbsG: Double,
    val totalProteinG: Double,
    val totalFatG: Double,
    val totalFiberG: Double,
    val weightGrams: Double? = null,
    val items: List<MealItemPayload> = emptyList(),
)

data class Product(
    val id: String,
    val name: String,
    val kind: String,
    val subtitle: String?,
    val brand: String?,
    val aliases: List<String>,
    val imageUrl: String?,
    val kcal: Double?,
    val carbsG: Double?,
    val proteinG: Double?,
    val fatG: Double?,
    val fiberG: Double?,
    val defaultGrams: Double?,
    val usageCount: Int,
    val lastUsedAt: Instant?,
)

data class Template(
    val id: String,
    val prefix: String = "",
    val name: String,
    val aliases: List<String>,
    val imageUrl: String?,
    val defaultKcal: Double?,
    val defaultCarbsG: Double?,
    val defaultProteinG: Double?,
    val defaultFatG: Double?,
    val defaultFiberG: Double?,
    val defaultGrams: Double?,
    val usageCount: Int,
    val lastUsedAt: Instant?,
)

@Serializable
data class MealItemPayload(
    val name: String,
    val brand: String? = null,
    val grams: Double? = null,
    val kcal: Double? = null,
    val carbsG: Double? = null,
    val proteinG: Double? = null,
    val fatG: Double? = null,
    val fiberG: Double? = null,
    val sourceKind: String? = null,
    val servingText: String? = null,
    val confidence: Double? = null,
    val confidenceReason: String? = null,
    val calculationMethod: String? = null,
    val patternId: String? = null,
    val productId: String? = null,
    val photoId: String? = null,
    val position: Int? = 0,
)

@Serializable
data class MealPatchPayload(
    val title: String? = null,
    val note: String? = null,
    val eatenAt: Instant? = null,
    val weightGrams: Double? = null,
)

@Serializable
data class MealItemPatchPayload(
    val name: String? = null,
    val grams: Double? = null,
    val kcal: Double? = null,
    val carbsG: Double? = null,
    val proteinG: Double? = null,
    val fatG: Double? = null,
    val fiberG: Double? = null,
)

@Serializable
sealed interface OutboxKind {
    @Serializable
    @SerialName("create_meal")
    data class CreateMeal(
        val payload: MealDraft,
        val eatenAt: Instant,
        val source: String,
        val items: List<MealItemPayload> = emptyList(),
    ) : OutboxKind

    @Serializable
    @SerialName("edit_meal")
    data class EditMeal(
        val serverId: String,
        val patch: MealPatchPayload,
    ) : OutboxKind

    @Serializable
    @SerialName("delete_meal")
    data class DeleteMeal(
        val serverId: String,
    ) : OutboxKind

    @Serializable
    @SerialName("patch_meal_item")
    data class PatchMealItem(
        val mealId: String,
        val itemId: String,
        val patch: MealItemPatchPayload,
    ) : OutboxKind

    @Serializable
    @SerialName("copy_meal_item_weight")
    data class CopyMealItemWeight(
        val mealId: String,
        val itemId: String,
        val grams: Double,
        val eatenAt: Instant,
    ) : OutboxKind

    @Serializable
    @SerialName("captured_meal")
    data class CapturedMeal(
        val localPhotoPath: String?,
        val capturedAt: Instant,
        val source: String,
        val optimisticName: String? = null,
        val optimisticWeightG: Int? = null,
        val idempotencyKey: String? = null,
    ) : OutboxKind

}

enum class OutboxState {
    Queued,
    Uploading,
    Confirmed,
    Stuck,
}

data class OutboxItem(
    val id: String,
    val kind: OutboxKind,
    val state: OutboxState,
    val createdAt: Instant,
    val lastAttemptAt: Instant?,
    val nextAttemptAt: Instant? = null,
    val attempts: Int,
    val serverIdOnSuccess: String?,
    val errorMessage: String?,
    val enteredCurrentStateAt: Instant = createdAt,
    val lastErrorCode: String? = null,
    val lastErrorMessage: String? = errorMessage,
    val draft: MealDraft? = null,
    val linkedMealId: String? = null,
    val reconciledAt: Instant? = null,
) {
    val isZombie: Boolean
        get() = linkedMealId != null

    val idempotencyKey: String?
        get() = (kind as? OutboxKind.CapturedMeal)?.idempotencyKey
}

data class SyncStatus(
    val queueDepth: Int,
    val lastSyncAt: Instant?,
    val isSyncing: Boolean,
)

data class UserError(
    val code: String,
    val message: String,
    val severity: Severity,
    val retryable: Boolean,
) {
    enum class Severity {
        Info,
        Warn,
        Error,
    }
}

data class UserGoals(
    val dailyKcal: Int?,
    val dailyProteinG: Int?,
    val dailyCarbsG: Int?,
    val dailyFatG: Int?,
    val weightKg: Double?,
    val goalsSetupCompleted: Boolean = false,
)

data class UiPrefs(
    val glucoseMode: String,
    val useCompactRows: Boolean,
)
