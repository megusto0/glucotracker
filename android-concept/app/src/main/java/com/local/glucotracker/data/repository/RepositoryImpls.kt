package com.local.glucotracker.data.repository

import androidx.room.withTransaction
import com.local.glucotracker.data.api.GlucoseApi
import com.local.glucotracker.data.api.HistoryApi
import com.local.glucotracker.data.api.MealApi
import com.local.glucotracker.data.api.NightscoutApi
import com.local.glucotracker.data.api.ProductsApi
import com.local.glucotracker.data.api.StatsApi
import com.local.glucotracker.data.api.TodayApi
import com.local.glucotracker.data.local.CachedDayTotalsDao
import com.local.glucotracker.data.local.CachedDayTotalsEntity
import com.local.glucotracker.data.local.CachedMealEntity
import com.local.glucotracker.data.local.CachedGlucoseDao
import com.local.glucotracker.data.local.CachedMealDao
import com.local.glucotracker.data.local.CachedProductDao
import com.local.glucotracker.data.local.CachedTemplateDao
import com.local.glucotracker.data.local.GlucotrackerDatabase
import com.local.glucotracker.data.local.OutboxDao
import com.local.glucotracker.data.mapper.buildDayState
import com.local.glucotracker.data.mapper.toCachedEntities
import com.local.glucotracker.data.mapper.toCachedEntity
import com.local.glucotracker.data.mapper.toCachedTemplateEntity
import com.local.glucotracker.data.mapper.toDayTotals
import com.local.glucotracker.data.mapper.toDomain
import com.local.glucotracker.data.mapper.toEntity
import com.local.glucotracker.data.mapper.toJson
import com.local.glucotracker.data.mapper.toRange
import com.local.glucotracker.data.mapper.toTotalsEntity
import com.local.glucotracker.data.sync.ConnectivityObserver
import com.local.glucotracker.data.sync.OutboxFlushScheduler
import com.local.glucotracker.data.sync.OutboxProcessor
import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.DayState
import com.local.glucotracker.domain.model.DayTotals
import com.local.glucotracker.domain.model.GlucoseRange
import com.local.glucotracker.domain.model.HistoryDay
import com.local.glucotracker.domain.model.HistoryFilter
import com.local.glucotracker.domain.model.HistoryPage
import com.local.glucotracker.domain.model.HistoryQuery
import com.local.glucotracker.domain.model.HistoryStatusFilter
import com.local.glucotracker.domain.model.Meal
import com.local.glucotracker.domain.model.MealDraft
import com.local.glucotracker.domain.model.NightscoutConnectionState
import com.local.glucotracker.domain.model.NightscoutDayStatus
import com.local.glucotracker.domain.model.NightscoutStatus
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.domain.model.Product
import com.local.glucotracker.domain.model.Source
import com.local.glucotracker.domain.model.SyncStatus
import com.local.glucotracker.domain.model.Template
import com.local.glucotracker.domain.repository.GlucoseRepository
import com.local.glucotracker.domain.repository.HistoryRepository
import com.local.glucotracker.domain.repository.MealRepository
import com.local.glucotracker.domain.repository.NightscoutRepository
import com.local.glucotracker.domain.repository.OutboxRepository
import com.local.glucotracker.domain.repository.ProductsRepository
import com.local.glucotracker.domain.repository.StatsRepository
import com.local.glucotracker.domain.repository.SyncRepository
import com.local.glucotracker.domain.repository.TodayRepository
import com.local.glucotracker.generated.model.FoodEpisodeResponse
import com.local.glucotracker.generated.model.MealResponse
import com.local.glucotracker.generated.model.MealStatus
import java.util.UUID
import javax.inject.Inject
import javax.inject.Named
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.datetime.Clock
import kotlinx.datetime.DatePeriod
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.atStartOfDayIn
import kotlinx.datetime.plus
import kotlinx.datetime.toLocalDateTime

@Singleton
class TodayRepositoryImpl @Inject constructor(
    private val database: GlucotrackerDatabase,
    private val totalsDao: CachedDayTotalsDao,
    private val mealDao: CachedMealDao,
    private val todayApi: TodayApi,
    private val mealApi: MealApi,
    @Named("apiBaseUrl") private val baseUrl: String,
) : TodayRepository {
    override fun observeDay(date: LocalDate): Flow<CachedView<DayState>> =
        localFirst(
            cache = {
                combine(
                    totalsDao.observeDay(date),
                    mealDao.observeForDay(date),
                ) { total, meals ->
                    total?.let { buildDayState(it, meals) }
                }
            },
            refresh = {
                val fetchedAt = Clock.System.now()
                val total = fetchTotalsForDate(date, fetchedAt)
                val meals = mealApi.listMealsForLocalDays(
                    fromDay = date,
                    toDay = date,
                ).map { it.toCachedEntity(fetchedAt, baseUrl = baseUrl) }

                database.withTransaction {
                    if (total != null) totalsDao.upsert(total)
                    mealDao.replaceForDay(date, meals)
                }
            },
        )

    private suspend fun fetchTotalsForDate(
        date: LocalDate,
        fetchedAt: Instant,
    ): CachedDayTotalsEntity? {
        if (date != currentLocalDate()) {
            return todayApi.getDay(date)?.toTotalsEntity(fetchedAt)
        }

        val today = todayApi.getToday()
        return if (today.date == date) {
            today.toTotalsEntity(fetchedAt)
        } else {
            todayApi.getDay(date)?.toTotalsEntity(fetchedAt)
        }
    }
}

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
class StatsRepositoryImpl @Inject constructor(
    private val totalsDao: CachedDayTotalsDao,
    private val todayApi: TodayApi,
) : StatsRepository {
    override fun observeDayTotals(day: LocalDate): Flow<CachedView<DayTotals>> =
        localFirst(
            cache = { totalsDao.observeDay(day).map { it?.toDayTotals() } },
            refresh = {
                val fetchedAt = Clock.System.now()
                val total = fetchTotalsForDate(day, fetchedAt)
                if (total != null) totalsDao.upsert(total)
            },
        )

    private suspend fun fetchTotalsForDate(
        day: LocalDate,
        fetchedAt: Instant,
    ): CachedDayTotalsEntity? {
        if (day != currentLocalDate()) {
            return todayApi.getDay(day)?.toTotalsEntity(fetchedAt)
        }

        val today = todayApi.getToday()
        return if (today.date == day) {
            today.toTotalsEntity(fetchedAt)
        } else {
            todayApi.getDay(day)?.toTotalsEntity(fetchedAt)
        }
    }
}

@Singleton
class HistoryRepositoryImpl @Inject constructor(
    private val database: GlucotrackerDatabase,
    private val mealDao: CachedMealDao,
    private val totalsDao: CachedDayTotalsDao,
    private val mealApi: MealApi,
    private val historyApi: HistoryApi,
    private val connectivityObserver: ConnectivityObserver,
    @Named("apiBaseUrl") private val baseUrl: String,
) : HistoryRepository {
    override fun observeMeals(from: Instant, to: Instant): Flow<CachedView<List<Meal>>> =
        localFirst(
            cache = { mealDao.observeBetween(from, to).map { meals -> meals.map { it.toDomain() } } },
            refresh = {
                val fetchedAt = Clock.System.now()
                mealDao.upsertAll(mealApi.listMeals(from, to).map { it.toCachedEntity(fetchedAt, baseUrl = baseUrl) })
            },
        )

    override fun observeCachedMeals(from: Instant, to: Instant): Flow<List<Meal>> =
        mealDao.observeBetween(from, to).map { meals -> meals.map { it.toDomain() } }

    override fun observeHistory(query: HistoryQuery): Flow<CachedView<HistoryPage>> {
        val from = query.fromDay.startOfDay()
        val to = query.toDay.nextDay().startOfDay()
        val ftsQuery = query.search.toFtsQuery()
        val status = query.status.localStatus()
        val withCgm = HistoryFilter.WithCgm in query.filters
        val withInsulin = HistoryFilter.WithInsulin in query.filters
        val lowConfidence = HistoryFilter.LowConfidence in query.filters
        val photoOnly = HistoryFilter.PhotoOnly in query.filters

        return localFirst(
            cache = {
                val meals = if (ftsQuery == null) {
                    mealDao.observeHistoryRange(
                        from = from,
                        to = to,
                        withCgm = withCgm,
                        withInsulin = withInsulin,
                        lowConfidence = lowConfidence,
                        photoOnly = photoOnly,
                        status = status,
                        lowConfidenceThreshold = LowConfidenceThreshold,
                    )
                } else {
                    mealDao.observeHistorySearch(
                        from = from,
                        to = to,
                        query = ftsQuery,
                        withCgm = withCgm,
                        withInsulin = withInsulin,
                        lowConfidence = lowConfidence,
                        photoOnly = photoOnly,
                        status = status,
                        lowConfidenceThreshold = LowConfidenceThreshold,
                    )
                }
                combine(
                    meals,
                    totalsDao.observeBetween(query.fromDay, query.toDay),
                ) { cachedMeals, totals ->
                    buildHistoryPage(
                        query = query,
                        meals = cachedMeals.map { it.toDomain() },
                        totals = totals.map { it.toDayTotals() },
                    )
                }
            },
            refresh = {
                if (!connectivityObserver.currentStatus().isConnected) return@localFirst

                withContext(Dispatchers.IO) {
                    val fetchedAt = Clock.System.now()
                    val mealResponses = if (query.search.isBlank()) {
                        mealApi.listMealsForLocalDays(
                            fromDay = query.fromDay,
                            toDay = query.toDay,
                            limit = HistoryNetworkLimit,
                            status = query.status.remoteStatus(),
                        )
                    } else {
                        mealApi.listMealsForLocalDays(
                            fromDay = query.fromDay,
                            toDay = query.toDay,
                            q = query.search,
                            limit = HistoryNetworkLimit,
                            status = query.status.remoteStatus(),
                        )
                    }
                    val balances = runCatching {
                        historyApi.balanceRange(query.fromDay, query.toDay)
                    }.getOrNull()
                        ?.days
                        .orEmpty()
                        .associateBy { it.date }
                    val totals = runCatching {
                        historyApi.dashboardRange(query.fromDay, query.toDay)
                    }.getOrNull()
                        ?.days
                        .orEmpty()
                        .map { day -> day.toTotalsEntity(fetchedAt, balances[day.date]) }
                    val contextByMealId = runCatching {
                        historyApi.timeline(from, to)
                    }.getOrNull()
                        ?.episodes
                        .orEmpty()
                        .toMealContext()
                    val remoteMeals = mealResponses.map { meal ->
                        val context = contextByMealId[meal.id.toString()] ?: MealContext()
                        meal.toCachedEntity(
                            fetchedAt = fetchedAt,
                            hasCgm = context.hasCgm,
                            hasInsulin = context.hasInsulin,
                            baseUrl = baseUrl,
                        )
                    }.filter { meal ->
                        meal.matchesFilters(
                            withCgm = withCgm,
                            withInsulin = withInsulin,
                            lowConfidence = lowConfidence,
                            photoOnly = photoOnly,
                        )
                    }

                    database.withTransaction {
                        totalsDao.upsertAll(totals)
                        mealDao.upsertAll(remoteMeals)
                    }
                }
            },
        )
    }
}

@Singleton
class ProductsRepositoryImpl @Inject constructor(
    private val productDao: CachedProductDao,
    private val templateDao: CachedTemplateDao,
    private val productsApi: ProductsApi,
) : ProductsRepository {
    override fun observeProducts(): Flow<CachedView<List<Product>>> =
        localFirst(
            cache = { productDao.observeAll().map { products -> products.map { it.toDomain() } } },
            refresh = {
                val fetchedAt = Clock.System.now()
                productDao.replaceAll(productsApi.products().map { it.toCachedEntity(fetchedAt) })
                templateDao.replaceAll(productsApi.templates().map { it.toCachedTemplateEntity(fetchedAt) })
            },
        )

    override fun observeTemplatesLocal(): Flow<List<Template>> =
        templateDao.observeAll().map { templates -> templates.map { it.toDomain() } }

    override suspend fun searchLocal(query: String, limit: Int): List<Product> {
        val fts = query.toFtsQuery() ?: return emptyList()
        return productDao.searchFts(fts, limit).map { it.toDomain() }
    }

    override suspend fun searchTemplatesLocal(query: String, limit: Int): List<Template> {
        val fts = query.toFtsQuery() ?: return emptyList()
        return templateDao.searchFts(fts, limit).map { it.toDomain() }
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
class MealRepositoryImpl @Inject constructor(
    private val mealDao: CachedMealDao,
    private val mealApi: MealApi,
    @Named("apiBaseUrl") private val baseUrl: String,
) : MealRepository {
    override fun observeMeal(id: String): Flow<CachedView<Meal>> =
        localFirst(
            cache = { mealDao.observeById(id).map { it?.toDomain() } },
            refresh = {
                val fetchedAt = Clock.System.now()
                mealDao.upsertAll(listOf(mealApi.getMeal(UUID.fromString(id)).toCachedEntity(fetchedAt, baseUrl = baseUrl)))
            },
        )
}

@Singleton
class OutboxRepositoryImpl @Inject constructor(
    private val database: GlucotrackerDatabase,
    private val outboxDao: OutboxDao,
    private val flushScheduler: OutboxFlushScheduler,
) : OutboxRepository {
    override fun observe(): Flow<List<OutboxItem>> =
        outboxDao.observeAll().map { items -> items.map { it.toDomain() } }

    override suspend fun enqueue(kind: OutboxKind): OutboxItem {
        val now = Clock.System.now()
        val item = OutboxItem(
            id = UUID.randomUUID().toString(),
            kind = kind,
            state = OutboxState.Queued,
            createdAt = now,
            lastAttemptAt = null,
            attempts = 0,
            serverIdOnSuccess = null,
            errorMessage = null,
        )
        enqueue(item)
        return item
    }

    override suspend fun enqueue(item: OutboxItem) {
        database.withTransaction {
            outboxDao.upsert(item.toEntity())
        }
        if (item.state == OutboxState.Queued) {
            flushScheduler.enqueueImmediate(
                foregroundPhotoUpload = item.kind is OutboxKind.PhotoEstimateRequest,
            )
        }
    }

    override suspend fun remove(id: String) {
        database.withTransaction {
            outboxDao.deleteById(id)
        }
    }

    override suspend fun markSending(id: String) {
        database.withTransaction {
            outboxDao.updateState(
                id = id,
                state = OutboxState.Sending,
                lastAttemptAt = Clock.System.now(),
                attemptDelta = 1,
                errorMessage = null,
            )
        }
    }

    override suspend fun markSent(id: String, serverIdOnSuccess: String?) {
        database.withTransaction {
            outboxDao.markSent(id, serverIdOnSuccess, Clock.System.now())
        }
    }

    override suspend fun markConflict(id: String, errorMessage: String?) {
        database.withTransaction {
            outboxDao.updateState(
                id = id,
                state = OutboxState.Conflict,
                lastAttemptAt = Clock.System.now(),
                attemptDelta = 0,
                errorMessage = errorMessage,
            )
        }
    }

    override suspend fun markEstimating(id: String) {
        database.withTransaction {
            outboxDao.updateState(
                id = id,
                state = OutboxState.Estimating,
                lastAttemptAt = Clock.System.now(),
                attemptDelta = 1,
                errorMessage = null,
            )
        }
    }

    override suspend fun markEstimateReady(id: String, draft: MealDraft) {
        database.withTransaction {
            outboxDao.markEstimateReady(
                id = id,
                draftJson = draft.toJson(),
                serverIdOnSuccess = draft.id,
                readyAt = Clock.System.now(),
            )
        }
    }
}

private const val HistoryNetworkLimit = 100
private const val LowConfidenceThreshold = 0.8

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

private data class MealContext(
    val hasCgm: Boolean = false,
    val hasInsulin: Boolean = false,
)

private fun buildHistoryPage(
    query: HistoryQuery,
    meals: List<Meal>,
    totals: List<DayTotals>,
): HistoryPage {
    val totalsByDate = totals.associateBy { it.date }
    val mealsByDate = meals.groupBy { it.eatenAtDay }
    val days = generateSequence(query.toDay) { date ->
        if (date == query.fromDay) null else date.plus(DatePeriod(days = -1))
    }.mapNotNull { date ->
        val dayMeals = mealsByDate[date].orEmpty()
        val dayTotals = totalsByDate[date]
        if (dayMeals.isEmpty() && dayTotals == null) {
            null
        } else {
            HistoryDay(
                date = date,
                totals = dayTotals,
                meals = dayMeals,
            )
        }
    }.toList()
    return HistoryPage(days = days)
}

private fun List<FoodEpisodeResponse>.toMealContext(): Map<String, MealContext> =
    flatMap { episode ->
        val context = MealContext(
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

private fun CachedMealEntity.matchesFilters(
    withCgm: Boolean,
    withInsulin: Boolean,
    lowConfidence: Boolean,
    photoOnly: Boolean,
): Boolean =
    (!withCgm || hasCgm) &&
        (!withInsulin || hasInsulin) &&
        (!lowConfidence || (confidence != null && confidence < LowConfidenceThreshold)) &&
        (!photoOnly || source == "photo" || thumbnailUrl != null)

private fun HistoryStatusFilter.localStatus(): String? =
    when (this) {
        HistoryStatusFilter.Active,
        HistoryStatusFilter.Accepted,
        -> "accepted"
        HistoryStatusFilter.Drafts -> "draft"
        HistoryStatusFilter.All -> null
    }

private fun HistoryStatusFilter.remoteStatus(): MealStatus? =
    when (this) {
        HistoryStatusFilter.Active,
        HistoryStatusFilter.Accepted,
        -> MealStatus.ACCEPTED
        HistoryStatusFilter.Drafts -> MealStatus.DRAFT
        HistoryStatusFilter.All -> null
    }

@Singleton
class SyncRepositoryImpl @Inject constructor(
    private val outboxDao: OutboxDao,
    private val outboxProcessor: OutboxProcessor,
) : SyncRepository {
    override fun observeStatus(): Flow<SyncStatus> =
        outboxDao.observeQueueDepth().map { depth ->
            SyncStatus(
                queueDepth = depth,
                lastSyncAt = null,
                isSyncing = false,
            )
        }

    override suspend fun requestSync() {
        outboxProcessor.processOnce()
    }
}

private fun currentLocalDate(): LocalDate =
    Clock.System.now().toLocalDateTime(TimeZone.currentSystemDefault()).date

private fun LocalDate.nextDay(): LocalDate = plus(DatePeriod(days = 1))

private fun LocalDate.startOfDay(): Instant =
    atStartOfDayIn(TimeZone.currentSystemDefault())

private fun String.toFtsQuery(): String? {
    val tokens = trim()
        .split(Regex("\\s+"))
        .map { token -> token.filter { it.isLetterOrDigit() || it == '_' } }
        .filter { it.isNotBlank() }
    if (tokens.isEmpty()) return null
    return tokens.joinToString(separator = " ") { "$it*" }
}
