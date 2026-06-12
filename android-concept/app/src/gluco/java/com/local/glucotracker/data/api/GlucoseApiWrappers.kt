package com.local.glucotracker.data.api

import com.local.glucotracker.generated.api.GlucoseApi as GeneratedGlucoseApi
import com.local.glucotracker.generated.api.NightscoutApi as GeneratedNightscoutApi
import com.local.glucotracker.generated.model.DayEpisodesResponse
import com.local.glucotracker.generated.model.GlucoseDashboardResponse
import com.local.glucotracker.generated.model.GlucoseTirDailyResponse
import com.local.glucotracker.generated.model.NightscoutDayStatusResponse
import com.local.glucotracker.generated.model.NightscoutInsulinEventResponse
import com.local.glucotracker.generated.model.NightscoutStatusResponse
import com.local.glucotracker.generated.model.NightscoutSyncTodayRequest
import com.local.glucotracker.generated.model.NightscoutSyncTodayResponse
import com.local.glucotracker.generated.model.TimelineResponse
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
