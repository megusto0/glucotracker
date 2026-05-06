package com.local.glucotracker.data.cache

import android.content.Context
import androidx.room.Room
import androidx.room.withTransaction
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.local.glucotracker.data.local.GlucotrackerDatabase
import com.local.glucotracker.data.local.PhotoStorage
import java.util.concurrent.TimeUnit
import kotlinx.datetime.Clock
import kotlinx.datetime.DatePeriod
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.minus
import kotlinx.datetime.toLocalDateTime

object CacheBudget {
    fun oldestMealDayToKeep(now: Instant, timeZone: TimeZone = TimeZone.currentSystemDefault()): LocalDate =
        now.toLocalDateTime(timeZone).date.minus(DatePeriod(days = 14))

    fun oldestGlucoseReadingToKeep(now: Instant): Instant =
        Instant.fromEpochMilliseconds(now.toEpochMilliseconds() - SIX_HOURS_MILLIS)

    fun oldestProductUseToKeep(now: Instant): Instant =
        Instant.fromEpochMilliseconds(now.toEpochMilliseconds() - NINETY_DAYS_MILLIS)

    suspend fun prune(database: GlucotrackerDatabase, now: Instant = Clock.System.now()) {
        database.withTransaction {
            database.cachedMealDao().pruneOlderThan(oldestMealDayToKeep(now))
            database.cachedGlucoseDao().pruneOlderThan(oldestGlucoseReadingToKeep(now))
            database.cachedProductDao().pruneUnusedBefore(oldestProductUseToKeep(now))
        }
    }

    private const val SIX_HOURS_MILLIS = 6L * 60L * 60L * 1000L
    private const val NINETY_DAYS_MILLIS = 90L * 24L * 60L * 60L * 1000L
}

class CachePruneWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        val database = Room.databaseBuilder(
            applicationContext,
            GlucotrackerDatabase::class.java,
            "glucotracker.db",
        ).fallbackToDestructiveMigration(dropAllTables = true).build()

        return try {
            CacheBudget.prune(database)
            PhotoStorage(applicationContext).sweepOrphans(
                database.outboxDao().referencedPhotoPaths().toSet(),
            )
            Result.success()
        } finally {
            database.close()
        }
    }
}

object CachePruneScheduler {
    private const val WorkName = "cache-prune"

    fun schedule(context: Context) {
        val request = PeriodicWorkRequestBuilder<CachePruneWorker>(1, TimeUnit.DAYS).build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            WorkName,
            ExistingPeriodicWorkPolicy.UPDATE,
            request,
        )
    }
}
