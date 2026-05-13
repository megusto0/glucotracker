package com.local.glucotracker.data.local

import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Index
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.RoomDatabase
import androidx.room.TypeConverters
import kotlinx.coroutines.flow.Flow
import kotlinx.datetime.Instant

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

@Database(
    entities = [
        CachedGlucoseEntity::class,
    ],
    version = 1,
    exportSchema = false,
)
@TypeConverters(GlucotrackerTypeConverters::class)
abstract class GlucoseCacheDatabase : RoomDatabase() {
    abstract fun cachedGlucoseDao(): CachedGlucoseDao
}
