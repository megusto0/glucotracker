package com.local.glucotracker.data.repository

import com.local.glucotracker.data.api.GlucoseApi
import com.local.glucotracker.data.api.NightscoutApi
import com.local.glucotracker.data.local.CachedGlucoseDao
import com.local.glucotracker.data.mapper.toCachedEntities
import com.local.glucotracker.data.mapper.toRange
import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.GlucoseRange
import com.local.glucotracker.domain.model.NightscoutConnectionState
import com.local.glucotracker.domain.model.NightscoutDayStatus
import com.local.glucotracker.domain.model.NightscoutStatus
import com.local.glucotracker.domain.model.Source
import com.local.glucotracker.domain.repository.GlucoseRepository
import com.local.glucotracker.domain.repository.NightscoutRepository
import com.local.glucotracker.generated.model.FoodEpisodeResponse
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate

@Singleton
class GlucoseRepositoryImpl @Inject constructor(
    private val glucoseDao: CachedGlucoseDao,
    private val glucoseApi: GlucoseApi,
) : GlucoseRepository {
    override fun observeRange(from: Instant, to: Instant): Flow<CachedView<GlucoseRange>> =
        localFirst(
            cache = { glucoseDao.observeRange(from, to).map { it.toRange() } },
            refresh = {
                val fetchedAt = Clock.System.now()
                val readings = glucoseApi.dashboard(from = from, to = to).toCachedEntities(fetchedAt)
                glucoseDao.upsertAll(readings)
            },
        )

    override fun observeCachedRange(from: Instant, to: Instant): Flow<CachedView<GlucoseRange>> =
        glucoseDao.observeRange(from, to).map { readings ->
            val range = readings.toRange()
            CachedView(
                value = range,
                fetchedAt = readings.maxOfOrNull { it.fetchedAt },
                isRefreshing = false,
                source = if (range == null) Source.Empty else Source.Cache,
            )
        }
}

@Singleton
class NightscoutRepositoryImpl @Inject constructor(
    private val nightscoutApi: NightscoutApi,
) : NightscoutRepository {
    override suspend fun status(): NightscoutStatus {
        val response = nightscoutApi.status()
        return NightscoutStatus(
            lastSyncAt = null,
            queueDepth = 0,
            connectionState = when {
                !response.configured -> NightscoutConnectionState.Unknown
                response.status != null -> NightscoutConnectionState.Connected
                else -> NightscoutConnectionState.Disconnected
            },
        )
    }

    override suspend fun dayStatus(date: LocalDate): NightscoutDayStatus =
        nightscoutApi.dayStatus(date).toDomain()

    override suspend fun syncToday(date: LocalDate): NightscoutDayStatus {
        nightscoutApi.syncToday(date)
        return dayStatus(date)
    }
}

@Singleton
class NightscoutMealContextProvider @Inject constructor(
    private val nightscoutApi: NightscoutApi,
) : MealContextProvider {
    override suspend fun contextByMealId(from: Instant, to: Instant): Map<String, MealContextFlags> =
        nightscoutApi.timeline(from, to).episodes.toMealContext()
}

private fun com.local.glucotracker.generated.model.NightscoutDayStatusResponse.toDomain(): NightscoutDayStatus =
    NightscoutDayStatus(
        date = date,
        configured = configured,
        connected = connected,
        acceptedMealsCount = acceptedMealsCount,
        unsyncedMealsCount = unsyncedMealsCount,
        syncedMealsCount = syncedMealsCount,
        failedMealsCount = failedMealsCount,
        lastSyncAt = lastSyncAt,
    )

private fun List<FoodEpisodeResponse>.toMealContext(): Map<String, MealContextFlags> =
    flatMap { episode ->
        val context = MealContextFlags(
            hasCgm = episode.glucose.orEmpty().isNotEmpty() ||
                episode.glucoseSummary.beforeValue != null ||
                episode.glucoseSummary.latestValue != null ||
                episode.glucoseSummary.minValue != null ||
                episode.glucoseSummary.maxValue != null ||
                episode.glucoseSummary.peakValue != null,
            hasInsulin = episode.insulin.orEmpty().isNotEmpty(),
        )
        episode.meals.map { meal -> meal.id.toString() to context }
    }.toMap()
