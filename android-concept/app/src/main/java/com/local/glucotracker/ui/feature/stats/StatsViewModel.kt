package com.local.glucotracker.ui.feature.stats

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.data.sync.ConnectivityObserver
import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.DayTotals
import com.local.glucotracker.domain.repository.StatsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
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
    ) : StatsState
    data class Charts(
        val date: LocalDate,
        val days: List<DayTotals>,
        val staleCacheAt: Instant?,
    ) : StatsState
}

@HiltViewModel
class StatsViewModel @Inject constructor(
    statsRepository: StatsRepository,
    connectivityObserver: ConnectivityObserver,
) : ViewModel() {
    private val today = currentLocalDate()
    private val periodDays = (6 downTo 0).map { offset -> today.minus(DatePeriod(days = offset)) }
    private val totalsFlow = combine(periodDays.map(statsRepository::observeDayTotals)) { views ->
        views.toList()
    }

    val state = combine(
        totalsFlow,
        connectivityObserver.observe(),
    ) { views, network ->
        val totals = views.mapNotNull(CachedView<DayTotals>::value)
        val trackedDays = totals.count { it.mealCount > 0 }
        when {
            views.any { it.isRefreshing } && totals.isEmpty() -> StatsState.Loading
            trackedDays < 3 -> StatsState.Sparse(date = today, trackedDays = trackedDays)
            else -> StatsState.Charts(
                date = today,
                days = totals,
                staleCacheAt = totals.staleCacheAt(network.isConnected),
            )
        }
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = StatsState.Loading,
    )
}

private fun currentLocalDate(): LocalDate =
    Clock.System.now().toLocalDateTime(TimeZone.currentSystemDefault()).date

private fun List<DayTotals>.staleCacheAt(isConnected: Boolean): Instant? {
    if (isConnected) return null
    val latestFetchedAt = mapNotNull { it.fetchedAt }.maxOrNull() ?: return null
    val ageMillis = Clock.System.now().toEpochMilliseconds() - latestFetchedAt.toEpochMilliseconds()
    return latestFetchedAt.takeIf { ageMillis > 24 * 60 * 60 * 1_000L }
}
