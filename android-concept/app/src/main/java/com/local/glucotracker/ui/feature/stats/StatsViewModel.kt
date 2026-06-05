package com.local.glucotracker.ui.feature.stats

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.data.settings.SettingsStore
import com.local.glucotracker.data.sync.ConnectivityObserver
import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.DayTotals
import com.local.glucotracker.domain.model.Meal
import com.local.glucotracker.domain.model.StatsInsight
import com.local.glucotracker.domain.model.StatsOverview
import com.local.glucotracker.domain.model.StatsOverviewAnomaly
import com.local.glucotracker.domain.model.StatsOverviewHourlyBucket
import com.local.glucotracker.domain.model.StatsOverviewTopProduct
import com.local.glucotracker.domain.model.StatsPeriod
import com.local.glucotracker.domain.repository.HistoryRepository
import com.local.glucotracker.domain.repository.StatsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlin.math.abs
import kotlin.math.sqrt
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.stateIn
import kotlinx.datetime.Clock
import kotlinx.datetime.DatePeriod
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.atStartOfDayIn
import kotlinx.datetime.minus
import kotlinx.datetime.plus
import kotlinx.datetime.toLocalDateTime

sealed interface StatsState {
    data object Loading : StatsState
    data class Sparse(
        val date: LocalDate,
        val trackedDays: Int,
        val period: StatsPeriod = StatsPeriod.Week,
    ) : StatsState
    data class Charts(
        val date: LocalDate,
        val days: List<StatsDay>,
        val staleCacheAt: Instant?,
        val period: StatsPeriod = StatsPeriod.Week,
        val insights: List<StatsInsight> = emptyList(),
        val overview: StatsOverview? = null,
        val localHourly: List<StatsOverviewHourlyBucket> = emptyList(),
        val localTopProducts: List<StatsOverviewTopProduct> = emptyList(),
        val localAnomalies: List<StatsOverviewAnomaly> = emptyList(),
    ) : StatsState
}

data class StatsDay(
    val date: LocalDate,
    val totals: DayTotals?,
)

@HiltViewModel
class StatsViewModel @Inject constructor(
    private val statsRepository: StatsRepository,
    private val historyRepository: HistoryRepository,
    connectivityObserver: ConnectivityObserver,
    private val settingsStore: SettingsStore,
) : ViewModel() {
    private val today = currentLocalDate()
    private val periodDays = daysForPeriod(StatsPeriod.Week)
    private val totalsFlow = combine(periodDays.map(statsRepository::observeDayTotals)) { views ->
        views.toList()
    }

    val state = combine(
        totalsFlow,
        connectivityObserver.observe(),
    ) { views, network ->
        val totalsByDate = views.mapNotNull(CachedView<DayTotals>::value).associateBy { it.date }
        val totals = periodDays.map { day -> StatsDay(date = day, totals = totalsByDate[day]) }
        val trackedDays = totals.count { it.totals?.mealCount ?: 0 > 0 }
        when {
            views.any { it.isRefreshing } && totals.all { it.totals == null } -> StatsState.Loading
            trackedDays < 3 -> StatsState.Sparse(date = today, trackedDays = trackedDays)
            else -> StatsState.Charts(
                date = today,
                days = totals,
                staleCacheAt = totals.mapNotNull(StatsDay::totals).staleCacheAt(network.isConnected),
            )
        }
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = StatsState.Loading,
    )

    @OptIn(ExperimentalCoroutinesApi::class)
    val foodState = settingsStore.statsPeriod.flatMapLatest { period ->
        val days = daysForPeriod(period)
        val periodTotalsFlow = combine(days.map(statsRepository::observeDayTotals)) { views ->
            views.toList()
        }
        val (from, to) = days.periodBounds()
        val cachedMealsFlow = historyRepository.observeCachedMeals(from, to)
        val insightsFlow = flow {
            emit(
                runCatching { statsRepository.getInsights(period, slot = "stats") }
                    .getOrDefault(emptyList()),
            )
        }
        val overviewFlow = flow {
            emit(runCatching { statsRepository.getOverview(period) }.getOrNull())
        }
        combine(
            periodTotalsFlow,
            cachedMealsFlow,
            insightsFlow,
            overviewFlow,
            connectivityObserver.observe(),
        ) { views, cachedMeals, insights, overview, network ->
            val totalsByDate = views.mapNotNull(CachedView<DayTotals>::value).associateBy { it.date }
            val totals = days.map { day -> StatsDay(date = day, totals = totalsByDate[day]) }
            val trackedDays = totals.count { it.totals?.mealCount ?: 0 > 0 }
            when {
                views.any { it.isRefreshing } && totals.all { it.totals == null } -> StatsState.Loading
                trackedDays < 3 -> StatsState.Sparse(
                    date = today,
                    trackedDays = trackedDays,
                    period = period,
                )
                else -> StatsState.Charts(
                    date = today,
                    days = totals,
                    staleCacheAt = totals.mapNotNull(StatsDay::totals).staleCacheAt(network.isConnected),
                    period = period,
                    insights = insights,
                    overview = overview,
                    localHourly = cachedMeals.toHourlyBuckets(),
                    localTopProducts = cachedMeals.toTopProducts(),
                    localAnomalies = totals.toAnomalies(cachedMeals),
                )
            }
        }
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = StatsState.Loading,
    )

    fun selectPeriod(period: StatsPeriod) {
        viewModelScope.launch {
            settingsStore.updateStatsPeriod(period)
        }
    }

    private fun daysForPeriod(period: StatsPeriod): List<LocalDate> =
        ((period.days - 1) downTo 0).map { offset -> today.minus(DatePeriod(days = offset)) }
}

private fun List<LocalDate>.periodBounds(): Pair<Instant, Instant> {
    val zone = TimeZone.currentSystemDefault()
    val start = first().atStartOfDayIn(zone)
    val end = last().plus(DatePeriod(days = 1)).atStartOfDayIn(zone)
    return start to end
}

private fun currentLocalDate(): LocalDate =
    Clock.System.now().toLocalDateTime(TimeZone.currentSystemDefault()).date

private fun List<DayTotals>.staleCacheAt(isConnected: Boolean): Instant? {
    if (isConnected) return null
    val latestFetchedAt = mapNotNull { it.fetchedAt }.maxOrNull() ?: return null
    val ageMillis = Clock.System.now().toEpochMilliseconds() - latestFetchedAt.toEpochMilliseconds()
    return latestFetchedAt.takeIf { ageMillis > 24 * 60 * 60 * 1_000L }
}

private fun List<Meal>.acceptedMeals(): List<Meal> =
    filter { meal -> meal.status.equals("accepted", ignoreCase = true) }

private fun List<Meal>.toHourlyBuckets(): List<StatsOverviewHourlyBucket> {
    val counts = IntArray(24)
    val zone = TimeZone.currentSystemDefault()
    acceptedMeals().forEach { meal ->
        val hour = meal.eatenAt.toLocalDateTime(zone).hour
        counts[hour] += 1
    }
    val maxCount = counts.maxOrNull() ?: 0
    return (0..23).map { hour ->
        StatsOverviewHourlyBucket(
            hour = hour,
            mealCount = counts[hour],
            share = if (maxCount > 0) counts[hour].toDouble() / maxCount else 0.0,
        )
    }
}

private fun List<Meal>.toTopProducts(): List<StatsOverviewTopProduct> {
    data class Bucket(
        val name: String,
        val count: Int,
    )

    val counts = linkedMapOf<String, Bucket>()
    acceptedMeals().forEach { meal ->
        val names = meal.items
            .mapNotNull { item ->
                val name = item.name.trim().takeIf(String::isNotEmpty) ?: return@mapNotNull null
                val key = item.productId?.let { "product:$it" } ?: "name:${name.lowercase()}"
                key to name
            }
            .ifEmpty {
                meal.title
                    ?.trim()
                    ?.takeIf(String::isNotEmpty)
                    ?.let { title -> listOf("meal:${title.lowercase()}" to title) }
                    .orEmpty()
            }
        names.forEach { (key, name) ->
            val previous = counts[key]
            counts[key] = Bucket(
                name = previous?.name ?: name,
                count = (previous?.count ?: 0) + 1,
            )
        }
    }
    return counts.values
        .sortedWith(compareByDescending<Bucket> { it.count }.thenBy { it.name.lowercase() })
        .take(5)
        .mapIndexed { index, bucket ->
            StatsOverviewTopProduct(
                rank = index + 1,
                name = bucket.name,
                count = bucket.count,
                kcalPer100g = null,
                proteinPer100g = null,
                fatPer100g = null,
                carbsPer100g = null,
                imageUrl = null,
            )
        }
}

private fun List<StatsDay>.toAnomalies(meals: List<Meal>): List<StatsOverviewAnomaly> {
    val values = mapNotNull { day ->
        day.totals
            ?.takeIf { it.mealCount > 0 }
            ?.kcal
    }
    if (values.size < 3) return emptyList()
    val average = values.average()
    val spread = sqrt(values.sumOf { value -> (value - average) * (value - average) } / values.size)
    val threshold = maxOf(250.0, spread * 1.2, average * 0.18)
    val mealsByDay = meals.acceptedMeals().groupBy { it.eatenAtDay }
    val typicalMealCount = mapNotNull { day ->
        day.totals
            ?.takeIf { it.mealCount > 0 }
            ?.mealCount
            ?.toDouble()
    }.medianOrZero()
    return mapNotNull { day ->
        val kcal = day.totals?.kcal ?: return@mapNotNull null
        val delta = kcal - average
        if (abs(delta) < threshold) return@mapNotNull null
        val direction = if (delta > 0) "up" else "down"
        StatsOverviewAnomaly(
            date = day.date,
            direction = direction,
            reason = localAnomalyReason(
                direction = direction,
                meals = mealsByDay[day.date].orEmpty(),
                fallbackMealCount = day.totals.mealCount,
                typicalMealCount = typicalMealCount,
            ),
            kcal = kcal,
            deltaKcal = delta,
        )
    }.sortedWith(compareByDescending<StatsOverviewAnomaly> { abs(it.deltaKcal) }.thenBy { it.date })
        .take(3)
}

private fun localAnomalyReason(
    direction: String,
    meals: List<Meal>,
    fallbackMealCount: Int,
    typicalMealCount: Double,
): String {
    val mealCount = meals.size.takeIf { it > 0 } ?: fallbackMealCount
    if (direction == "up" && mealCount > typicalMealCount) {
        return LOCAL_REASON_MORE_MEALS
    }
    if (direction == "down") {
        if (meals.isNotEmpty()) {
            val hasMorning = meals.any { meal ->
                val hour = meal.eatenAt.toLocalDateTime(TimeZone.currentSystemDefault()).hour
                hour in 6..10
            }
            if (!hasMorning) return LOCAL_REASON_NO_MORNING
        }
        if (mealCount < typicalMealCount) return LOCAL_REASON_LESS_MEALS
    }
    return LOCAL_REASON_RHYTHM
}

private fun List<Double>.medianOrZero(): Double {
    if (isEmpty()) return 0.0
    val sorted = sorted()
    val mid = sorted.size / 2
    return if (sorted.size % 2 == 0) {
        (sorted[mid - 1] + sorted[mid]) / 2
    } else {
        sorted[mid]
    }
}

const val LOCAL_REASON_MORE_MEALS = "__local_more_meals"
const val LOCAL_REASON_LESS_MEALS = "__local_less_meals"
const val LOCAL_REASON_NO_MORNING = "__local_no_morning"
const val LOCAL_REASON_RHYTHM = "__local_rhythm"
