package com.local.glucotracker.data.local

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Fts4
import androidx.room.Index
import androidx.room.PrimaryKey
import androidx.room.TypeConverter
import com.local.glucotracker.domain.model.OutboxState
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate

class GlucotrackerTypeConverters {
    @TypeConverter
    fun instantToLong(value: Instant?): Long? = value?.toEpochMilliseconds()

    @TypeConverter
    fun longToInstant(value: Long?): Instant? = value?.let(Instant::fromEpochMilliseconds)

    @TypeConverter
    fun localDateToString(value: LocalDate?): String? = value?.toString()

    @TypeConverter
    fun stringToLocalDate(value: String?): LocalDate? = value?.let(LocalDate::parse)

    @TypeConverter
    fun outboxStateToString(value: OutboxState?): String? = value?.name

    @TypeConverter
    fun stringToOutboxState(value: String?): OutboxState? =
        value?.let {
            when (it) {
                "Sending" -> OutboxState.Uploading
                "Sent" -> OutboxState.Confirmed
                "EstimateReady", "Estimating" -> OutboxState.Queued
                "Conflict" -> OutboxState.Stuck
                else -> OutboxState.valueOf(it)
            }
        }
}

@Entity(
    tableName = "cached_meals",
    indices = [Index(value = ["eatenAtDay", "eatenAt"])],
)
data class CachedMealEntity(
    @PrimaryKey val id: String,
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
    val fetchedAt: Instant,
    val confidence: Double? = null,
    val hasCgm: Boolean = false,
    val hasInsulin: Boolean = false,
    val itemsJson: String? = null,
    val tagsCsv: String = "",
    val nightscoutSyncStatus: String? = null,
    val nightscoutSyncedAt: Instant? = null,
    val nightscoutLastAttemptAt: Instant? = null,
    val nightscoutSyncError: String? = null,
    val postprandialJson: String? = null,
    val photoIdempotencyKey: String? = null,
    val estimateStatus: String? = null,
    val estimateError: String? = null,
)

@Fts4(tokenizer = "unicode61")
@Entity(tableName = "cached_meal_fts")
data class CachedMealFtsEntity(
    @PrimaryKey
    @ColumnInfo(name = "rowid")
    val rowId: Int,
    val mealId: String,
    val title: String,
    val note: String,
    val source: String,
)

@Entity(tableName = "cached_day_totals")
data class CachedDayTotalsEntity(
    @PrimaryKey val date: LocalDate,
    val kcal: Double,
    val carbsG: Double,
    val proteinG: Double,
    val fatG: Double,
    val fiberG: Double,
    val mealCount: Int,
    val weekAvgKcal: Double?,
    val prevWeekAvgKcal: Double?,
    val weekAvgCarbsG: Double?,
    val prevWeekAvgCarbsG: Double?,
    val hoursSinceLastMeal: Double?,
    val fetchedAt: Instant,
    val netBalanceKcal: Double? = null,
    val tdeeKcal: Double? = null,
    val photoCount: Int = 0,
    val dailyAverageKcalForPeriod: Double? = null,
)

@Entity(tableName = "cached_products")
data class CachedProductEntity(
    @PrimaryKey val id: String,
    val name: String,
    val kind: String,
    val subtitle: String?,
    val brand: String?,
    val aliasesCsv: String,
    val imageUrl: String?,
    val kcal: Double?,
    val carbsG: Double?,
    val proteinG: Double?,
    val fatG: Double?,
    val fiberG: Double?,
    val defaultGrams: Double?,
    val usageCount: Int,
    val lastUsedAt: Instant?,
    val fetchedAt: Instant,
)

@Fts4(tokenizer = "unicode61")
@Entity(tableName = "cached_product_fts")
data class CachedProductFtsEntity(
    @PrimaryKey
    @ColumnInfo(name = "rowid")
    val rowId: Int,
    val productId: String,
    val name: String,
    val subtitle: String,
    val aliases: String,
)

@Entity(tableName = "cached_templates")
data class CachedTemplateEntity(
    @PrimaryKey val id: String,
    val prefix: String = "",
    val name: String,
    val aliasesCsv: String,
    val imageUrl: String?,
    val defaultKcal: Double?,
    val defaultCarbsG: Double?,
    val defaultProteinG: Double?,
    val defaultFatG: Double?,
    val defaultFiberG: Double?,
    val defaultGrams: Double?,
    val usageCount: Int,
    val lastUsedAt: Instant?,
    val fetchedAt: Instant,
)

@Fts4(tokenizer = "unicode61")
@Entity(tableName = "cached_template_fts")
data class CachedTemplateFtsEntity(
    @PrimaryKey
    @ColumnInfo(name = "rowid")
    val rowId: Int,
    val templateId: String,
    val name: String,
    val aliases: String,
)

@Entity(tableName = "outbox")
data class OutboxEntity(
    @PrimaryKey val id: String,
    val kindType: String,
    val kindJson: String,
    val state: OutboxState,
    val createdAt: Instant,
    val lastAttemptAt: Instant?,
    val nextAttemptAt: Instant?,
    val attempts: Int,
    val serverIdOnSuccess: String?,
    val errorMessage: String?,
    val enteredCurrentStateAt: Instant,
    val lastErrorCode: String?,
    val lastErrorMessage: String?,
    val draftJson: String?,
    val localPhotoPath: String?,
    val linkedMealId: String? = null,
    val reconciledAt: Instant? = null,
)
