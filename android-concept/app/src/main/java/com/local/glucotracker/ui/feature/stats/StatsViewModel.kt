package com.local.glucotracker.ui.feature.stats

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.data.settings.SettingsStore
import com.local.glucotracker.data.sync.ConnectivityObserver
import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.DayTotals
import com.local.glucotracker.domain.model.StatsInsight
import com.local.glucotracker.domain.model.StatsPeriod
import com.local.glucotracker.domain.repository.StatsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
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
import kotlinx.datetime.minus
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
    ) : StatsState
}

data class StatsDay(
    val date: LocalDate,
    val totals: DayTotals?,
)

@HiltViewModel
class StatsViewModel @Inject constructor(
    private val statsRepository: StatsRepository,
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
        val insightsFlow = flow {
            emit(
                runCatching { statsRepository.getInsights(period, slot = "stats") }
                    .getOrDefault(emptyList()),
            )
        }
        combine(
            periodTotalsFlow,
            insightsFlow,
            connectivityObserver.observe(),
        ) { views, insights, network ->
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

private fun currentLocalDate(): LocalDate =
    Clock.System.now().toLocalDateTime(TimeZone.currentSystemDefault()).date

private fun List<DayTotals>.staleCacheAt(isConnected: Boolean): Instant? {
    if (isConnected) return null
    val latestFetchedAt = mapNotNull { it.fetchedAt }.maxOrNull() ?: return null
    val ageMillis = Clock.System.now().toEpochMilliseconds() - latestFetchedAt.toEpochMilliseconds()
    return latestFetchedAt.takeIf { ageMillis > 24 * 60 * 60 * 1_000L }
}
