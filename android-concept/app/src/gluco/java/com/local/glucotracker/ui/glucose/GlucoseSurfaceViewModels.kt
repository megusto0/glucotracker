package com.local.glucotracker.ui.glucose

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.domain.model.NightscoutConnectionState
import com.local.glucotracker.domain.model.NightscoutDayStatus
import com.local.glucotracker.domain.model.NightscoutStatus
import com.local.glucotracker.domain.model.GlucoseReading
import com.local.glucotracker.domain.model.InsulinEvent
import com.local.glucotracker.data.repository.InsulinRepository
import com.local.glucotracker.domain.repository.GlucoseRepository
import com.local.glucotracker.domain.repository.NightscoutRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

sealed interface MiniGlucoseUiState {
    data object Empty : MiniGlucoseUiState
    data class Reading(
        val valueMmol: Double,
        val deltaMmol: Double?,
        val minutesAgo: Int,
        val points: List<Double>,
    ) : MiniGlucoseUiState
}

@HiltViewModel
@OptIn(ExperimentalCoroutinesApi::class)
class MiniGlucoseViewModel @Inject constructor(
    glucoseRepository: GlucoseRepository,
) : ViewModel() {
    private val refreshAnchor = MutableStateFlow(Clock.System.now())

    val state = refreshAnchor
        .flatMapLatest { anchor ->
            glucoseRepository.observeRange(lastSixHoursFrom(anchor), anchor)
        }
        .map { it.toMiniGlucose() }
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5_000),
            initialValue = MiniGlucoseUiState.Empty,
        )

    init {
        viewModelScope.launch {
            while (true) {
                refreshAnchor.value = Clock.System.now()
                delay(MiniGlucoseRefreshIntervalMillis)
            }
        }
    }
}

@HiltViewModel
class GlucoseSparklineViewModel @Inject constructor(
    private val glucoseRepository: GlucoseRepository,
) : ViewModel() {
    fun readings(date: LocalDate): Flow<List<GlucoseReading>> {
        val (from, to) = date.dayBounds()
        return glucoseRepository.observeCachedRange(from, to)
            .map { view -> view.value?.readings.orEmpty() }
    }

}

@HiltViewModel
class InsulinContextViewModel @Inject constructor(
    private val insulinRepository: InsulinRepository,
) : ViewModel() {
    private val dayEvents = MutableStateFlow<Map<LocalDate, List<InsulinEvent>>>(emptyMap())
    private val requestedDates = mutableSetOf<LocalDate>()

    fun events(date: LocalDate): Flow<List<InsulinEvent>> {
        load(date)
        return dayEvents.map { eventsByDay -> eventsByDay[date].orEmpty() }
    }

    private fun load(date: LocalDate) {
        if (!requestedDates.add(date)) return
        viewModelScope.launch {
            val events = runCatching { insulinRepository.eventsForDay(date) }.getOrDefault(emptyList())
            dayEvents.update { current -> current + (date to events) }
        }
    }
}

data class MoreNightscoutState(
    val status: NightscoutStatus,
    val isRefreshing: Boolean,
)

@HiltViewModel
class MoreNightscoutViewModel @Inject constructor(
    private val nightscoutRepository: NightscoutRepository,
) : ViewModel() {
    private val empty = NightscoutStatus(
        lastSyncAt = null,
        queueDepth = 0,
        connectionState = NightscoutConnectionState.Unknown,
    )

    private val mutableState = kotlinx.coroutines.flow.MutableStateFlow(
        MoreNightscoutState(status = empty, isRefreshing = false),
    )

    val state = mutableState.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = mutableState.value,
    )

    init {
        refresh()
    }

    fun syncNow() {
        viewModelScope.launch {
            load { nightscoutRepository.syncToday(currentLocalDate()).toStatus() }
        }
    }

    private fun refresh() {
        viewModelScope.launch {
            load { nightscoutRepository.dayStatus(currentLocalDate()).toStatus() }
        }
    }

    private suspend fun load(block: suspend () -> NightscoutStatus) {
        mutableState.value = mutableState.value.copy(isRefreshing = true)
        val current = mutableState.value.status
        val status = runCatching { block() }
            .getOrElse {
                runCatching { nightscoutRepository.status() }
                    .getOrElse { current.copy(connectionState = NightscoutConnectionState.Disconnected) }
            }
        mutableState.value = MoreNightscoutState(status = status, isRefreshing = false)
    }
}

private fun NightscoutDayStatus.toStatus(): NightscoutStatus =
    NightscoutStatus(
        lastSyncAt = lastSyncAt,
        queueDepth = unsyncedMealsCount + failedMealsCount,
        connectionState = when {
            !configured -> NightscoutConnectionState.Unknown
            connected -> NightscoutConnectionState.Connected
            else -> NightscoutConnectionState.Disconnected
        },
    )

private fun currentLocalDate(): LocalDate =
    Clock.System.now().toLocalDateTime(TimeZone.currentSystemDefault()).date

private fun lastSixHoursFrom(anchor: Instant): Instant =
    Instant.fromEpochMilliseconds(anchor.toEpochMilliseconds() - 6 * 60 * 60 * 1_000L)

private const val MiniGlucoseRefreshIntervalMillis = 5 * 60 * 1_000L
