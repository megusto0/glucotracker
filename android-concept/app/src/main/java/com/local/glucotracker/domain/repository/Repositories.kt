package com.local.glucotracker.domain.repository

import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.DayTotals
import com.local.glucotracker.domain.model.DayState
import com.local.glucotracker.domain.model.HistoryPage
import com.local.glucotracker.domain.model.HistoryQuery
import com.local.glucotracker.domain.model.Meal
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.Product
import com.local.glucotracker.domain.model.StatsInsight
import com.local.glucotracker.domain.model.StatsOverview
import com.local.glucotracker.domain.model.StatsPeriod
import com.local.glucotracker.domain.model.SyncStatus
import com.local.glucotracker.domain.model.Template
import com.local.glucotracker.data.repository.BrandPrefix
import kotlinx.coroutines.flow.Flow
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate

interface TodayRepository {
    fun observeDay(date: LocalDate): Flow<CachedView<DayState>>
}

interface StatsRepository {
    fun observeDayTotals(day: LocalDate): Flow<CachedView<DayTotals>>
    suspend fun getInsights(period: StatsPeriod, slot: String): List<StatsInsight>
    suspend fun getOverview(period: StatsPeriod): StatsOverview
}

interface HistoryRepository {
    fun observeMeals(from: Instant, to: Instant): Flow<CachedView<List<Meal>>>
    fun observeCachedMeals(from: Instant, to: Instant): Flow<List<Meal>>
    fun observeHistory(query: HistoryQuery): Flow<CachedView<HistoryPage>>
}

interface ProductsRepository {
    fun observeProducts(): Flow<CachedView<List<Product>>>
    fun observeTemplatesLocal(): Flow<List<Template>>
    suspend fun searchLocal(query: String, limit: Int = 20, prefix: BrandPrefix? = null): List<Product>
    suspend fun searchTemplatesLocal(query: String, limit: Int = 20): List<Template>
    suspend fun refreshProducts()
}

interface MealRepository {
    fun observeMeal(id: String): Flow<CachedView<Meal>>
    suspend fun retryPhotoEstimate(id: String)
}

interface OutboxRepository {
    fun observe(): Flow<List<OutboxItem>>
    fun observeOutbox(): Flow<List<OutboxItem>> = observe()
    fun observeActiveCount(): Flow<Int>
    suspend fun enqueue(kind: OutboxKind): OutboxItem
    suspend fun enqueue(item: OutboxItem)
    suspend fun remove(id: String)
    suspend fun markUploading(id: String)
    suspend fun markPhotoEstimating(id: String, serverMealId: String)
    suspend fun markConfirmed(id: String, serverIdOnSuccess: String?)
    suspend fun markStuck(id: String, errorCode: String, errorMessage: String?)
    suspend fun requeue(id: String, nextAttemptAt: kotlinx.datetime.Instant?, errorCode: String?, errorMessage: String?)
    suspend fun retry(id: String)
    suspend fun revertNetworkStuckItems(): Int
}

interface SyncRepository {
    fun observeStatus(): Flow<SyncStatus>
    suspend fun requestSync()
}
