package com.local.glucotracker.data.local

import androidx.room.Dao
import androidx.room.Database
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.RoomDatabase
import androidx.room.Transaction
import androidx.room.TypeConverters
import kotlinx.coroutines.flow.Flow
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate

@Dao
interface OutboxDao {
    @Query("SELECT * FROM outbox ORDER BY createdAt ASC")
    fun observeAll(): Flow<List<OutboxEntity>>

    @Query("SELECT COUNT(*) FROM outbox WHERE state IN ('Queued', 'Uploading')")
    fun observeQueueDepth(): Flow<Int>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(item: OutboxEntity)

    @Query(
        """
        SELECT * FROM outbox
        WHERE (state = 'Queued' AND (nextAttemptAt IS NULL OR nextAttemptAt <= :now))
           OR (
                state = 'Uploading'
                AND (lastAttemptAt IS NULL OR lastAttemptAt <= :staleBefore)
              )
        ORDER BY createdAt ASC
        """,
    )
    suspend fun retryableItems(
        now: Instant,
        staleBefore: Instant,
    ): List<OutboxEntity>

    @Query(
        """
        UPDATE outbox
        SET state = :state,
            lastAttemptAt = :lastAttemptAt,
            nextAttemptAt = :nextAttemptAt,
            attempts = attempts + :attemptDelta,
            errorMessage = :errorMessage,
            enteredCurrentStateAt = CASE WHEN state != :state THEN :stateChangedAt ELSE enteredCurrentStateAt END,
            lastErrorCode = :lastErrorCode,
            lastErrorMessage = :lastErrorMessage
        WHERE id = :id
        """,
    )
    suspend fun updateState(
        id: String,
        state: com.local.glucotracker.domain.model.OutboxState,
        lastAttemptAt: Instant?,
        nextAttemptAt: Instant?,
        attemptDelta: Int,
        errorMessage: String?,
        stateChangedAt: Instant,
        lastErrorCode: String?,
        lastErrorMessage: String?,
    )

    @Query("UPDATE outbox SET state = 'Confirmed', serverIdOnSuccess = :serverIdOnSuccess, lastAttemptAt = :confirmedAt, nextAttemptAt = NULL, errorMessage = NULL, enteredCurrentStateAt = :confirmedAt, lastErrorCode = NULL, lastErrorMessage = NULL WHERE id = :id")
    suspend fun markConfirmed(id: String, serverIdOnSuccess: String?, confirmedAt: Instant)

    @Query("UPDATE outbox SET state = 'Queued', nextAttemptAt = :nextAttemptAt, errorMessage = :errorMessage, enteredCurrentStateAt = :queuedAt, lastErrorCode = :lastErrorCode, lastErrorMessage = :lastErrorMessage WHERE id = :id")
    suspend fun markQueuedForRetry(
        id: String,
        nextAttemptAt: Instant?,
        errorMessage: String?,
        queuedAt: Instant,
        lastErrorCode: String?,
        lastErrorMessage: String?,
    )

    @Query("UPDATE outbox SET state = 'Queued', attempts = 0, lastAttemptAt = NULL, nextAttemptAt = NULL, errorMessage = NULL, enteredCurrentStateAt = :queuedAt, lastErrorCode = NULL, lastErrorMessage = NULL WHERE id = :id")
    suspend fun resetForManualRetry(id: String, queuedAt: Instant)

    @Query("UPDATE outbox SET nextAttemptAt = NULL WHERE state = 'Queued'")
    suspend fun clearQueuedBackoff(): Int

    @Query("UPDATE outbox SET state = 'Queued', nextAttemptAt = NULL, errorMessage = NULL, enteredCurrentStateAt = :queuedAt, lastErrorCode = NULL, lastErrorMessage = NULL WHERE state = 'Uploading' AND (lastAttemptAt IS NULL OR lastAttemptAt <= :staleBefore)")
    suspend fun revertStaleUploadingToQueued(staleBefore: Instant, queuedAt: Instant): Int

    @Query(
        """
        UPDATE outbox
        SET state = 'Stuck',
            nextAttemptAt = NULL,
            errorMessage = NULL,
            enteredCurrentStateAt = :now,
            lastErrorCode = :errorCode,
            lastErrorMessage = NULL
        WHERE state IN ('Queued', 'Uploading')
          AND attempts > 0
          AND enteredCurrentStateAt <= :staleBefore
          AND (nextAttemptAt IS NULL OR nextAttemptAt <= :now)
        """,
    )
    suspend fun markTimedOutActiveRows(
        staleBefore: Instant,
        now: Instant,
        errorCode: String,
    ): Int

    @Query("SELECT localPhotoPath FROM outbox WHERE localPhotoPath IS NOT NULL")
    suspend fun referencedPhotoPaths(): List<String>

    @Query("DELETE FROM outbox WHERE id = :id")
    suspend fun deleteById(id: String)

    @Query(
        """
        UPDATE outbox
        SET state = 'Queued',
            attempts = 0,
            lastAttemptAt = NULL,
            lastErrorCode = NULL,
            lastErrorMessage = NULL,
            nextAttemptAt = NULL,
            enteredCurrentStateAt = :now
        WHERE state = 'Stuck'
          AND lastErrorCode IN (:errorCodes)
          AND linkedMealId IS NULL
        """,
    )
    suspend fun revertNetworkStuck(errorCodes: List<String>, now: Instant): Int

    @Query("SELECT COUNT(*) FROM outbox")
    suspend fun countAll(): Int

    @Query("SELECT * FROM outbox WHERE state IN (:states)")
    suspend fun findInStates(states: List<com.local.glucotracker.domain.model.OutboxState>): List<OutboxEntity>

    @Query(
        """
        UPDATE outbox
        SET state = 'Confirmed',
            serverIdOnSuccess = :linkedMealId,
            linkedMealId = :linkedMealId,
            reconciledAt = :reconciledAt,
            nextAttemptAt = NULL,
            errorMessage = NULL,
            enteredCurrentStateAt = :reconciledAt,
            lastErrorCode = NULL,
            lastErrorMessage = NULL
        WHERE id = :id
        """,
    )
    suspend fun markReconciled(id: String, linkedMealId: String, reconciledAt: Instant)
}

@Dao
abstract class CachedMealDao {
    @Query("SELECT * FROM cached_meals WHERE eatenAtDay = :day ORDER BY eatenAt DESC")
    abstract fun observeForDay(day: LocalDate): Flow<List<CachedMealEntity>>

    @Query("SELECT * FROM cached_meals WHERE eatenAt BETWEEN :from AND :to ORDER BY eatenAt DESC")
    abstract fun observeBetween(from: Instant, to: Instant): Flow<List<CachedMealEntity>>

    @Query("SELECT * FROM cached_meals WHERE id = :id")
    abstract fun observeById(id: String): Flow<CachedMealEntity?>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    protected abstract suspend fun upsertMealsInternal(meals: List<CachedMealEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    protected abstract suspend fun upsertFtsInternal(rows: List<CachedMealFtsEntity>)

    @Query("DELETE FROM cached_meal_fts WHERE mealId IN (:ids)")
    protected abstract suspend fun deleteFts(ids: List<String>)

    @Query("SELECT id FROM cached_meals WHERE eatenAtDay = :day")
    protected abstract suspend fun idsForDay(day: LocalDate): List<String>

    @Query("DELETE FROM cached_meals WHERE id IN (:ids)")
    protected abstract suspend fun deleteMealsByIds(ids: List<String>)

    @Transaction
    open suspend fun upsertAll(meals: List<CachedMealEntity>) {
        if (meals.isEmpty()) return
        val ids = meals.map { it.id }
        deleteFts(ids)
        upsertMealsInternal(meals)
        upsertFtsInternal(meals.map { it.toFtsEntity() })
    }

    @Transaction
    open suspend fun replaceForDay(day: LocalDate, meals: List<CachedMealEntity>) {
        val incomingIds = meals.map { it.id }.toSet()
        val staleIds = idsForDay(day).filterNot { it in incomingIds }
        if (staleIds.isNotEmpty()) {
            deleteFts(staleIds)
            deleteMealsByIds(staleIds)
        }
        upsertAll(meals)
    }

    @Query(
        """
        SELECT * FROM cached_meals
        WHERE eatenAt BETWEEN :from AND :to
          AND (:withCgm = 0 OR hasCgm = 1)
          AND (:withInsulin = 0 OR hasInsulin = 1)
          AND (:lowConfidence = 0 OR (confidence IS NOT NULL AND confidence < :lowConfidenceThreshold))
          AND (:photoOnly = 0 OR source = 'photo' OR thumbnailUrl IS NOT NULL)
          AND (:status IS NULL OR status = :status)
        ORDER BY eatenAt DESC
        """,
    )
    abstract fun observeHistoryRange(
        from: Instant,
        to: Instant,
        withCgm: Boolean,
        withInsulin: Boolean,
        lowConfidence: Boolean,
        photoOnly: Boolean,
        status: String?,
        lowConfidenceThreshold: Double,
    ): Flow<List<CachedMealEntity>>

    @Query(
        """
        SELECT m.* FROM cached_meals m
        JOIN cached_meal_fts f ON m.id = f.mealId
        WHERE cached_meal_fts MATCH :query
          AND m.eatenAt BETWEEN :from AND :to
          AND (:withCgm = 0 OR m.hasCgm = 1)
          AND (:withInsulin = 0 OR m.hasInsulin = 1)
          AND (:lowConfidence = 0 OR (m.confidence IS NOT NULL AND m.confidence < :lowConfidenceThreshold))
          AND (:photoOnly = 0 OR m.source = 'photo' OR m.thumbnailUrl IS NOT NULL)
          AND (:status IS NULL OR m.status = :status)
        ORDER BY m.eatenAt DESC
        """,
    )
    abstract fun observeHistorySearch(
        from: Instant,
        to: Instant,
        query: String,
        withCgm: Boolean,
        withInsulin: Boolean,
        lowConfidence: Boolean,
        photoOnly: Boolean,
        status: String?,
        lowConfidenceThreshold: Double,
    ): Flow<List<CachedMealEntity>>

    @Query("DELETE FROM cached_meals WHERE eatenAtDay < :oldestDayToKeep")
    abstract suspend fun pruneOlderThan(oldestDayToKeep: LocalDate): Int

    @Query("SELECT COUNT(*) FROM cached_meals")
    abstract suspend fun countAll(): Int

    @Query("SELECT * FROM cached_meals WHERE photoIdempotencyKey IS NOT NULL")
    abstract suspend fun allWithIdempotencyKey(): List<CachedMealEntity>

    @Query("SELECT * FROM cached_meals WHERE status = 'accepted'")
    abstract suspend fun allAccepted(): List<CachedMealEntity>

    private fun CachedMealEntity.toFtsEntity(): CachedMealFtsEntity =
        CachedMealFtsEntity(
            rowId = id.hashCode(),
            mealId = id,
            title = title.orEmpty(),
            note = note.orEmpty(),
            source = source,
        )
}

@Dao
interface CachedDayTotalsDao {
    @Query("SELECT * FROM cached_day_totals WHERE date = :date")
    fun observeDay(date: LocalDate): Flow<CachedDayTotalsEntity?>

    @Query("SELECT * FROM cached_day_totals WHERE date BETWEEN :from AND :to ORDER BY date DESC")
    fun observeBetween(from: LocalDate, to: LocalDate): Flow<List<CachedDayTotalsEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(total: CachedDayTotalsEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(totals: List<CachedDayTotalsEntity>)
}

@Dao
abstract class CachedProductDao {
    @Query("SELECT * FROM cached_products ORDER BY usageCount DESC, name ASC")
    abstract fun observeAll(): Flow<List<CachedProductEntity>>

    @Query("SELECT * FROM cached_products ORDER BY usageCount DESC, name ASC LIMIT :limit")
    abstract suspend fun top(limit: Int): List<CachedProductEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    protected abstract suspend fun upsertProductsInternal(products: List<CachedProductEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    protected abstract suspend fun upsertFtsInternal(rows: List<CachedProductFtsEntity>)

    @Query("DELETE FROM cached_product_fts WHERE productId IN (:ids)")
    protected abstract suspend fun deleteFts(ids: List<String>)

    @Query("DELETE FROM cached_product_fts")
    protected abstract suspend fun deleteAllFts()

    @Query("DELETE FROM cached_products")
    protected abstract suspend fun deleteAllInternal()

    @Transaction
    open suspend fun upsertAll(products: List<CachedProductEntity>) {
        if (products.isEmpty()) return
        val ids = products.map { it.id }
        deleteFts(ids)
        upsertProductsInternal(products)
        upsertFtsInternal(products.map { it.toFtsEntity() })
    }

    @Transaction
    open suspend fun replaceAll(products: List<CachedProductEntity>) {
        deleteAllFts()
        deleteAllInternal()
        if (products.isEmpty()) return
        upsertProductsInternal(products)
        upsertFtsInternal(products.map { it.toFtsEntity() })
    }

    @Query(
        """
        SELECT p.* FROM cached_products p
        JOIN cached_product_fts f ON p.id = f.productId
        WHERE cached_product_fts MATCH :query
        ORDER BY p.usageCount DESC, p.name ASC
        LIMIT :limit
        """,
    )
    abstract suspend fun searchFts(query: String, limit: Int): List<CachedProductEntity>

    @Query("DELETE FROM cached_products WHERE lastUsedAt IS NOT NULL AND lastUsedAt < :oldestUseToKeep")
    abstract suspend fun pruneUnusedBefore(oldestUseToKeep: Instant): Int

    private fun CachedProductEntity.toFtsEntity(): CachedProductFtsEntity =
        CachedProductFtsEntity(
            rowId = id.hashCode(),
            productId = id,
            name = name,
            subtitle = subtitle.orEmpty(),
            aliases = aliasesCsv,
        )
}

@Dao
abstract class CachedTemplateDao {
    @Query("SELECT * FROM cached_templates ORDER BY usageCount DESC, name ASC")
    abstract fun observeAll(): Flow<List<CachedTemplateEntity>>

    @Query("SELECT * FROM cached_templates ORDER BY usageCount DESC, name ASC LIMIT :limit")
    abstract suspend fun top(limit: Int): List<CachedTemplateEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    protected abstract suspend fun upsertTemplatesInternal(templates: List<CachedTemplateEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    protected abstract suspend fun upsertFtsInternal(rows: List<CachedTemplateFtsEntity>)

    @Query("DELETE FROM cached_template_fts WHERE templateId IN (:ids)")
    protected abstract suspend fun deleteFts(ids: List<String>)

    @Query("DELETE FROM cached_template_fts")
    protected abstract suspend fun deleteAllFts()

    @Query("DELETE FROM cached_templates")
    protected abstract suspend fun deleteAllInternal()

    @Transaction
    open suspend fun upsertAll(templates: List<CachedTemplateEntity>) {
        if (templates.isEmpty()) return
        val ids = templates.map { it.id }
        deleteFts(ids)
        upsertTemplatesInternal(templates)
        upsertFtsInternal(templates.map { it.toFtsEntity() })
    }

    @Transaction
    open suspend fun replaceAll(templates: List<CachedTemplateEntity>) {
        deleteAllFts()
        deleteAllInternal()
        if (templates.isEmpty()) return
        upsertTemplatesInternal(templates)
        upsertFtsInternal(templates.map { it.toFtsEntity() })
    }

    @Query(
        """
        SELECT t.* FROM cached_templates t
        JOIN cached_template_fts f ON t.id = f.templateId
        WHERE cached_template_fts MATCH :query
        ORDER BY t.usageCount DESC, t.name ASC
        LIMIT :limit
        """,
    )
    abstract suspend fun searchFts(query: String, limit: Int): List<CachedTemplateEntity>

    private fun CachedTemplateEntity.toFtsEntity(): CachedTemplateFtsEntity =
        CachedTemplateFtsEntity(
            rowId = id.hashCode(),
            templateId = id,
            name = name,
            aliases = aliasesCsv,
        )
}

@Database(
    entities = [
        CachedMealEntity::class,
        CachedMealFtsEntity::class,
        CachedDayTotalsEntity::class,
        CachedProductEntity::class,
        CachedProductFtsEntity::class,
        CachedTemplateEntity::class,
        CachedTemplateFtsEntity::class,
        OutboxEntity::class,
    ],
    version = 13,
    exportSchema = false,
)
@TypeConverters(GlucotrackerTypeConverters::class)
abstract class GlucotrackerDatabase : RoomDatabase() {
    abstract fun outboxDao(): OutboxDao
    abstract fun cachedMealDao(): CachedMealDao
    abstract fun cachedDayTotalsDao(): CachedDayTotalsDao
    abstract fun cachedProductDao(): CachedProductDao
    abstract fun cachedTemplateDao(): CachedTemplateDao
}
