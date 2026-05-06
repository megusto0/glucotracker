package com.local.glucotracker.ui.feature.history

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.data.sync.ConnectivityObserver
import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.DayTotals
import com.local.glucotracker.domain.model.HistoryFilter
import com.local.glucotracker.domain.model.HistoryPage
import com.local.glucotracker.domain.model.HistoryQuery
import com.local.glucotracker.domain.model.HistoryStatusFilter
import com.local.glucotracker.domain.model.Meal
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.domain.repository.HistoryRepository
import com.local.glucotracker.domain.repository.OutboxRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.datetime.Clock
import kotlinx.datetime.DatePeriod
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.plus
import kotlinx.datetime.toLocalDateTime

data class HistoryScreenState(
    val filters: Set<HistoryFilter>,
    val status: HistoryStatusFilter,
    val search: String,
    val days: List<HistoryDayUi>,
    val isRefreshing: Boolean,
    val showNeedsNetworkHint: Boolean,
)

data class HistoryDayUi(
    val date: LocalDate,
    val totals: DayTotals?,
    val rows: List<HistoryMealRowUi>,
    val sparkline: List<Double>,
)

data class HistoryMealRowUi(
    val id: String,
    val recordId: String?,
    val outboxId: String?,
    val kind: HistoryMealRowKind,
    val eatenAt: Instant,
    val title: String?,
    val source: HistoryMealSource,
    val status: HistoryMealStatus,
    val photo: String?,
    val totalKcal: Double?,
    val totalCarbsG: Double?,
)

enum class HistoryMealRowKind {
    Accepted,
    Pending,
}

enum class HistoryMealSource {
    Photo,
    Pattern,
    Manual,
    Mixed,
    Text,
}

enum class HistoryMealStatus {
    Accepted,
    Estimating,
    Queued,
    Conflict,
}

@HiltViewModel
@OptIn(ExperimentalCoroutinesApi::class)
class HistoryViewModel @Inject constructor(
    private val historyRepository: HistoryRepository,
    outboxRepository: OutboxRepository,
    connectivityObserver: ConnectivityObserver,
) : ViewModel() {
    private val loadedDays = MutableStateFlow(InitialHistoryDays)
    private val filters = MutableStateFlow<Set<HistoryFilter>>(emptySet())
    private val status = MutableStateFlow(HistoryStatusFilter.Active)
    private val search = MutableStateFlow("")

    private val query = combine(
        loadedDays,
        filters,
        status,
        search,
    ) { days, activeFilters, activeStatus, activeSearch ->
        val today = currentLocalDate()
        HistoryQuery(
            fromDay = today.plus(DatePeriod(days = -(days - 1))),
            toDay = today,
            filters = activeFilters,
            status = activeStatus,
            search = activeSearch.trim(),
        )
    }

    private val history = query.flatMapLatest(historyRepository::observeHistory)

    val state = combine(
        query,
        history,
        outboxRepository.observe(),
        connectivityObserver.observe(),
    ) { activeQuery, page, outbox, network ->
        page.toScreenState(
            query = activeQuery,
            outbox = outbox,
            isOnline = network.isConnected,
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = HistoryScreenState(
            filters = emptySet(),
            status = HistoryStatusFilter.Active,
            search = "",
            days = emptyList(),
            isRefreshing = false,
            showNeedsNetworkHint = false,
        ),
    )

    fun loadMore() {
        loadedDays.value += HistoryPageDays
    }

    fun toggleFilter(filter: HistoryFilter) {
        filters.value = if (filter in filters.value) {
            filters.value - filter
        } else {
            filters.value + filter
        }
    }

    fun setStatus(next: HistoryStatusFilter) {
        status.value = next
    }

    fun setSearch(next: String) {
        search.value = next
    }
}

private const val InitialHistoryDays = 7
private const val HistoryPageDays = 7
private const val OfflineCacheDays = 14

private fun CachedView<HistoryPage>.toScreenState(
    query: HistoryQuery,
    outbox: List<OutboxItem>,
    isOnline: Boolean,
): HistoryScreenState {
    val activeOutbox = outbox.filter { it.state.isActiveQueueState() }
    val pageDays = value?.days.orEmpty()
    val daysByDate = pageDays.associateBy { it.date }
    val pendingByDate = activeOutbox
        .mapNotNull { item -> item.toPendingRow(query) }
        .groupBy { it.eatenAt.localDate() }
    val days = pageDays
        .map { day ->
            val acceptedRows = day.meals.toAcceptedRows(activeOutbox)
            val pendingRows = pendingByDate[day.date].orEmpty()
            HistoryDayUi(
                date = day.date,
                totals = day.totals,
                rows = (acceptedRows + pendingRows).sortedByDescending { it.eatenAt },
                sparkline = day.meals.sortedBy { it.eatenAt }.map { it.totalCarbsG },
            )
        }
        .let { existingDays ->
            val missingPendingDays = pendingByDate
                .filterKeys { date -> date !in daysByDate }
                .map { (date, rows) ->
                    HistoryDayUi(
                        date = date,
                        totals = null,
                        rows = rows.sortedByDescending { it.eatenAt },
                        sparkline = rows.sortedBy { it.eatenAt }.mapNotNull { it.totalCarbsG },
                    )
                }
            (existingDays + missingPendingDays).sortedByDescending { it.date }
        }

    return HistoryScreenState(
        filters = query.filters,
        status = query.status,
        search = query.search,
        days = days,
        isRefreshing = isRefreshing,
        showNeedsNetworkHint = !isOnline && query.toDay.daysSince(query.fromDay) + 1 > OfflineCacheDays,
    )
}

private fun List<Meal>.toAcceptedRows(outbox: List<OutboxItem>): List<HistoryMealRowUi> {
    val deleteItemsByServerId = outbox
        .mapNotNull { item -> (item.kind as? OutboxKind.DeleteMeal)?.serverId?.let { it to item } }
        .toMap()
    val editItemsByServerId = outbox
        .mapNotNull { item -> (item.kind as? OutboxKind.EditMeal)?.serverId?.let { it to item } }
        .toMap()
    val itemPatchItemsByMealId = outbox
        .mapNotNull { item -> (item.kind as? OutboxKind.PatchMealItem)?.mealId?.let { it to item } }
        .toMap()

    return filterNot { meal -> deleteItemsByServerId[meal.id]?.state?.let { it != OutboxState.Conflict } == true }
        .map { meal ->
            val activeItem = deleteItemsByServerId[meal.id]
                ?: editItemsByServerId[meal.id]
                ?: itemPatchItemsByMealId[meal.id]
            val editPatch = (activeItem?.kind as? OutboxKind.EditMeal)?.patch
            HistoryMealRowUi(
                id = meal.id,
                recordId = meal.id,
                outboxId = activeItem?.id,
                kind = HistoryMealRowKind.Accepted,
                eatenAt = editPatch?.eatenAt ?: meal.eatenAt,
                title = editPatch?.title ?: meal.title,
                source = meal.source.toMealSource(),
                status = activeItem?.state.toMealStatus(),
                photo = meal.thumbnailUrl,
                totalKcal = meal.totalKcal,
                totalCarbsG = meal.totalCarbsG,
            )
        }
}

private fun OutboxItem.toPendingRow(query: HistoryQuery): HistoryMealRowUi? {
    if (query.status != HistoryStatusFilter.Active && query.status != HistoryStatusFilter.All) return null

    val row = when (val outboxKind = kind) {
        is OutboxKind.CreateMeal -> {
            val draft = outboxKind.payload
            HistoryMealRowUi(
                id = id,
                recordId = null,
                outboxId = id,
                kind = HistoryMealRowKind.Pending,
                eatenAt = outboxKind.eatenAt,
                title = draft.title,
                source = outboxKind.source.toMealSource(),
                status = state.toMealStatus(),
                photo = draft.localPhotoPath,
                totalKcal = draft.totalKcal,
                totalCarbsG = draft.totalCarbsG,
            )
        }
        is OutboxKind.PhotoEstimateRequest -> {
            HistoryMealRowUi(
                id = id,
                recordId = null,
                outboxId = id,
                kind = HistoryMealRowKind.Pending,
                eatenAt = outboxKind.capturedAt,
                title = draft?.title,
                source = HistoryMealSource.Photo,
                status = state.toMealStatus(),
                photo = outboxKind.localPhotoPath,
                totalKcal = draft?.totalKcal,
                totalCarbsG = draft?.totalCarbsG,
            )
        }
        is OutboxKind.AcceptDraft -> {
            HistoryMealRowUi(
                id = id,
                recordId = null,
                outboxId = id,
                kind = HistoryMealRowKind.Pending,
                eatenAt = outboxKind.eatenAt,
                title = draft?.title,
                source = HistoryMealSource.Photo,
                status = state.toMealStatus(),
                photo = draft?.localPhotoPath,
                totalKcal = draft?.totalKcal,
                totalCarbsG = draft?.totalCarbsG,
            )
        }
        is OutboxKind.CopyMealItemWeight,
        is OutboxKind.CreateFingerstick,
        is OutboxKind.DeleteMeal,
        is OutboxKind.EditMeal,
        is OutboxKind.PatchMealItem,
        -> return null
    }

    return row.takeIf { it.matches(query) }
}

private fun HistoryMealRowUi.matches(query: HistoryQuery): Boolean {
    val date = eatenAt.localDate()
    if (date < query.fromDay || date > query.toDay) return false
    if (HistoryFilter.PhotoOnly in query.filters && source != HistoryMealSource.Photo && photo == null) return false
    if (HistoryFilter.LowConfidence in query.filters) return false
    if (HistoryFilter.WithCgm in query.filters || HistoryFilter.WithInsulin in query.filters) return false
    if (query.search.isBlank()) return true
    val haystack = listOfNotNull(title, source.name).joinToString(" ").lowercase()
    return query.search
        .lowercase()
        .split(Regex("\\s+"))
        .filter { it.isNotBlank() }
        .all { token -> token in haystack }
}

private fun OutboxState?.toMealStatus(): HistoryMealStatus =
    when (this) {
        OutboxState.Conflict -> HistoryMealStatus.Conflict
        OutboxState.Estimating,
        OutboxState.EstimateReady,
        -> HistoryMealStatus.Estimating
        OutboxState.Queued,
        OutboxState.Sending,
        -> HistoryMealStatus.Queued
        else -> HistoryMealStatus.Accepted
    }

private fun OutboxState.isActiveQueueState(): Boolean =
    this == OutboxState.Queued ||
        this == OutboxState.Sending ||
        this == OutboxState.Conflict ||
        this == OutboxState.Estimating

private fun String.toMealSource(): HistoryMealSource =
    when (lowercase()) {
        "photo",
        "photo_estimate",
        "gallery",
        -> HistoryMealSource.Photo
        "pattern",
        "template",
        -> HistoryMealSource.Pattern
        "manual" -> HistoryMealSource.Manual
        "text" -> HistoryMealSource.Text
        else -> HistoryMealSource.Mixed
    }

private fun currentLocalDate(): LocalDate =
    Clock.System.now().toLocalDateTime(TimeZone.currentSystemDefault()).date

private fun Instant.localDate(): LocalDate =
    toLocalDateTime(TimeZone.currentSystemDefault()).date

private fun LocalDate.daysSince(other: LocalDate): Int =
    ((toEpochDay() - other.toEpochDay()).coerceAtLeast(0)).toInt()

private fun LocalDate.toEpochDay(): Long =
    java.time.LocalDate.of(year, monthNumber, dayOfMonth).toEpochDay()
