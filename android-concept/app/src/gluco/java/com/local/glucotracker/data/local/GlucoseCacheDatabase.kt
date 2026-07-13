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
    indices = [Index(value = ["day"])],
)
data class CachedInsulinEventEntity(
    @PrimaryKey val id: String,
    val day: LocalDate,
    val timestamp: Instant,
    val doseUnits: Double,
    val kind: String,
    val anchorMealId: String?,
    @ColumnInfo(defaultValue = "0") val isEditable: Boolean,
    val fetchedAt: Instant,
)

@Dao
interface CachedInsulinEventDao {
    @Query("SELECT * FROM cached_insulin_events WHERE day = :day ORDER BY timestamp ASC")
    fun observeDay(day: LocalDate): Flow<List<CachedInsulinEventEntity>>

    @Query("DELETE FROM cached_insulin_events WHERE day = :day")
    suspend fun deleteDay(day: LocalDate)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(events: List<CachedInsulinEventEntity>)

    @Transaction
    suspend fun replaceDay(day: LocalDate, events: List<CachedInsulinEventEntity>) {
        deleteDay(day)
        upsertAll(events)
    }

    @Query("DELETE FROM cached_insulin_events WHERE day < :oldestDayToKeep")
    suspend fun pruneOlderThan(oldestDayToKeep: LocalDate): Int
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

@Database(
    entities = [
        CachedGlucoseEntity::class,
        CachedFingerstickEntity::class,
        CachedInsulinEventEntity::class,
    ],
    version = 4,
    exportSchema = false,
)
@TypeConverters(GlucotrackerTypeConverters::class)
abstract class GlucoseCacheDatabase : RoomDatabase() {
    abstract fun cachedGlucoseDao(): CachedGlucoseDao

    abstract fun cachedFingerstickDao(): CachedFingerstickDao

    abstract fun cachedInsulinEventDao(): CachedInsulinEventDao
}
