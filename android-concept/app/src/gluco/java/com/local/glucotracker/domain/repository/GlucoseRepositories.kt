package com.local.glucotracker.domain.repository

import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.GlucoseRange
import com.local.glucotracker.domain.model.NightscoutDayStatus
import com.local.glucotracker.domain.model.NightscoutStatus
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
