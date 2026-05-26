package com.local.glucotracker.data.repository

import androidx.room.withTransaction
import com.local.glucotracker.data.api.HistoryApi
import com.local.glucotracker.data.api.MealApi
import com.local.glucotracker.data.api.ProductsApi
import com.local.glucotracker.data.api.StatsApi
import com.local.glucotracker.data.api.TodayApi
import com.local.glucotracker.data.local.CachedDayTotalsDao
import com.local.glucotracker.data.local.CachedDayTotalsEntity
import com.local.glucotracker.data.local.CachedMealEntity
import com.local.glucotracker.data.local.CachedMealDao
import com.local.glucotracker.data.local.CachedProductDao
import com.local.glucotracker.data.local.CachedTemplateDao
import com.local.glucotracker.data.local.GlucotrackerDatabase
import com.local.glucotracker.data.local.OutboxDao
import com.local.glucotracker.data.mapper.buildDayState
import com.local.glucotracker.data.mapper.toCachedEntity
import com.local.glucotracker.data.mapper.toCachedTemplateEntity
import com.local.glucotracker.data.mapper.toDayTotals
import com.local.glucotracker.data.mapper.toDomain
import com.local.glucotracker.data.mapper.toEntity
import com.local.glucotracker.data.mapper.toJson
import com.local.glucotracker.data.mapper.toTotalsEntity
import com.local.glucotracker.data.sync.ConnectivityObserver
import com.local.glucotracker.data.sync.MealReconciler
import com.local.glucotracker.data.sync.OutboxFlushScheduler
import com.local.glucotracker.data.sync.OutboxProcessor
import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.DayState
import com.local.glucotracker.domain.model.DayTotals
import com.local.glucotracker.domain.model.HistoryDay
import com.local.glucotracker.domain.model.HistoryFilter
import com.local.glucotracker.domain.model.HistoryPage
import com.local.glucotracker.domain.model.HistoryQuery
import com.local.glucotracker.domain.model.HistoryStatusFilter
import com.local.glucotracker.domain.model.Meal
import com.local.glucotracker.domain.model.MealDraft
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.domain.model.Product
import com.local.glucotracker.domain.model.Source
import com.local.glucotracker.domain.model.StatsInsight
import com.local.glucotracker.domain.model.StatsPeriod
import com.local.glucotracker.domain.model.SyncStatus
import com.local.glucotracker.domain.model.Template
import com.local.glucotracker.domain.repository.HistoryRepository
import com.local.glucotracker.domain.repository.MealRepository
import com.local.glucotracker.domain.repository.OutboxRepository
import com.local.glucotracker.domain.repository.ProductsRepository
import com.local.glucotracker.domain.repository.StatsRepository
import com.local.glucotracker.domain.repository.SyncRepository
import com.local.glucotracker.domain.repository.TodayRepository
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
    private val statsApi: StatsApi,
    private val mealApi: MealApi,
    private val reconciler: MealReconciler,
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
                val rawMeals = mealApi.listMealsForLocalDays(
                    fromDay = date,
                    toDay = date,
                )
                reconciler.reconcileBatch(rawMeals)
                val meals = rawMeals.map { it.toCachedEntity(fetchedAt, baseUrl = baseUrl) }

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
        val balance = runCatching { statsApi.kcalBalance(date) }.getOrNull()
        if (date != currentLocalDate()) {
            return todayApi.getDay(date)?.toTotalsEntity(
                fetchedAt = fetchedAt,
                balanceResponse = balance,
            )
        }

        val today = todayApi.getToday()
        return if (today.date == date) {
            today.toTotalsEntity(fetchedAt, balance)
        } else {
            todayApi.getDay(date)?.toTotalsEntity(
                fetchedAt = fetchedAt,
                balanceResponse = balance,
            )
        }
    }
}

@Singleton
class StatsRepositoryImpl @Inject constructor(
    private val totalsDao: CachedDayTotalsDao,
    private val statsApi: StatsApi,
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

    override suspend fun getInsights(period: StatsPeriod, slot: String): List<StatsInsight> =
        statsApi.insights(period = period.apiValue, slot = slot).map { insight ->
            StatsInsight(
                id = insight.id,
                kind = insight.kind.value,
                text = insight.text,
                weight = insight.weight.value,
                supportingNumbers = insight.supportingNumbers.orEmpty(),
            )
        }

    private suspend fun fetchTotalsForDate(
        day: LocalDate,
        fetchedAt: Instant,
    ): CachedDayTotalsEntity? {
        val balance = runCatching { statsApi.kcalBalance(day) }.getOrNull()
        if (day != currentLocalDate()) {
            return todayApi.getDay(day)?.toTotalsEntity(
                fetchedAt = fetchedAt,
                balanceResponse = balance,
            )
        }

        val today = todayApi.getToday()
        return if (today.date == day) {
            today.toTotalsEntity(fetchedAt, balance)
        } else {
            todayApi.getDay(day)?.toTotalsEntity(
                fetchedAt = fetchedAt,
                balanceResponse = balance,
            )
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
    private val mealContextProvider: MealContextProvider,
    private val reconciler: MealReconciler,
    @Named("apiBaseUrl") private val baseUrl: String,
) : HistoryRepository {
    override fun observeMeals(from: Instant, to: Instant): Flow<CachedView<List<Meal>>> =
        localFirst(
            cache = { mealDao.observeBetween(from, to).map { meals -> meals.map { it.toDomain() } } },
            refresh = {
                val fetchedAt = Clock.System.now()
                val rawMeals = mealApi.listMeals(from, to)
                reconciler.reconcileBatch(rawMeals)
                mealDao.upsertAll(rawMeals.map { it.toCachedEntity(fetchedAt, baseUrl = baseUrl) })
            },
        )

    override fun observeCachedMeals(from: Instant, to: Instant): Flow<List<Meal>> =
        mealDao.observeBetween(from, to).map { meals -> meals.map { it.toDomain() } }

    override fun observeHistory(query: HistoryQuery): Flow<CachedView<HistoryPage>> {
        val from = query.fromDay.startOfDay()
        val to = query.toDay.nextDay().startOfDay()
        val ftsQuery = query.search.toFtsQuery()
        val status = query.status.localStatus()
        val withCgm = false
        val withInsulin = false
        val lowConfidence = HistoryFilter.LowConfidence in query.filters
        val photoOnly = HistoryFilter.PhotoOnly in query.filters
        val sweetOnly = HistoryFilter.Sweet in query.filters
        val breakfastOnly = HistoryFilter.Breakfast in query.filters

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
                    val domainMeals = cachedMeals
                        .map { it.toDomain() }
                        .filter { it.matchesHistoryFilters(query) }
                    buildHistoryPage(
                        query = query,
                        meals = domainMeals,
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
                            sweet = sweetOnly.takeIf { it },
                            breakfast = breakfastOnly.takeIf { it },
                            photoOnly = photoOnly.takeIf { it },
                            lowConfidence = lowConfidence.takeIf { it },
                        )
                    } else {
                        mealApi.listMealsForLocalDays(
                            fromDay = query.fromDay,
                            toDay = query.toDay,
                            q = query.search,
                            limit = HistoryNetworkLimit,
                            status = query.status.remoteStatus(),
                            sweet = sweetOnly.takeIf { it },
                            breakfast = breakfastOnly.takeIf { it },
                            photoOnly = photoOnly.takeIf { it },
                            lowConfidence = lowConfidence.takeIf { it },
                        )
                    }
                    reconciler.reconcileBatch(mealResponses)
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
                        mealContextProvider.contextByMealId(from, to)
                    }.getOrDefault(emptyMap())
                    val remoteMeals = mealResponses.map { meal ->
                        val context = contextByMealId[meal.id.toString()] ?: MealContextFlags()
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
                        ) && meal.toDomain().matchesHistoryFilters(query)
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

    override suspend fun searchLocal(query: String, limit: Int, prefix: BrandPrefix?): List<Product> {
        val rows = query.toFtsQuery()
            ?.let { productDao.searchFts(it, limit * 3) }
            ?: productDao.top(limit * 3)
        return rows
            .map { it.toDomain() }
            .filter { product -> product.matches(prefix) }
            .take(limit)
    }

    override suspend fun searchTemplatesLocal(query: String, limit: Int): List<Template> {
        val fts = query.toFtsQuery()
        return (fts?.let { templateDao.searchFts(it, limit) } ?: templateDao.top(limit))
            .map { it.toDomain() }
    }

    override suspend fun refreshProducts() {
        val fetchedAt = Clock.System.now()
        productDao.replaceAll(productsApi.products().map { it.toCachedEntity(fetchedAt) })
        templateDao.replaceAll(productsApi.templates().map { it.toCachedTemplateEntity(fetchedAt) })
    }
}

private fun Product.matches(prefix: BrandPrefix?): Boolean =
    when (prefix) {
        null -> true
        BrandPrefix.Bk -> brandSlug == "bk" || brandSlug == "burgerking"
        BrandPrefix.Mc -> brandSlug == "mc" || brandSlug == "mcdonalds" || brandSlug == "macdonalds"
        BrandPrefix.Kfc -> brandSlug == "kfc"
        BrandPrefix.Restaurant -> kind.equals("restaurant", ignoreCase = true)
        BrandPrefix.Product -> !kind.equals("restaurant", ignoreCase = true)
        BrandPrefix.Template -> false
    }

private val Product.brandSlug: String
    get() = brand.orEmpty()
        .lowercase()
        .filter { it.isLetterOrDigit() }

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

    override fun observeActiveCount(): Flow<Int> =
        outboxDao.observeQueueDepth()

    override suspend fun enqueue(kind: OutboxKind): OutboxItem {
        val now = Clock.System.now()
        val item = OutboxItem(
            id = UUID.randomUUID().toString(),
            kind = kind,
            state = OutboxState.Queued,
            createdAt = now,
            lastAttemptAt = null,
            nextAttemptAt = null,
            attempts = 0,
            serverIdOnSuccess = null,
            errorMessage = null,
            enteredCurrentStateAt = now,
            lastErrorCode = null,
            lastErrorMessage = null,
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
                foregroundPhotoUpload = item.kind is OutboxKind.CapturedMeal,
            )
        }
    }

    override suspend fun remove(id: String) {
        database.withTransaction {
            outboxDao.deleteById(id)
        }
    }

    override suspend fun markUploading(id: String) {
        val now = Clock.System.now()
        database.withTransaction {
            outboxDao.updateState(
                id = id,
                state = OutboxState.Uploading,
                lastAttemptAt = now,
                nextAttemptAt = null,
                attemptDelta = 1,
                errorMessage = null,
                stateChangedAt = now,
                lastErrorCode = null,
                lastErrorMessage = null,
            )
        }
    }

    override suspend fun markConfirmed(id: String, serverIdOnSuccess: String?) {
        database.withTransaction {
            outboxDao.markConfirmed(id, serverIdOnSuccess, Clock.System.now())
        }
    }

    override suspend fun markStuck(id: String, errorCode: String, errorMessage: String?) {
        val now = Clock.System.now()
        database.withTransaction {
            outboxDao.updateState(
                id = id,
                state = OutboxState.Stuck,
                lastAttemptAt = now,
                nextAttemptAt = null,
                attemptDelta = 0,
                errorMessage = errorMessage,
                stateChangedAt = now,
                lastErrorCode = errorCode,
                lastErrorMessage = errorMessage,
            )
        }
    }

    override suspend fun requeue(
        id: String,
        nextAttemptAt: Instant?,
        errorCode: String?,
        errorMessage: String?,
    ) {
        database.withTransaction {
            outboxDao.markQueuedForRetry(
                id = id,
                nextAttemptAt = nextAttemptAt,
                errorMessage = errorMessage,
                queuedAt = Clock.System.now(),
                lastErrorCode = errorCode,
                lastErrorMessage = errorMessage,
            )
        }
    }

    override suspend fun retry(id: String) {
        database.withTransaction {
            outboxDao.resetForManualRetry(id, Clock.System.now())
        }
        flushScheduler.enqueueImmediate()
    }

    override suspend fun revertNetworkStuckItems(): Int {
        val recoverableErrorCodes = listOf(
            "server_unreachable",
            "no_network",
            "connect_timeout",
            "server_error",
            "unknown",
        )
        return database.withTransaction {
            outboxDao.revertNetworkStuck(recoverableErrorCodes, Clock.System.now())
        }
    }
}

private const val HistoryNetworkLimit = 100
private const val LowConfidenceThreshold = 0.8

internal fun buildHistoryPage(
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
        if (dayMeals.isEmpty() && (dayTotals == null || dayTotals.mealCount <= 0)) {
            null
        } else {
            HistoryDay(
                date = date,
                totals = dayTotals,
                meals = dayMeals,
                dailyAverageKcalForPeriod = dayTotals?.dailyAverageKcalForPeriod,
                photoCount = dayTotals?.photoCount
                    ?: dayMeals.count { meal -> meal.source == "photo" || meal.thumbnailUrl != null },
            )
        }
    }.toList()
    return HistoryPage(
        days = days,
        totalDays = totals.count { it.mealCount > 0 }.coerceAtLeast(days.size),
        totalRecords = totals.sumOf { it.mealCount }.coerceAtLeast(meals.size),
    )
}

private fun Meal.matchesHistoryFilters(query: HistoryQuery): Boolean =
    (!query.filters.contains(HistoryFilter.Sweet) || "sweet" in tags || hasSweetText()) &&
        (!query.filters.contains(HistoryFilter.Breakfast) || eatenAt.hourInLocalTime() in 6..10)

private fun Meal.hasSweetText(): Boolean {
    val haystack = (listOfNotNull(title) + items.map { it.name }).joinToString(" ").lowercase()
    return listOf(
        "шоколад",
        "печенье",
        "торт",
        "конфет",
        "маффин",
        "кекс",
        "десерт",
        "слад",
        "cookie",
        "chocolate",
        "cake",
        "candy",
        "muffin",
        "dessert",
    ).any { keyword -> keyword in haystack }
}

private fun Instant.hourInLocalTime(): Int =
    toLocalDateTime(TimeZone.currentSystemDefault()).hour

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
    private val flushScheduler: OutboxFlushScheduler,
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
        outboxDao.clearQueuedBackoff()
        val result = outboxProcessor.processOnce()
        if (result.shouldRetry) {
            flushScheduler.enqueueImmediate()
        }
    }
}

private fun currentLocalDate(): LocalDate =
    Clock.System.now().toLocalDateTime(TimeZone.currentSystemDefault()).date

private fun LocalDate.nextDay(): LocalDate = plus(DatePeriod(days = 1))

private fun LocalDate.startOfDay(): Instant =
    atStartOfDayIn(TimeZone.currentSystemDefault())

internal fun String.toFtsQuery(): String? {
    val tokens = trim()
        .split(Regex("\\s+"))
        .map { token -> token.filter { it.isLetterOrDigit() || it == '_' } }
        .map { it.lowercase() }
        .filter { it.isNotBlank() && it !in SearchStopWords }
    if (tokens.isEmpty()) return null
    return tokens.joinToString(separator = " ") { "$it*" }
}

private val SearchStopWords = setOf(
    "с",
    "со",
    "и",
    "в",
    "во",
    "на",
    "из",
    "к",
    "ко",
    "по",
    "для",
)
