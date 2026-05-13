package com.local.glucotracker.data.cache

import com.local.glucotracker.data.local.GlucoseCacheDatabase
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant

object GlucoseCacheBudget {
    fun oldestReadingToKeep(now: Instant): Instant =
        Instant.fromEpochMilliseconds(now.toEpochMilliseconds() - SIX_HOURS_MILLIS)

    suspend fun prune(database: GlucoseCacheDatabase, now: Instant = Clock.System.now()) {
        database.cachedGlucoseDao().pruneOlderThan(oldestReadingToKeep(now))
    }

    private const val SIX_HOURS_MILLIS = 6L * 60L * 60L * 1000L
}
