package com.local.glucotracker.domain.repository

import com.local.glucotracker.domain.model.ActiveGlucoseContext
import com.local.glucotracker.domain.model.BodySpan
import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.FingerstickReading
import com.local.glucotracker.domain.model.GlucoseEpisodeMark
import com.local.glucotracker.domain.model.GlucoseRange
import com.local.glucotracker.domain.model.GlucoseTirDay
import com.local.glucotracker.domain.model.InsulinEvent
import com.local.glucotracker.domain.model.NightscoutDayStatus
import com.local.glucotracker.domain.model.NightscoutStatus
import com.local.glucotracker.domain.model.SensorQuality
import com.local.glucotracker.domain.model.SensorCode
import com.local.glucotracker.domain.model.SensorSession
import kotlinx.coroutines.flow.Flow
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate

interface GlucoseRepository {
    fun observeRange(from: Instant, to: Instant): Flow<CachedView<GlucoseRange>>
    fun observeCachedRange(from: Instant, to: Instant): Flow<CachedView<GlucoseRange>>
}

interface NightscoutRepository {
    suspend fun status(): NightscoutStatus
    suspend fun dayStatus(date: LocalDate): NightscoutDayStatus
    suspend fun syncToday(date: LocalDate): NightscoutDayStatus
}

interface SensorRepository {
    fun observeSensors(): Flow<CachedView<List<SensorSession>>>
    fun observeSensorCodes(): Flow<CachedView<List<SensorCode>>>
    fun observeFingersticks(from: Instant, to: Instant): Flow<CachedView<List<FingerstickReading>>>
    suspend fun refreshSensors()
    suspend fun refreshSensorCodes()
    suspend fun refreshFingersticks(from: Instant, to: Instant)
    suspend fun sensorQuality(sensorId: String): SensorQuality
}

/**
 * What happened around the glucose curve: insulin, sleep and effort, and the
 * server's current IOB/COB and day TIR. Insulin is local-first (Room); the rest
 * is read from the server on refresh and simply absent offline.
 */
interface GlucoseContextRepository {
    fun observeInsulin(from: Instant, to: Instant): Flow<List<InsulinEvent>>
    suspend fun refreshInsulin(from: Instant, to: Instant)
    suspend fun bodySpans(from: Instant, to: Instant): List<BodySpan>
    suspend fun episodes(from: Instant, to: Instant): List<GlucoseEpisodeMark>
    suspend fun activeContext(now: Instant): ActiveGlucoseContext?
    suspend fun tirForDay(date: LocalDate): GlucoseTirDay?
}
