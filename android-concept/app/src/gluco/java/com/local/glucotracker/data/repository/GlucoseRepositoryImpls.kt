package com.local.glucotracker.data.repository

import com.local.glucotracker.data.api.GlucoseApi
import com.local.glucotracker.data.api.NightscoutApi
import com.local.glucotracker.data.local.CachedFingerstickDao
import com.local.glucotracker.data.local.CachedGlucoseDao
import com.local.glucotracker.data.mapper.toCachedFingersticks
import com.local.glucotracker.data.mapper.toCachedEntities
import com.local.glucotracker.data.mapper.toFingersticks
import com.local.glucotracker.data.mapper.toRange
import com.local.glucotracker.data.mapper.withNormalizedDisplay
import com.local.glucotracker.data.settings.GlucoSettingsStore
import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.FingerstickReading
import com.local.glucotracker.domain.model.GlucoseRange
import com.local.glucotracker.domain.model.NightscoutConnectionState
import com.local.glucotracker.domain.model.NightscoutDayStatus
import com.local.glucotracker.domain.model.NightscoutStatus
import com.local.glucotracker.domain.model.Source
import com.local.glucotracker.domain.model.SensorPhase
import com.local.glucotracker.domain.model.SensorQuality
import com.local.glucotracker.domain.model.SensorQualityConfidence
import com.local.glucotracker.domain.model.SensorSession
import com.local.glucotracker.domain.repository.GlucoseRepository
import com.local.glucotracker.domain.repository.NightscoutRepository
import com.local.glucotracker.domain.repository.SensorRepository
import com.local.glucotracker.generated.model.FoodEpisodeResponse
import com.local.glucotracker.generated.model.SensorQualityResponse
import com.local.glucotracker.generated.model.SensorSessionResponse
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate

@Singleton
class GlucoseRepositoryImpl @Inject constructor(
    private val glucoseDao: CachedGlucoseDao,
    private val glucoseApi: GlucoseApi,
    private val settingsStore: GlucoSettingsStore,
) : GlucoseRepository {
    override fun observeRange(from: Instant, to: Instant): Flow<CachedView<GlucoseRange>> =
        combine(
            localFirst(
                cache = { glucoseDao.observeRange(from, to).map { it.toRange() } },
                refresh = {
                    val fetchedAt = Clock.System.now()
                    val readings = glucoseApi.dashboard(from = from, to = to).toCachedEntities(fetchedAt)
                    glucoseDao.upsertAll(readings)
                },
            ),
            settingsStore.normalizedGlucoseDisplay,
        ) { cached, normalized ->
            cached.copy(value = cached.value?.withNormalizedDisplay(normalized))
        }

    override fun observeCachedRange(from: Instant, to: Instant): Flow<CachedView<GlucoseRange>> =
        combine(
            glucoseDao.observeRange(from, to),
            settingsStore.normalizedGlucoseDisplay,
        ) { readings, normalized ->
            val range = readings.toRange()?.withNormalizedDisplay(normalized)
            CachedView(
                value = range,
                fetchedAt = readings.maxOfOrNull { it.fetchedAt },
                isRefreshing = false,
                source = if (range == null) Source.Empty else Source.Cache,
            )
        }
}

@Singleton
class SensorRepositoryImpl @Inject constructor(
    private val glucoseApi: GlucoseApi,
    private val fingerstickDao: CachedFingerstickDao,
) : SensorRepository {
    private val sensors = MutableStateFlow(
        CachedView<List<SensorSession>>(
            value = null,
            fetchedAt = null,
            isRefreshing = false,
            source = Source.Empty,
        ),
    )

    override fun observeSensors(): Flow<CachedView<List<SensorSession>>> = sensors

    override fun observeFingersticks(
        from: Instant,
        to: Instant,
    ): Flow<CachedView<List<FingerstickReading>>> =
        localFirst(
            cache = {
                fingerstickDao.observeRange(from, to).map { rows ->
                    rows.toFingersticks().takeIf { it.isNotEmpty() }
                }
            },
            refresh = { refreshFingersticks(from, to) },
        )

    override suspend fun refreshSensors() {
        sensors.update { it.copy(isRefreshing = true) }
        runCatching { glucoseApi.sensors().map { it.toDomain() } }
            .onSuccess { refreshed ->
                sensors.value = CachedView(
                    value = refreshed,
                    fetchedAt = Clock.System.now(),
                    isRefreshing = false,
                    source = Source.Network,
                )
            }
            .onFailure {
                sensors.update { cached -> cached.copy(isRefreshing = false) }
            }
    }

    override suspend fun refreshFingersticks(from: Instant, to: Instant) {
        val fetchedAt = Clock.System.now()
        val readings = glucoseApi.fingersticks(from, to).toCachedFingersticks(fetchedAt)
        fingerstickDao.replaceRange(from, to, readings)
    }

    override suspend fun sensorQuality(sensorId: String): SensorQuality =
        glucoseApi.sensorQuality(java.util.UUID.fromString(sensorId)).toDomain()
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

private fun SensorSessionResponse.toDomain(): SensorSession = SensorSession(
    id = id.toString(),
    startedAt = startedAt,
    endedAt = endedAt,
    expectedLifeDays = expectedLifeDays?.toDouble() ?: 15.0,
    label = label,
    vendor = vendor,
    model = model,
    excludedFromAnalytics = excludedFromAnalytics == true,
    exclusionReason = exclusionReason,
)

private fun SensorQualityResponse.toDomain(): SensorQuality = SensorQuality(
    qualityScore = qualityScore,
    confidence = when (confidence) {
        SensorQualityResponse.Confidence.NONE -> SensorQualityConfidence.None
        SensorQualityResponse.Confidence.LOW -> SensorQualityConfidence.Low
        SensorQualityResponse.Confidence.MEDIUM -> SensorQualityConfidence.Medium
        SensorQualityResponse.Confidence.HIGH -> SensorQualityConfidence.High
    },
    sensorAgeDays = sensorAgeDays?.toDouble(),
    sensorPhase = when (sensorPhase) {
        SensorQualityResponse.SensorPhase.WARMUP -> SensorPhase.Warmup
        SensorQualityResponse.SensorPhase.STABLE -> SensorPhase.Stable
        SensorQualityResponse.SensorPhase.END_OF_LIFE -> SensorPhase.EndOfLife
        null -> null
    },
    fingerstickCount = fingerstickCount,
    validCalibrationPoints = validCalibrationPoints,
    missingDataPercent = missingDataPct?.toDouble(),
    noiseScore = noiseScore.toDouble(),
    mardPercent = mardPercent?.toDouble(),
    suspectedCompressionCount = suspectedCompressionCount,
)
