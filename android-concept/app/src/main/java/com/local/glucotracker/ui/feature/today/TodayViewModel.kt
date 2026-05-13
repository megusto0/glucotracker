package com.local.glucotracker.ui.feature.today

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.data.settings.SettingsStore
import com.local.glucotracker.data.sync.ConnectivityObserver
import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.DayTotals
import com.local.glucotracker.domain.model.Meal
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.domain.model.StatsPeriod
import com.local.glucotracker.domain.model.SyncStatus
import com.local.glucotracker.domain.model.UserGoals
import com.local.glucotracker.domain.model.hasRestaurantSource
import com.local.glucotracker.domain.model.matchesCreateMeal
import com.local.glucotracker.domain.repository.OutboxRepository
import com.local.glucotracker.domain.repository.StatsRepository
import com.local.glucotracker.domain.repository.SyncRepository
import com.local.glucotracker.domain.repository.TodayRepository
import com.local.glucotracker.ui.format.PhotoProcessingUiState
import com.local.glucotracker.ui.format.mapOutboxAndMealToPhotoProcessingUiState
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.datetime.Clock
import kotlinx.datetime.DatePeriod
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.plus
import kotlinx.datetime.toLocalDateTime

sealed interface TodayState {
    data object Loading : TodayState
    data class Empty(
        val date: LocalDate,
        val syncStatus: SyncStatus,
        val isRefreshing: Boolean,
        val canGoNext: Boolean,
        val softObservation: String? = null,
    ) : TodayState
    data class Day(
        val date: LocalDate,
        val totals: DayTotals,
        val goals: UserGoals,
        val rows: List<TodayMealRowUi>,
        val pendingQueueCount: Int,
        val syncStatus: SyncStatus,
        val isRefreshing: Boolean,
        val lastAddedId: String?,
        val canGoNext: Boolean,
        val softObservation: String? = null,
        val isOnline: Boolean = true,
    ) : TodayState
}

data class TodayMealRowUi(
    val id: String,
    val recordId: String?,
    val outboxId: String?,
    val kind: TodayMealRowKind,
    val eatenAt: Instant,
    val title: String?,
    val source: TodayMealSource,
    val status: TodayMealStatus,
    val photo: String?,
    val totalKcal: Double?,
    val totalCarbsG: Double?,
    val totalProteinG: Double?,
    val totalFatG: Double?,
    val errorMessage: String?,
    val enteredCurrentStateAt: Instant? = null,
    val nextAttemptAt: Instant? = null,
    val lastErrorCode: String? = null,
    val estimateStatus: String? = null,
    val photoProcessing: PhotoProcessingUiState? = null,
)

enum class TodayMealRowKind {
    Accepted,
    Pending,
}

enum class TodayMealSource {
    Photo,
    Restaurant,
    Pattern,
    Manual,
    Mixed,
    Text,
}

enum class TodayMealStatus {
    Accepted,
    Draft,
    Estimating,
    Queued,
    Uploading,
    Stuck,
}

@HiltViewModel
@OptIn(ExperimentalCoroutinesApi::class)
class TodayViewModel @Inject constructor(
    private val todayRepository: TodayRepository,
    private val outboxRepository: OutboxRepository,
    private val syncRepository: SyncRepository,
    private val statsRepository: StatsRepository,
    private val settingsStore: SettingsStore,
    private val connectivityObserver: ConnectivityObserver,
) : ViewModel() {
    private val selectedDate = MutableStateFlow(currentLocalDate())
    private val refreshTick = MutableStateFlow(0)

    private val isOnline = connectivityObserver.observe()
        .map { it.isConnected }
        .stateIn(viewModelScope, SharingStarted.Eagerly, true)

    private val dayView = combine(selectedDate, refreshTick) { date, _ -> date }
        .flatMapLatest { date -> todayRepository.observeDay(date) }

    private val coreState = combine(
        selectedDate,
        dayView,
        outboxRepository.observe(),
        syncRepository.observeStatus(),
    ) { date, cachedDay, outbox, syncStatus ->
        TodayCoreState(
            date = date,
            cachedDay = cachedDay,
            outbox = outbox,
            syncStatus = syncStatus,
        )
    }

    private val softObservation = refreshTick.flatMapLatest {
        flow {
            val text = runCatching {
                statsRepository.getInsights(StatsPeriod.Fortnight, slot = "today")
                    .firstOrNull()
                    ?.text
            }.getOrNull()
            emit(text)
        }
    }

    val state = combine(
        coreState,
        settingsStore.userGoals,
        softObservation,
        isOnline,
    ) { core, goals, observation, online ->
        toTodayState(
            date = core.date,
            cachedDay = core.cachedDay,
            outbox = core.outbox,
            syncStatus = core.syncStatus,
            goals = goals,
            softObservation = observation.takeIf { core.date == currentLocalDate() },
            isOnline = online,
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = TodayState.Loading,
    )

    init {
        requestSyncInBackground()
    }

    fun refresh() {
        refreshTick.value += 1
        requestSyncInBackground()
    }

    fun selectDate(date: LocalDate) {
        selectedDate.value = date
    }

    fun previousDay() {
        selectedDate.value = selectedDate.value.plus(DatePeriod(days = -1))
    }

    fun nextDay() {
        if (selectedDate.value < currentLocalDate()) {
            selectedDate.value = selectedDate.value.plus(DatePeriod(days = 1))
        }
    }

    fun deleteRow(row: TodayMealRowUi) {
        viewModelScope.launch {
            if (row.kind == TodayMealRowKind.Pending && row.outboxId != null) {
                outboxRepository.remove(row.outboxId)
            } else if (row.recordId != null) {
                outboxRepository.enqueue(OutboxKind.DeleteMeal(serverId = row.recordId))
            }
        }
    }

    fun saveOnboardingGoals(kcal: Int?, protein: Int?, carbs: Int?, fat: Int?) {
        viewModelScope.launch {
            kcal?.let { settingsStore.updateGoal("dailyKcal", it.toString()) }
            protein?.let { settingsStore.updateGoal("dailyProteinG", it.toString()) }
            carbs?.let { settingsStore.updateGoal("dailyCarbsG", it.toString()) }
            fat?.let { settingsStore.updateGoal("dailyFatG", it.toString()) }
            settingsStore.completeGoalsSetup()
        }
    }

    fun skipGoalsOnboarding() {
        viewModelScope.launch {
            settingsStore.completeGoalsSetup()
        }
    }

    private fun requestSyncInBackground() {
        viewModelScope.launch {
            runCatching { syncRepository.requestSync() }
        }
    }
}

private data class TodayCoreState(
    val date: LocalDate,
    val cachedDay: CachedView<com.local.glucotracker.domain.model.DayState>,
    val outbox: List<OutboxItem>,
    val syncStatus: SyncStatus,
)

private fun toTodayState(
    date: LocalDate,
    cachedDay: CachedView<com.local.glucotracker.domain.model.DayState>,
    outbox: List<OutboxItem>,
    syncStatus: SyncStatus,
    goals: UserGoals,
    softObservation: String?,
    isOnline: Boolean,
): TodayState {
    val day = cachedDay.value
    val serverMeals = day?.meals.orEmpty()
    val acceptedMeals = serverMeals.filter { it.isAcceptedStatus() }
    val backendDrafts = serverMeals.filter { it.isDraftStatus() }
    val activeOutbox = outbox.filter { it.state.isVisibleQueueState() }
        .filterNot { item -> item.isAlreadyAccepted(acceptedMeals) }
        .filterNot { it.isZombie }
    val pendingCount = activeOutbox.count { item -> item.affectsDay(date, acceptedMeals) }
    val visibleSyncStatus = syncStatus.copy(
        queueDepth = activeOutbox.count { item -> item.state.countsInSyncQueue() },
    )
    val rows = buildRows(date, acceptedMeals, backendDrafts, activeOutbox)

    if (day == null && rows.isEmpty()) {
        return if (cachedDay.isRefreshing) {
            TodayState.Loading
        } else {
            TodayState.Empty(
                date = date,
                syncStatus = visibleSyncStatus,
                isRefreshing = cachedDay.isRefreshing,
                canGoNext = date < currentLocalDate(),
                softObservation = softObservation,
            )
        }
    }

    return TodayState.Day(
        date = date,
        totals = day?.totals ?: DayTotals(
            date = date,
            kcal = 0.0,
            carbsG = 0.0,
            proteinG = 0.0,
            fatG = 0.0,
            fiberG = 0.0,
            mealCount = 0,
        ),
        goals = goals,
        rows = rows,
        pendingQueueCount = pendingCount,
        syncStatus = visibleSyncStatus,
        isRefreshing = cachedDay.isRefreshing,
        lastAddedId = null,
        canGoNext = date < currentLocalDate(),
        softObservation = softObservation,
        isOnline = isOnline,
    )
}

private fun buildRows(
    date: LocalDate,
    acceptedMeals: List<Meal>,
    backendDrafts: List<Meal>,
    outbox: List<OutboxItem>,
): List<TodayMealRowUi> {
    val deleteItemsByServerId = outbox
        .mapNotNull { item -> (item.kind as? OutboxKind.DeleteMeal)?.serverId?.let { it to item } }
        .toMap()
    val editItemsByServerId = outbox
        .mapNotNull { item -> (item.kind as? OutboxKind.EditMeal)?.serverId?.let { it to item } }
        .toMap()
    val itemPatchItemsByMealId = outbox
        .mapNotNull { item -> (item.kind as? OutboxKind.PatchMealItem)?.mealId?.let { it to item } }
        .toMap()
    val localDraftMealIds = outbox.mapNotNull { item -> item.referencedDraftMealId() }.toSet()
    val photoQueueItems = outbox
        .filter { item -> item.kind is OutboxKind.CapturedMeal }
        .filter { item -> item.affectsDay(date, acceptedMeals) }
        .sortedBy { item -> item.createdAt }
    val photoQueueSize = photoQueueItems.size
    val photoQueuePositions = photoQueueItems
        .mapIndexed { index, item -> item.id to index + 1 }
        .toMap()

    val acceptedRows = acceptedMeals
        .filterNot { meal -> deleteItemsByServerId[meal.id]?.state?.let { it != OutboxState.Stuck } == true }
        .map { meal ->
            val deleteItem = deleteItemsByServerId[meal.id]
            val editItem = editItemsByServerId[meal.id]
            val activeItem = deleteItem ?: editItem ?: itemPatchItemsByMealId[meal.id]
            meal.toAcceptedRow(activeItem)
        }

    val backendDraftRows = backendDrafts
        .filterNot { meal -> deleteItemsByServerId[meal.id]?.state?.let { it != OutboxState.Stuck } == true }
        .filterNot { meal -> meal.id in localDraftMealIds }
        .map { meal ->
            val deleteItem = deleteItemsByServerId[meal.id]
            val editItem = editItemsByServerId[meal.id]
            val activeItem = deleteItem ?: editItem ?: itemPatchItemsByMealId[meal.id]
            meal.toBackendDraftRow(activeItem)
        }

    val pendingRows = outbox.mapNotNull { item ->
        item.toPendingRow(
            date = date,
            queuePosition = photoQueuePositions[item.id],
            queueSize = photoQueueSize.takeIf { it > 0 },
        )
    }

    return (acceptedRows + backendDraftRows + pendingRows).sortedByDescending { row -> row.eatenAt }
}

private fun Meal.toAcceptedRow(outboxItem: OutboxItem?): TodayMealRowUi {
    val editPatch = (outboxItem?.kind as? OutboxKind.EditMeal)?.patch
    return TodayMealRowUi(
        id = id,
        recordId = id,
        outboxId = outboxItem?.id,
        kind = TodayMealRowKind.Accepted,
        eatenAt = editPatch?.eatenAt ?: eatenAt,
        title = editPatch?.title ?: title,
        source = toMealSource(),
        status = outboxItem?.state.toMealStatus() ?: TodayMealStatus.Accepted,
        photo = thumbnailUrl,
        totalKcal = totalKcal,
        totalCarbsG = totalCarbsG,
        totalProteinG = totalProteinG,
        totalFatG = totalFatG,
        errorMessage = outboxItem?.errorMessage,
        enteredCurrentStateAt = outboxItem?.enteredCurrentStateAt,
        nextAttemptAt = outboxItem?.nextAttemptAt,
        lastErrorCode = outboxItem?.lastErrorCode,
        estimateStatus = estimateStatus,
        photoProcessing = null,
    )
}

private fun Meal.toBackendDraftRow(outboxItem: OutboxItem?): TodayMealRowUi {
    val editPatch = (outboxItem?.kind as? OutboxKind.EditMeal)?.patch
    return TodayMealRowUi(
        id = id,
        recordId = id,
        outboxId = outboxItem?.id,
        kind = TodayMealRowKind.Pending,
        eatenAt = editPatch?.eatenAt ?: eatenAt,
        title = editPatch?.title ?: title,
        source = toMealSource(),
        status = outboxItem?.state.toMealStatus() ?: estimateStatus.toBackendDraftStatus(),
        photo = thumbnailUrl,
        totalKcal = totalKcal,
        totalCarbsG = totalCarbsG,
        totalProteinG = totalProteinG,
        totalFatG = totalFatG,
        errorMessage = outboxItem?.errorMessage ?: estimateError,
        enteredCurrentStateAt = outboxItem?.enteredCurrentStateAt,
        nextAttemptAt = outboxItem?.nextAttemptAt,
        lastErrorCode = outboxItem?.lastErrorCode,
        estimateStatus = estimateStatus,
        photoProcessing = mapOutboxAndMealToPhotoProcessingUiState(this),
    )
}

@Suppress("REDUNDANT_ELSE_IN_WHEN")
private fun OutboxItem.toPendingRow(
    date: LocalDate,
    queuePosition: Int?,
    queueSize: Int?,
): TodayMealRowUi? {
    return when (val outboxKind = kind) {
        is OutboxKind.CreateMeal -> {
            if (outboxKind.eatenAt.localDate() != date) return null
            val draft = outboxKind.payload
            TodayMealRowUi(
                id = id,
                recordId = null,
                outboxId = id,
                kind = TodayMealRowKind.Pending,
                eatenAt = outboxKind.eatenAt,
                title = draft.title,
                source = outboxKind.toMealSource(),
                status = state.toMealStatus(),
                photo = draft.localPhotoPath,
                totalKcal = draft.totalKcal,
                totalCarbsG = draft.totalCarbsG,
                totalProteinG = draft.totalProteinG,
                totalFatG = draft.totalFatG,
                errorMessage = errorMessage,
                enteredCurrentStateAt = enteredCurrentStateAt,
                nextAttemptAt = nextAttemptAt,
                lastErrorCode = lastErrorCode,
                photoProcessing = null,
            )
        }
        is OutboxKind.CapturedMeal -> {
            if (outboxKind.capturedAt.localDate() != date) return null
            TodayMealRowUi(
                id = id,
                recordId = null,
                outboxId = id,
                kind = TodayMealRowKind.Pending,
                eatenAt = outboxKind.capturedAt,
                title = draft?.title ?: outboxKind.optimisticName,
                source = TodayMealSource.Photo,
                status = state.toMealStatus(),
                photo = outboxKind.localPhotoPath,
                totalKcal = null,
                totalCarbsG = null,
                totalProteinG = null,
                totalFatG = null,
                errorMessage = errorMessage,
                enteredCurrentStateAt = enteredCurrentStateAt,
                nextAttemptAt = nextAttemptAt,
                lastErrorCode = lastErrorCode,
                photoProcessing = mapOutboxAndMealToPhotoProcessingUiState(
                    outboxItem = this,
                    queuePosition = queuePosition,
                    queueSize = queueSize,
                ),
            )
        }
        is OutboxKind.CopyMealItemWeight,
        is OutboxKind.DeleteMeal,
        is OutboxKind.EditMeal,
        is OutboxKind.PatchMealItem,
        -> null
        else -> null
    }
}

@Suppress("REDUNDANT_ELSE_IN_WHEN")
private fun OutboxItem.affectsDay(date: LocalDate, acceptedMeals: List<Meal>): Boolean =
    when (val outboxKind = kind) {
        is OutboxKind.CreateMeal -> outboxKind.eatenAt.localDate() == date
        is OutboxKind.CapturedMeal -> outboxKind.capturedAt.localDate() == date
        is OutboxKind.CopyMealItemWeight -> false
        is OutboxKind.EditMeal -> {
            outboxKind.patch.eatenAt?.localDate() == date ||
                acceptedMeals.any { meal -> meal.id == outboxKind.serverId }
        }
        is OutboxKind.PatchMealItem -> acceptedMeals.any { meal -> meal.id == outboxKind.mealId }
        is OutboxKind.DeleteMeal -> acceptedMeals.any { meal -> meal.id == outboxKind.serverId }
        else -> false
    }

private fun OutboxItem.isAlreadyAccepted(acceptedMeals: List<Meal>): Boolean {
    val acceptedIds = acceptedMeals.map { it.id }.toSet()
    return when (val outboxKind = kind) {
        is OutboxKind.CapturedMeal -> draft?.id in acceptedIds ||
            (attempts > 0 && acceptedMeals.any { meal -> meal.matchesPhotoCapture(outboxKind.capturedAt) })
        is OutboxKind.CreateMeal -> (serverIdOnSuccess != null && serverIdOnSuccess in acceptedIds) ||
            (attempts > 0 && acceptedMeals.any { meal -> meal.matchesCreateMeal(outboxKind) })
        else -> false
    }
}

private fun OutboxState?.toMealStatus(): TodayMealStatus =
    when (this) {
        OutboxState.Stuck -> TodayMealStatus.Stuck
        OutboxState.Uploading -> TodayMealStatus.Uploading
        OutboxState.Queued -> TodayMealStatus.Queued
        else -> TodayMealStatus.Accepted
    }

private fun String?.toBackendDraftStatus(): TodayMealStatus =
    when (this?.lowercase()) {
        "estimating" -> TodayMealStatus.Estimating
        "failed",
        "timeout",
        "error",
        -> TodayMealStatus.Stuck
        else -> TodayMealStatus.Draft
    }

private fun OutboxState.countsInSyncQueue(): Boolean =
    this == OutboxState.Queued ||
        this == OutboxState.Uploading

private fun OutboxState.isVisibleQueueState(): Boolean =
    this == OutboxState.Queued ||
        this == OutboxState.Uploading ||
        this == OutboxState.Stuck

private fun OutboxItem.referencedDraftMealId(): String? =
    when (val outboxKind = kind) {
        is OutboxKind.CapturedMeal -> draft?.id ?: serverIdOnSuccess
        else -> null
    }

private fun String.toMealSource(): TodayMealSource =
    when (lowercase()) {
        "photo",
        "photo_estimate",
        "gallery",
        -> TodayMealSource.Photo
        "restaurant",
        "restaurant_db",
        -> TodayMealSource.Restaurant
        "pattern",
        "template",
        -> TodayMealSource.Pattern
        "manual" -> TodayMealSource.Manual
        "text" -> TodayMealSource.Text
        else -> TodayMealSource.Mixed
    }

private fun Meal.toMealSource(): TodayMealSource =
    if (hasRestaurantSource()) {
        TodayMealSource.Restaurant
    } else {
        source.toMealSource()
    }

private fun OutboxKind.CreateMeal.toMealSource(): TodayMealSource =
    if (hasRestaurantSource()) {
        TodayMealSource.Restaurant
    } else {
        source.toMealSource()
    }

private fun Meal.isAcceptedStatus(): Boolean =
    status.equals("accepted", ignoreCase = true)

private fun Meal.isDraftStatus(): Boolean =
    status.equals("draft", ignoreCase = true)

private fun Meal.matchesPhotoCapture(capturedAt: Instant): Boolean =
    source.toMealSource() == TodayMealSource.Photo &&
        eatenAt.toLocalDateTime(TimeZone.currentSystemDefault()).let { mealTime ->
            val capturedTime = capturedAt.toLocalDateTime(TimeZone.currentSystemDefault())
            mealTime.date == capturedTime.date &&
                mealTime.hour == capturedTime.hour &&
                mealTime.minute == capturedTime.minute
        }

private fun currentLocalDate(): LocalDate =
    Clock.System.now().toLocalDateTime(TimeZone.currentSystemDefault()).date

private fun Instant.localDate(): LocalDate =
    toLocalDateTime(TimeZone.currentSystemDefault()).date
