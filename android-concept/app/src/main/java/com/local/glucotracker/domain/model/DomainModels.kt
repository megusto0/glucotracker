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
    val glucoseRange: GlucoseRange?,
    val dayparts: List<DaypartCard>,
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
)

data class HistoryQuery(
    val fromDay: LocalDate,
    val toDay: LocalDate,
    val filters: Set<HistoryFilter> = emptySet(),
    val status: HistoryStatusFilter = HistoryStatusFilter.Active,
    val search: String = "",
)

enum class HistoryFilter {
    WithCgm,
    WithInsulin,
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
)

data class HistoryDay(
    val date: LocalDate,
    val totals: DayTotals?,
    val meals: List<Meal>,
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

data class GlucoseReading(
    val readingAt: Instant,
    val rawValueMmolL: Double,
    val displayValueMmolL: Double,
    val normalizedValueMmolL: Double?,
    val smoothedValueMmolL: Double?,
    val flags: List<String>,
)

data class GlucoseRange(
    val from: Instant,
    val to: Instant,
    val readings: List<GlucoseReading>,
    val tirSegments: List<TirSegment>,
)

data class TirSegment(
    val label: String,
    val percent: Int,
)

data class DaypartCard(
    val id: String,
    val label: String,
    val kcal: Double,
    val carbsG: Double,
    val mealCount: Int,
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
    @SerialName("photo_estimate_request")
    data class PhotoEstimateRequest(
        val localPhotoPath: String,
        val capturedAt: Instant,
        val source: String,
    ) : OutboxKind

    @Serializable
    @SerialName("accept_draft")
    data class AcceptDraft(
        val estimateId: String,
        val eatenAt: Instant,
        val weightOverride: Double? = null,
        val items: List<MealItemPayload> = emptyList(),
    ) : OutboxKind

    @Serializable
    @SerialName("create_fingerstick")
    data class CreateFingerstick(
        val measuredAt: Instant,
        val glucoseMmolL: Double,
        val meterName: String? = null,
        val notes: String? = null,
    ) : OutboxKind
}

enum class OutboxState {
    Queued,
    Sending,
    Sent,
    Conflict,
    Estimating,
    EstimateReady,
}

data class OutboxItem(
    val id: String,
    val kind: OutboxKind,
    val state: OutboxState,
    val createdAt: Instant,
    val lastAttemptAt: Instant?,
    val attempts: Int,
    val serverIdOnSuccess: String?,
    val errorMessage: String?,
    val draft: MealDraft? = null,
)

data class SyncStatus(
    val queueDepth: Int,
    val lastSyncAt: Instant?,
    val isSyncing: Boolean,
)

data class UserGoals(
    val dailyKcal: Int?,
    val dailyCarbsG: Int?,
    val weightKg: Double?,
)

data class UiPrefs(
    val glucoseMode: String,
    val useCompactRows: Boolean,
)

enum class NightscoutConnectionState {
    Unknown,
    Connected,
    Disconnected,
}

data class NightscoutStatus(
    val lastSyncAt: Instant?,
    val queueDepth: Int,
    val connectionState: NightscoutConnectionState,
)

data class NightscoutDayStatus(
    val date: LocalDate,
    val configured: Boolean,
    val connected: Boolean,
    val acceptedMealsCount: Int,
    val unsyncedMealsCount: Int,
    val syncedMealsCount: Int,
    val failedMealsCount: Int,
    val lastSyncAt: Instant?,
)
