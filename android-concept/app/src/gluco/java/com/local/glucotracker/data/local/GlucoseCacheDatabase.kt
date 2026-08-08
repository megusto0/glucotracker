package com.local.glucotracker.data.local

import androidx.room.ColumnInfo
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Index
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.RoomDatabase
import androidx.room.Transaction
import androidx.room.TypeConverters
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import kotlinx.coroutines.flow.Flow
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate

@Entity(
    tableName = "cached_glucose",
    indices = [Index(value = ["readingAt"])],
)
data class CachedGlucoseEntity(
    @PrimaryKey val readingAt: Instant,
    val rawValueMmolL: Double,
    val displayValueMmolL: Double,
    val normalizedValueMmolL: Double?,
    val smoothedValueMmolL: Double?,
    val flagsCsv: String,
    val fetchedAt: Instant,
)

@Dao
interface CachedGlucoseDao {
    @Query("SELECT * FROM cached_glucose WHERE readingAt BETWEEN :from AND :to ORDER BY readingAt ASC")
    fun observeRange(from: Instant, to: Instant): Flow<List<CachedGlucoseEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(readings: List<CachedGlucoseEntity>)

    @Query("DELETE FROM cached_glucose WHERE readingAt < :oldestReadingToKeep")
    suspend fun pruneOlderThan(oldestReadingToKeep: Instant): Int
}

@Entity(
    tableName = "cached_fingersticks",
    indices = [Index(value = ["measuredAt"])],
)
data class CachedFingerstickEntity(
    @PrimaryKey val id: String,
    val measuredAt: Instant,
    val glucoseMmolL: Double,
    val meterName: String?,
    val notes: String?,
    val createdAt: Instant,
    val fetchedAt: Instant,
)

@Dao
interface CachedFingerstickDao {
    @Query("SELECT * FROM cached_fingersticks WHERE measuredAt BETWEEN :from AND :to ORDER BY measuredAt DESC")
    fun observeRange(from: Instant, to: Instant): Flow<List<CachedFingerstickEntity>>

    @Query("DELETE FROM cached_fingersticks WHERE measuredAt BETWEEN :from AND :to")
    suspend fun deleteRange(from: Instant, to: Instant)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(readings: List<CachedFingerstickEntity>)

    @Transaction
    suspend fun replaceRange(
        from: Instant,
        to: Instant,
        readings: List<CachedFingerstickEntity>,
    ) {
        deleteRange(from, to)
        upsertAll(readings)
    }

    @Query("DELETE FROM cached_fingersticks WHERE measuredAt < :oldestReadingToKeep")
    suspend fun pruneOlderThan(oldestReadingToKeep: Instant): Int
}

/**
 * Offline cache of the backend insulin attribution for one local day.
 * Once an event was seen, it survives offline and process death.
 */
@Entity(
    tableName = "cached_insulin_events",
    indices = [
        Index(value = ["day"]),
        Index(value = ["userId", "day"]),
    ],
)
data class CachedInsulinEventEntity(
    @PrimaryKey val id: String,
    @ColumnInfo(defaultValue = "''") val userId: String,
    val day: LocalDate,
    val timestamp: Instant,
    val doseUnits: Double,
    val kind: String,
    val anchorMealId: String?,
    @ColumnInfo(defaultValue = "0") val isEditable: Boolean,
    val fetchedAt: Instant,
)

/**
 * Server-owned episode snapshot used to preserve grouping and footer facts
 * across process death. Meal/insulin ids are UUIDs, so comma-separated storage
 * is unambiguous and keeps this cache read-only and deliberately denormalized.
 */
@Entity(
    tableName = "cached_episodes",
    primaryKeys = ["userId", "key"],
    indices = [Index(value = ["userId", "day"])],
)
data class CachedEpisodeEntity(
    val userId: String,
    val key: String,
    val day: LocalDate,
    val startAt: Instant,
    val classification: String,
    val mealIdsCsv: String,
    val insulinIdsCsv: String,
    val outcomeStatus: String,
    val outcomeKind: String,
    val outcomeStartValue: Double?,
    val outcomeResultValue: Double?,
    val outcomeDeltaMmolL: Double?,
    val outcomeIsLow: Boolean,
    val fetchedAt: Instant,
)

@Dao
interface CachedInsulinEventDao {
    @Query(
        "SELECT * FROM cached_insulin_events " +
            "WHERE userId = :userId AND day = :day ORDER BY timestamp ASC",
    )
    fun observeDay(userId: String, day: LocalDate): Flow<List<CachedInsulinEventEntity>>

    @Query(
        "SELECT * FROM cached_episodes " +
            "WHERE userId = :userId AND day = :day ORDER BY startAt ASC",
    )
    fun observeEpisodesDay(userId: String, day: LocalDate): Flow<List<CachedEpisodeEntity>>

    @Query("DELETE FROM cached_insulin_events WHERE userId = :userId AND day = :day")
    suspend fun deleteDay(userId: String, day: LocalDate)

    @Query("DELETE FROM cached_episodes WHERE userId = :userId AND day = :day")
    suspend fun deleteEpisodesDay(userId: String, day: LocalDate)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(events: List<CachedInsulinEventEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertEpisodes(episodes: List<CachedEpisodeEntity>)

    @Transaction
    suspend fun replaceDay(
        userId: String,
        day: LocalDate,
        events: List<CachedInsulinEventEntity>,
        episodes: List<CachedEpisodeEntity>,
    ) {
        deleteDay(userId, day)
        deleteEpisodesDay(userId, day)
        upsertAll(events)
        upsertEpisodes(episodes)
    }

    @Query("DELETE FROM cached_insulin_events WHERE day < :oldestDayToKeep")
    suspend fun pruneEventsOlderThan(oldestDayToKeep: LocalDate): Int

    @Query("DELETE FROM cached_episodes WHERE day < :oldestDayToKeep")
    suspend fun pruneEpisodesOlderThan(oldestDayToKeep: LocalDate): Int

    @Transaction
    suspend fun pruneOlderThan(oldestDayToKeep: LocalDate): Int =
        pruneEventsOlderThan(oldestDayToKeep) + pruneEpisodesOlderThan(oldestDayToKeep)
}

val GLUCOSE_CACHE_MIGRATION_1_2 = object : Migration(1, 2) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL(
            "CREATE TABLE IF NOT EXISTS `cached_insulin_events` (" +
                "`id` TEXT NOT NULL, " +
                "`day` TEXT NOT NULL, " +
                "`timestamp` INTEGER NOT NULL, " +
                "`doseUnits` REAL NOT NULL, " +
                "`kind` TEXT NOT NULL, " +
                "`anchorMealId` TEXT, " +
                "`fetchedAt` INTEGER NOT NULL, " +
                "PRIMARY KEY(`id`))",
        )
        db.execSQL(
            "CREATE INDEX IF NOT EXISTS `index_cached_insulin_events_day` " +
                "ON `cached_insulin_events` (`day`)",
        )
    }
}

val GLUCOSE_CACHE_MIGRATION_2_3 = object : Migration(2, 3) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL(
            "CREATE TABLE IF NOT EXISTS `cached_fingersticks` (" +
                "`id` TEXT NOT NULL, " +
                "`measuredAt` INTEGER NOT NULL, " +
                "`glucoseMmolL` REAL NOT NULL, " +
                "`meterName` TEXT, " +
                "`notes` TEXT, " +
                "`createdAt` INTEGER NOT NULL, " +
                "`fetchedAt` INTEGER NOT NULL, " +
                "PRIMARY KEY(`id`))",
        )
        db.execSQL(
            "CREATE INDEX IF NOT EXISTS `index_cached_fingersticks_measuredAt` " +
                "ON `cached_fingersticks` (`measuredAt`)",
        )
    }
}

val GLUCOSE_CACHE_MIGRATION_3_4 = object : Migration(3, 4) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL(
            "ALTER TABLE `cached_insulin_events` " +
                "ADD COLUMN `isEditable` INTEGER NOT NULL DEFAULT 0",
        )
    }
}

val GLUCOSE_CACHE_MIGRATION_4_5 = object : Migration(4, 5) {
    override fun migrate(db: SupportSQLiteDatabase) {
        // Legacy rows cannot safely be attributed after multi-user auth. Keep
        // them non-destructively, but hide them behind an empty owner until a
        // fresh user-scoped day snapshot replaces them.
        db.execSQL(
            "ALTER TABLE `cached_insulin_events` " +
                "ADD COLUMN `userId` TEXT NOT NULL DEFAULT ''",
        )
        db.execSQL(
            "CREATE INDEX IF NOT EXISTS `index_cached_insulin_events_userId_day` " +
                "ON `cached_insulin_events` (`userId`, `day`)",
        )
        db.execSQL(
            "CREATE TABLE IF NOT EXISTS `cached_episodes` (" +
                "`userId` TEXT NOT NULL, " +
                "`key` TEXT NOT NULL, " +
                "`day` TEXT NOT NULL, " +
                "`startAt` INTEGER NOT NULL, " +
                "`classification` TEXT NOT NULL, " +
                "`mealIdsCsv` TEXT NOT NULL, " +
                "`insulinIdsCsv` TEXT NOT NULL, " +
                "`outcomeStatus` TEXT NOT NULL, " +
                "`outcomeKind` TEXT NOT NULL, " +
                "`outcomeStartValue` REAL, " +
                "`outcomeResultValue` REAL, " +
                "`outcomeDeltaMmolL` REAL, " +
                "`outcomeIsLow` INTEGER NOT NULL, " +
                "`fetchedAt` INTEGER NOT NULL, " +
                "PRIMARY KEY(`userId`, `key`))",
        )
        db.execSQL(
            "CREATE INDEX IF NOT EXISTS `index_cached_episodes_userId_day` " +
                "ON `cached_episodes` (`userId`, `day`)",
        )
    }
}

@Database(
    entities = [
        CachedGlucoseEntity::class,
        CachedFingerstickEntity::class,
        CachedInsulinEventEntity::class,
        CachedEpisodeEntity::class,
    ],
    version = 5,
    exportSchema = false,
)
@TypeConverters(GlucotrackerTypeConverters::class)
abstract class GlucoseCacheDatabase : RoomDatabase() {
    abstract fun cachedGlucoseDao(): CachedGlucoseDao

    abstract fun cachedFingerstickDao(): CachedFingerstickDao

    abstract fun cachedInsulinEventDao(): CachedInsulinEventDao
}
