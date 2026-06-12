package com.local.glucotracker.data.cache

import com.local.glucotracker.data.local.GlucoseCacheDatabase
import kotlinx.datetime.Clock
import kotlinx.datetime.DatePeriod
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.minus
import kotlinx.datetime.toLocalDateTime

object GlucoseCacheBudget {
    fun oldestReadingToKeep(now: Instant): Instant =
        Instant.fromEpochMilliseconds(now.toEpochMilliseconds() - SIX_HOURS_MILLIS)

    fun oldestInsulinDayToKeep(now: Instant): LocalDate =
        now.toLocalDateTime(TimeZone.currentSystemDefault())
            .date
            .minus(DatePeriod(days = INSULIN_DAYS_TO_KEEP))

    suspend fun prune(database: GlucoseCacheDatabase, now: Instant = Clock.System.now()) {
        database.cachedGlucoseDao().pruneOlderThan(oldestReadingToKeep(now))
        database.cachedInsulinEventDao().pruneOlderThan(oldestInsulinDayToKeep(now))
    }

    private const val SIX_HOURS_MILLIS = 6L * 60L * 60L * 1000L

    // Mirrors the offline meal budget: last 14 days stay readable offline.
    private const val INSULIN_DAYS_TO_KEEP = 14
}
