package com.local.glucotracker.domain.repository

import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.DayTotals
import com.local.glucotracker.domain.model.DayState
import com.local.glucotracker.domain.model.GlucoseRange
import com.local.glucotracker.domain.model.HistoryPage
import com.local.glucotracker.domain.model.HistoryQuery
import com.local.glucotracker.domain.model.Meal
import com.local.glucotracker.domain.model.MealDraft
import com.local.glucotracker.domain.model.NightscoutDayStatus
import com.local.glucotracker.domain.model.NightscoutStatus
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.Product
import com.local.glucotracker.domain.model.SyncStatus
import com.local.glucotracker.domain.model.Template
import kotlinx.coroutines.flow.Flow
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate

interface TodayRepository {
    fun observeDay(date: LocalDate): Flow<CachedView<DayState>>
}

interface GlucoseRepository {
    fun observeRange(from: Instant, to: Instant): Flow<CachedView<GlucoseRange>>
    fun observeCachedRange(from: Instant, to: Instant): Flow<CachedView<GlucoseRange>>
}

interface StatsRepository {
    fun observeDayTotals(day: LocalDate): Flow<CachedView<DayTotals>>
}

interface HistoryRepository {
    fun observeMeals(from: Instant, to: Instant): Flow<CachedView<List<Meal>>>
    fun observeCachedMeals(from: Instant, to: Instant): Flow<List<Meal>>
    fun observeHistory(query: HistoryQuery): Flow<CachedView<HistoryPage>>
}

interface ProductsRepository {
    fun observeProducts(): Flow<CachedView<List<Product>>>
    fun observeTemplatesLocal(): Flow<List<Template>>
    suspend fun searchLocal(query: String, limit: Int = 20): List<Product>
    suspend fun searchTemplatesLocal(query: String, limit: Int = 20): List<Template>
}

interface MealRepository {
    fun observeMeal(id: String): Flow<CachedView<Meal>>
}

interface OutboxRepository {
    fun observe(): Flow<List<OutboxItem>>
    fun observeOutbox(): Flow<List<OutboxItem>> = observe()
    suspend fun enqueue(kind: OutboxKind): OutboxItem
    suspend fun enqueue(item: OutboxItem)
    suspend fun remove(id: String)
    suspend fun markSending(id: String)
    suspend fun markSent(id: String, serverIdOnSuccess: String?)
    suspend fun markConflict(id: String, errorMessage: String?)
    suspend fun markEstimating(id: String)
    suspend fun markEstimateReady(id: String, draft: MealDraft)
}

interface SyncRepository {
    fun observeStatus(): Flow<SyncStatus>
    suspend fun requestSync()
}

interface NightscoutRepository {
    suspend fun status(): NightscoutStatus
    suspend fun dayStatus(date: LocalDate): NightscoutDayStatus
    suspend fun syncToday(date: LocalDate): NightscoutDayStatus
}
