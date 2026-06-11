package com.local.glucotracker.ui.glucose

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.data.api.GlucoseApi
import com.local.glucotracker.data.settings.GlucoAlarmToggles
import com.local.glucotracker.data.settings.GlucoSettingsStore
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
import kotlin.math.roundToInt
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.mapLatest
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.atStartOfDayIn
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

data class TodayGlucoseKpiState(
    val belowRangePercent: Int?,
)

@HiltViewModel
@OptIn(ExperimentalCoroutinesApi::class)
class TodayGlucoseKpiViewModel @Inject constructor(
    glucoseRepository: GlucoseRepository,
) : ViewModel() {
    private val refreshAnchor = MutableStateFlow(Clock.System.now())

    val state = refreshAnchor
        .flatMapLatest { anchor ->
            glucoseRepository.observeRange(anchor.startOfLocalDay(), anchor)
        }
        .map { view ->
            val readings = view.value?.readings.orEmpty()
            TodayGlucoseKpiState(
                belowRangePercent = readings
                    .takeIf { it.isNotEmpty() }
                    ?.let { points ->
                        val below = points.count {
                            it.displayValueMmolL < BelowRangeThresholdMmol
                        }
                        (below * 100.0 / points.size).roundToInt()
                    },
            )
        }
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5_000),
            initialValue = TodayGlucoseKpiState(belowRangePercent = null),
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

data class TirDayUi(
    val veryLowPct: Int,
    val lowPct: Int,
    val inRangePct: Int,
    val highPct: Int,
    val veryHighPct: Int,
    val hasData: Boolean,
)

@HiltViewModel
@OptIn(ExperimentalCoroutinesApi::class)
class StatsTirViewModel @Inject constructor(
    private val glucoseApi: GlucoseApi,
) : ViewModel() {
    private val period = MutableStateFlow<String?>(null)

    val state: StateFlow<List<TirDayUi>> = period
        .filterNotNull()
        .mapLatest { selected ->
            runCatching { glucoseApi.tirDaily(selected).days.map { it.toUi() } }
                .getOrDefault(emptyList())
        }
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5_000),
            initialValue = emptyList(),
        )

    fun load(periodApiValue: String) {
        period.value = periodApiValue
    }
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

@HiltViewModel
class MoreGlucoseSettingsViewModel @Inject constructor(
    private val settingsStore: GlucoSettingsStore,
) : ViewModel() {
    val alarmToggles = settingsStore.alarmToggles.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = GlucoAlarmToggles(),
    )

    fun toggleAlarm(key: String) {
        viewModelScope.launch {
            settingsStore.toggleAlarm(key)
        }
    }
}

private fun com.local.glucotracker.generated.model.GlucoseTirDayResponse.toUi(): TirDayUi =
    TirDayUi(
        veryLowPct = (veryLowPct?.toDouble() ?: 0.0).roundToInt(),
        lowPct = (lowPct?.toDouble() ?: 0.0).roundToInt(),
        inRangePct = (inRangePct?.toDouble() ?: 0.0).roundToInt(),
        highPct = (highPct?.toDouble() ?: 0.0).roundToInt(),
        veryHighPct = (veryHighPct?.toDouble() ?: 0.0).roundToInt(),
        hasData = points > 0,
    )

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

private fun Instant.startOfLocalDay(): Instant {
    val zone = TimeZone.currentSystemDefault()
    return toLocalDateTime(zone).date.atStartOfDayIn(zone)
}

private const val MiniGlucoseRefreshIntervalMillis = 5 * 60 * 1_000L
private const val BelowRangeThresholdMmol = 3.9
