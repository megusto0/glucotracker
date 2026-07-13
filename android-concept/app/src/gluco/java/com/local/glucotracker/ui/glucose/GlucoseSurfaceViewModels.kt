package com.local.glucotracker.ui.glucose

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.data.api.GlucoseApi
import com.local.glucotracker.data.settings.GlucoAlarmToggles
import com.local.glucotracker.data.settings.GlucoSettingsStore
import com.local.glucotracker.domain.model.CreateNightscoutInsulinOutboxKind
import com.local.glucotracker.domain.model.DeleteNightscoutInsulinOutboxKind
import com.local.glucotracker.domain.model.NightscoutConnectionState
import com.local.glucotracker.domain.model.NightscoutDayStatus
import com.local.glucotracker.domain.model.NightscoutStatus
import com.local.glucotracker.domain.model.GlucoseReading
import com.local.glucotracker.domain.model.InsulinDayContext
import com.local.glucotracker.domain.model.InsulinEvent
import com.local.glucotracker.domain.model.InsulinEventType
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.domain.model.UpdateNightscoutInsulinOutboxKind
import com.local.glucotracker.data.repository.InsulinRepository
import com.local.glucotracker.domain.repository.GlucoseRepository
import com.local.glucotracker.domain.repository.NightscoutRepository
import com.local.glucotracker.domain.repository.OutboxRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlin.math.roundToInt
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.mapLatest
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.flow.stateIn
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
    private val outboxRepository: OutboxRepository,
) : ViewModel() {
    private val loadedSignatures = mutableMapOf<LocalDate, String>()

    fun context(date: LocalDate): Flow<InsulinDayContext> {
        val mutationsForDate = outboxRepository.observe()
            .map { items -> items.insulinOutboxForDate(date) }
            .distinctUntilChanged()
            // Any state transition of an insulin outbox item (incl. confirm)
            // re-pulls the server attribution, so the optimistic row is
            // replaced by the accepted one without reopening the screen.
            .onEach { items -> refreshIfStale(date, items.insulinSignature()) }
        return combine(
            mutationsForDate,
            // Room-backed: events the user has seen survive offline and
            // process death; a failed refresh leaves them untouched.
            insulinRepository.observeContextForDay(date),
        ) { items, server ->
            applyInsulinOutbox(server = server, items = items, date = date)
        }
    }

    private fun refreshIfStale(date: LocalDate, signature: String) {
        synchronized(loadedSignatures) {
            if (loadedSignatures[date] == signature) return
            loadedSignatures[date] = signature
        }
        viewModelScope.launch {
            runCatching { insulinRepository.refreshDay(date) }
                .onFailure {
                    synchronized(loadedSignatures) { loadedSignatures.remove(date) }
                }
        }
    }
}

data class PendingInsulin(
    val outboxId: String,
    val recordedAt: Instant,
    val units: Double,
)

internal fun List<OutboxItem>.pendingInsulinForDate(date: LocalDate): List<PendingInsulin> =
    mapNotNull { item ->
        val kind = item.kind as? CreateNightscoutInsulinOutboxKind ?: return@mapNotNull null
        // Confirmed mutations are refreshed from the backend and must no longer
        // render a second optimistic row beside the accepted event.
        if (item.state == OutboxState.Confirmed) return@mapNotNull null
        val localDate = kind.recordedAt
            .toLocalDateTime(TimeZone.currentSystemDefault())
            .date
        if (localDate != date) return@mapNotNull null
        PendingInsulin(
            outboxId = item.id,
            recordedAt = kind.recordedAt,
            units = kind.insulinUnits,
        )
    }

internal fun List<PendingInsulin>.signature(): String =
    joinToString("|") { it.outboxId }

internal fun List<OutboxItem>.insulinOutboxForDate(date: LocalDate): List<OutboxItem> =
    filter { item ->
        when (val kind = item.kind) {
            is CreateNightscoutInsulinOutboxKind -> kind.recordedAt.localDate() == date
            is UpdateNightscoutInsulinOutboxKind ->
                kind.originalRecordedAt.localDate() == date || kind.recordedAt.localDate() == date
            is DeleteNightscoutInsulinOutboxKind -> kind.recordedAt.localDate() == date
            else -> false
        }
    }

internal fun List<OutboxItem>.insulinSignature(): String =
    joinToString("|") { item ->
        "${item.id}:${item.state}:${item.attempts}:${item.serverIdOnSuccess.orEmpty()}"
    }

internal fun applyInsulinOutbox(
    server: InsulinDayContext,
    items: List<OutboxItem>,
    date: LocalDate,
): InsulinDayContext {
    val deletes = items.mapNotNull { it.kind as? DeleteNightscoutInsulinOutboxKind }
        .map { it.eventId }
        .toSet()
    val updates = items.mapNotNull { item ->
        (item.kind as? UpdateNightscoutInsulinOutboxKind)?.let { it to item.state }
    }.associateBy({ it.first.eventId }, { it })

    fun apply(event: InsulinEvent): InsulinEvent? {
        if (event.id in deletes) return null
        val (update, state) = updates[event.id] ?: return event
        if (update.recordedAt.localDate() != date) return null
        val alreadyFresh = state == OutboxState.Confirmed &&
            kotlin.math.abs(event.doseUnits - update.insulinUnits) < 0.01 &&
            event.timestamp == update.recordedAt
        return event.copy(
            timestamp = update.recordedAt,
            doseUnits = update.insulinUnits,
            isPending = !alreadyFresh,
        )
    }

    val byMealId = server.byMealId.mapValues { (_, events) ->
        events.mapNotNull(::apply)
    }.filterValues { it.isNotEmpty() }
    val orphans = server.orphans.mapNotNull(::apply).toMutableList()
    val knownIds = server.allEvents.map { it.id }.toSet()
    updates.values.forEach { (update, state) ->
        if (update.eventId !in knownIds && update.recordedAt.localDate() == date) {
            orphans += InsulinEvent(
                id = update.eventId,
                timestamp = update.recordedAt,
                doseUnits = update.insulinUnits,
                source = "glucotracker",
                sourceEventId = update.eventId,
                eventType = InsulinEventType.Bolus,
                isReadOnly = false,
                isPending = state != OutboxState.Confirmed,
            )
        }
    }
    val pendingCreates = items.pendingInsulinForDate(date)
    val optimisticCreates = mergeInsulinEvents(
        server = byMealId.values.flatten() + orphans,
        pending = pendingCreates,
    ).filter { it.isPending && it.id.startsWith("outbox-") }
    orphans += optimisticCreates
    return server.copy(
        byMealId = byMealId,
        orphans = orphans.sortedBy { it.timestamp },
    )
}

private fun Instant.localDate(): LocalDate =
    toLocalDateTime(TimeZone.currentSystemDefault()).date

/**
 * Server events plus optimistic outbox rows. A pending row is dropped as
 * soon as the server list contains a matching event (same dose within
 * two minutes), so confirm transitions swap seamlessly.
 */
internal fun mergeInsulinEvents(
    server: List<InsulinEvent>,
    pending: List<PendingInsulin>,
): List<InsulinEvent> {
    val optimistic = pending
        .filterNot { candidate -> server.any { event -> event.matches(candidate) } }
        .map { candidate ->
            InsulinEvent(
                id = "outbox-${candidate.outboxId}",
                timestamp = candidate.recordedAt,
                doseUnits = candidate.units,
                source = "glucotracker",
                sourceEventId = null,
                eventType = InsulinEventType.Bolus,
                isReadOnly = true,
                isPending = true,
            )
        }
    return server + optimistic
}

private fun InsulinEvent.matches(pending: PendingInsulin): Boolean =
    kotlin.math.abs(doseUnits - pending.units) < 0.01 &&
        kotlin.math.abs(
            timestamp.toEpochMilliseconds() - pending.recordedAt.toEpochMilliseconds(),
        ) <= 2 * 60 * 1_000L

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

    val normalizedGlucoseDisplay = settingsStore.normalizedGlucoseDisplay.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = false,
    )

    fun toggleAlarm(key: String) {
        viewModelScope.launch {
            settingsStore.toggleAlarm(key)
        }
    }

    fun toggleNormalizedGlucoseDisplay() {
        viewModelScope.launch {
            settingsStore.toggleNormalizedGlucoseDisplay()
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
