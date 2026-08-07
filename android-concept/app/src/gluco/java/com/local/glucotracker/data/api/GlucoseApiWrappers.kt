package com.local.glucotracker.data.api

import com.local.glucotracker.generated.api.GlucoseApi as GeneratedGlucoseApi
import com.local.glucotracker.generated.api.NightscoutApi as GeneratedNightscoutApi
import com.local.glucotracker.generated.model.BodyStatesResponse
import com.local.glucotracker.generated.model.DayEpisodesResponse
import com.local.glucotracker.generated.model.EpisodeBreakdownResponse
import com.local.glucotracker.generated.model.FingerstickReadingResponse
import com.local.glucotracker.generated.model.GlucoseDashboardResponse
import com.local.glucotracker.generated.model.GlucoseTirDailyResponse
import com.local.glucotracker.generated.model.InsulinRecommendationRequest
import com.local.glucotracker.generated.model.InsulinRecommendationResponse
import com.local.glucotracker.generated.model.NightscoutDayStatusResponse
import com.local.glucotracker.generated.model.NightscoutInsulinEventResponse
import com.local.glucotracker.generated.model.NightscoutStatusResponse
import com.local.glucotracker.generated.model.NightscoutSyncTodayRequest
import com.local.glucotracker.generated.model.NightscoutSyncTodayResponse
import com.local.glucotracker.generated.model.SensorQualityResponse
import com.local.glucotracker.generated.model.SensorCodeResponse
import com.local.glucotracker.generated.model.SensorSessionResponse
import com.local.glucotracker.generated.model.TimelineResponse
import com.local.glucotracker.generated.model.TopUpDoseResponse
import javax.inject.Inject
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate

class GlucoseApi @Inject constructor(
    private val glucoseApi: GeneratedGlucoseApi,
) {
    suspend fun dashboard(from: Instant, to: Instant, mode: String? = null): GlucoseDashboardResponse =
        glucoseApi.getGlucoseDashboard(from = from, to = to, mode = mode).body()

    suspend fun tirDaily(period: String): GlucoseTirDailyResponse =
        glucoseApi.getGlucoseTirDaily(period = period).body()

    suspend fun episodes(from: Instant, to: Instant): DayEpisodesResponse =
        glucoseApi.getGlucoseEpisodes(from = from, to = to).body()

    /**
     * One episode taken apart.
     *
     * The range is the one the day was listed with, not a range derived here:
     * the key is resolved by re-running the same grouping, and a different span
     * can split a sitting differently and resolve to another episode or none.
     */
    suspend fun episodeBreakdown(
        key: String,
        from: Instant,
        to: Instant,
    ): EpisodeBreakdownResponse =
        glucoseApi.getGlucoseEpisodeBreakdown(key = key, from = from, to = to).body()

    suspend fun bodyStates(from: Instant, to: Instant): BodyStatesResponse =
        glucoseApi.getGlucoseBodyStates(from = from, to = to).body()

    /**
     * The follow-up arithmetic, optionally as of a past moment.
     *
     * With [at] it answers "what did this say when that bolus was given" — the
     * question a chasing dose raises and the only one the diary cannot
     * reconstruct on its own.
     */
    suspend fun topUpDose(
        at: Instant? = null,
        targetMmolL: Double? = null,
    ): TopUpDoseResponse =
        glucoseApi.getTopUpDose(
            targetMmolL = targetMmolL?.let { java.math.BigDecimal.valueOf(it) },
            at = at,
        ).body()

    suspend fun insulinRecommendation(
        mealIds: List<java.util.UUID>,
    ): InsulinRecommendationResponse =
        glucoseApi.getInsulinRecommendation(
            InsulinRecommendationRequest(mealIds = mealIds),
        ).body()

    suspend fun sensors(): List<SensorSessionResponse> =
        glucoseApi.listSensors().body()

    suspend fun sensorCodes(): List<SensorCodeResponse> =
        glucoseApi.listSensorCodes().body()

    suspend fun sensorQuality(sensorId: java.util.UUID): SensorQualityResponse =
        glucoseApi.getSensorQuality(sensorId).body()

    suspend fun fingersticks(from: Instant, to: Instant): List<FingerstickReadingResponse> =
        glucoseApi.listFingersticks(from = from, to = to).body()
}

class NightscoutApi @Inject constructor(
    private val nightscoutApi: GeneratedNightscoutApi,
) {
    suspend fun status(): NightscoutStatusResponse =
        nightscoutApi.getNightscoutStatus().body()

    suspend fun dayStatus(date: LocalDate): NightscoutDayStatusResponse =
        nightscoutApi.getNightscoutDayStatus(date).body()

    suspend fun syncToday(date: LocalDate): NightscoutSyncTodayResponse =
        nightscoutApi.syncTodayToNightscout(
            NightscoutSyncTodayRequest(date = date, confirm = true),
        ).body()

    suspend fun timeline(from: Instant, to: Instant): TimelineResponse =
        nightscoutApi.getTimeline(from = from, to = to).body()

    suspend fun insulin(from: Instant, to: Instant): List<NightscoutInsulinEventResponse> =
        nightscoutApi.getNightscoutInsulin(from = from, to = to).body()
}
