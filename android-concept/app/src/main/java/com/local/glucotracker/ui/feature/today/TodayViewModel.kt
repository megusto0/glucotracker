package com.local.glucotracker.ui.feature.today

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.data.api.GoalsApi
import com.local.glucotracker.data.api.ScheduleApi
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
import kotlin.math.roundToInt
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.datetime.Clock
import kotlinx.datetime.DatePeriod
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.minus
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
        val typicalKcal14d: Int? = null,
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
    private val goalsApi: GoalsApi,
    private val scheduleApi: ScheduleApi,
    private val settingsStore: SettingsStore,
    private val connectivityObserver: ConnectivityObserver,
) : ViewModel() {
    private val selectedDate = MutableStateFlow(currentLocalDate())
    private val refreshTick = MutableStateFlow(0)
    private val dayRefreshTick = MutableStateFlow(0)

    private val isOnline = connectivityObserver.observe()
        .map { it.isConnected }
        .stateIn(viewModelScope, SharingStarted.Eagerly, true)

    // Keep the requested date attached to the cache emission it produced.
    // Combining selectedDate and dayView independently let the new date win a
    // frame before the new Room query did, briefly drawing yesterday's rows
    // under today's header and then rebuilding every card.
    private val dayView = combine(selectedDate, refreshTick, dayRefreshTick) { date, _, _ -> date }
        .switchDated(todayRepository::observeDay)

    private val coreState = combine(
        dayView,
        outboxRepository.observe(),
        syncRepository.observeStatus(),
    ) { datedDay, outbox, syncStatus ->
        TodayCoreState(
            date = datedDay.date,
            cachedDay = datedDay.value,
            outbox = outbox,
            syncStatus = syncStatus,
        )
    }

    private val softObservation = refreshTick.flatMapLatest {
        flow {
            emit(null)
            val text = runCatching {
                statsRepository.getInsights(StatsPeriod.Fortnight, slot = "today")
                    .firstOrNull()
                    ?.text
            }.getOrNull()
            emit(text)
        }
    }

    private val nonTypicalPeriods = refreshTick.flatMapLatest {
        flow {
            emit(emptyList())
            emit(
                runCatching {
                    scheduleApi.getSchedule().nonTypicalPeriods.orEmpty()
                        .map { period -> NonTypicalDatePeriod(period.startDate, period.endDate) }
                }.getOrDefault(emptyList()),
            )
        }
    }

    private val typicalKcal14d = selectedDate.flatMapLatest { date ->
        val comparisonDays = (1..TypicalKcalWindowDays)
            .map { offset -> date.minus(DatePeriod(days = offset)) }
            .reversed()
        combine(
            nonTypicalPeriods,
            combine(comparisonDays.map(statsRepository::observeDayTotals)) { views -> views.toList() },
        ) { excludedPeriods, views ->
            comparisonDays.zip(views)
                .filterNot { (day, _) -> excludedPeriods.any { it.contains(day) } }
                .mapNotNull { (_, view) ->
                    view.value
                        ?.takeIf { totals -> totals.mealCount > 0 && totals.kcal > 0.0 }
                        ?.kcal
                }
                .medianKcalOrNull(minDays = TypicalKcalMinTrackedDays)
        }
    }

    val state = combine(
        coreState,
        settingsStore.userGoals,
        softObservation,
        isOnline,
        typicalKcal14d,
    ) { core, goals, observation, online, typicalKcal ->
        toTodayState(
            date = core.date,
            cachedDay = core.cachedDay,
            outbox = core.outbox,
            syncStatus = core.syncStatus,
            goals = goals,
            softObservation = observation.takeIf { core.date == currentLocalDate() },
            isOnline = online,
            typicalKcal14d = typicalKcal,
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = TodayState.Loading,
    )

    init {
        requestSyncInBackground()
        refreshDayWhenOutboxConfirms()
        refreshDayWhilePhotoEstimateIsPending()
    }

    /**
     * Re-pull the day cache as soon as an outbox mutation confirms so the
     * accepted record (and server totals) replace the optimistic row without
     * waiting for a manual refresh.
     */
    private fun refreshDayWhenOutboxConfirms() {
        viewModelScope.launch {
            outboxRepository.observe()
                .map { items ->
                    items
                        .filter { it.state == OutboxState.Confirmed }
                        .map { it.id }
                        .toSet()
                }
                .distinctUntilChanged()
                .collect { confirmedIds ->
                    if (confirmedIds.isNotEmpty()) {
                        dayRefreshTick.update { it + 1 }
                    }
                }
        }
    }

    /**
     * Keep the local-first day stream active while a server-side photo
     * estimate is running, and periodically reconcile it with the backend.
     * This lets the row replace "estimating" with the accepted server record
     * even while the camera route temporarily covers Today.
     */
    private fun refreshDayWhilePhotoEstimateIsPending() {
        viewModelScope.launch {
            state
                .map { todayState ->
                    (todayState as? TodayState.Day)
                        ?.rows
                        ?.any { row ->
                            row.kind == TodayMealRowKind.Pending &&
                                row.source == TodayMealSource.Photo &&
                                // The server's own field first, the UI enum only
                                // as a fallback. Keying the loop on the enum
                                // alone tied it to whichever row builder happened
                                // to win, and when that changed the loop simply
                                // stopped running with nothing to show for it.
                                (
                                    row.estimateStatus.equals("estimating", true) ||
                                        row.status == TodayMealStatus.Estimating
                                    )
                        } == true
                }
                .distinctUntilChanged()
                .flatMapLatest { isEstimating ->
                    if (!isEstimating) {
                        emptyFlow()
                    } else {
                        flow {
                            while (true) {
                                delay(PhotoEstimateDayRefreshIntervalMs)
                                emit(Unit)
                            }
                        }
                    }
                }
                .collect {
                    dayRefreshTick.update { it + 1 }
                }
        }
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
                // A confirmed-but-not-yet-cached creation already exists on
                // the server; removing only the outbox row would resurrect it.
                if (row.recordId != null) {
                    outboxRepository.enqueue(OutboxKind.DeleteMeal(serverId = row.recordId))
                }
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
            pushGoalsSetupToBackend()
        }
    }

    fun skipGoalsOnboarding() {
        viewModelScope.launch {
            settingsStore.completeGoalsSetup()
            pushGoalsSetupToBackend()
        }
    }

    private fun requestSyncInBackground() {
        viewModelScope.launch {
            runCatching { syncRepository.requestSync() }
        }
    }

    private suspend fun pushGoalsSetupToBackend() {
        val goals = settingsStore.userGoals.firstOrNull()
        runCatching {
            goalsApi.updateGoals(
                kcalGoalPerDay = goals?.dailyKcal,
                proteinGoalGPerDay = goals?.dailyProteinG,
                carbGoalGPerDay = goals?.dailyCarbsG,
                fatGoalGPerDay = goals?.dailyFatG,
                goalsSetupCompleted = true,
            )
        }
    }
}

private data class TodayCoreState(
    val date: LocalDate,
    val cachedDay: CachedView<com.local.glucotracker.domain.model.DayState>,
    val outbox: List<OutboxItem>,
    val syncStatus: SyncStatus,
)

internal data class DatedValue<T>(
    val date: LocalDate,
    val value: T,
)

/**
 * Switch a date-bound stream without ever pairing a new date with the last
 * value emitted by the previous date's stream.
 */
@OptIn(ExperimentalCoroutinesApi::class)
internal fun <T> kotlinx.coroutines.flow.Flow<LocalDate>.switchDated(
    observe: (LocalDate) -> kotlinx.coroutines.flow.Flow<T>,
): kotlinx.coroutines.flow.Flow<DatedValue<T>> =
    flatMapLatest { date -> observe(date).map { DatedValue(date, it) } }

private data class NonTypicalDatePeriod(
    val startDate: LocalDate,
    val endDate: LocalDate,
) {
    fun contains(date: LocalDate): Boolean = date >= startDate && date <= endDate
}

private fun toTodayState(
    date: LocalDate,
    cachedDay: CachedView<com.local.glucotracker.domain.model.DayState>,
    outbox: List<OutboxItem>,
    syncStatus: SyncStatus,
    goals: UserGoals,
    softObservation: String?,
    isOnline: Boolean,
    typicalKcal14d: Int?,
): TodayState {
    val day = cachedDay.value
    val serverMeals = day?.meals.orEmpty()
    val acceptedMeals = serverMeals.filter { it.isAcceptedStatus() }
    val backendDrafts = serverMeals.filter { it.isDraftStatus() }
    // Confirmed creations stay visible until the accepted meal lands in the
    // day cache, so the row never blinks out between confirm and refetch.
    val activeOutbox = visibleTodayOutbox(outbox, acceptedMeals)
    val pendingCount = activeOutbox.count { item ->
        item.state.countsInSyncQueue() && item.affectsDay(date, acceptedMeals)
    }
    val visibleSyncStatus = syncStatus.copy(
        queueDepth = activeOutbox.count { item -> item.state.countsInSyncQueue() },
    )
    val rows = buildRows(date, acceptedMeals, backendDrafts, activeOutbox)
    val totals = day?.totals ?: DayTotals(
        date = date,
        kcal = 0.0,
        carbsG = 0.0,
        proteinG = 0.0,
        fatG = 0.0,
        fiberG = 0.0,
        mealCount = 0,
    )
    val effectiveGoals = goals.withHealthConnectKcalGoal(totals)

    if (day == null && rows.isEmpty()) {
        return TodayState.Empty(
            date = date,
            syncStatus = visibleSyncStatus,
            isRefreshing = cachedDay.isRefreshing,
            canGoNext = date < currentLocalDate(),
            softObservation = softObservation,
        )
    }

    return TodayState.Day(
        date = date,
        totals = totals,
        goals = effectiveGoals,
        rows = rows,
        pendingQueueCount = pendingCount,
        syncStatus = visibleSyncStatus,
        isRefreshing = cachedDay.isRefreshing,
        lastAddedId = null,
        canGoNext = date < currentLocalDate(),
        softObservation = softObservation,
        isOnline = isOnline,
        typicalKcal14d = typicalKcal14d,
    )
}

/**
 * Keep a photo creation visible after upload links it to a server draft. The
 * linked id is also used to suppress that draft below, so retaining the local
 * row does not create a duplicate. It is removed only after the accepted meal
 * has reached the local day cache.
 */
internal fun visibleTodayOutbox(
    outbox: List<OutboxItem>,
    acceptedMeals: List<Meal>,
): List<OutboxItem> =
    outbox
        .filter { it.state.isVisibleQueueState() || it.isConfirmedCreation() }
        .filterNot { item -> item.isAlreadyAccepted(acceptedMeals) }

private fun UserGoals.withHealthConnectKcalGoal(totals: DayTotals): UserGoals {
    val healthConnectGoal = totals.healthConnectTdeeKcal() ?: return this
    return copy(dailyKcal = healthConnectGoal)
}

private fun DayTotals.healthConnectTdeeKcal(): Int? =
    tdeeKcal
        ?.takeIf { activitySource in HealthConnectGoalSources && it > 0.0 }
        ?.roundToInt()

private val HealthConnectGoalSources = setOf(
    "health_connect_total",
    "health_connect_total_calories",
    "health_connect_active",
    "health_connect_steps",
)

// internal so the handover between the optimistic row and the server draft
// can be pinned by a test; it has now regressed twice.
internal fun buildRows(
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
    // Which row owns a photographed meal changes the moment the upload lands.
    //
    // Before that the optimistic outbox row is the better one: it has the local
    // file and can say "отправляем". After it, the server's own draft is, because
    // only that row carries `estimate_status` — the one field that says whether
    // the estimate is still running. Hiding the server draft for the whole life
    // of the outbox item left a confirmed upload rendering from a record that
    // knows nothing about the estimate, which is why it sat unchanged.
    val localDraftMealIds = outbox
        .filter { item -> item.state != OutboxState.Confirmed }
        .mapNotNull { item -> item.referencedDraftMealId() }
        .toSet()
    // The other half of the handover: once the day cache holds the meal, the
    // optimistic row has done its job. Without this the two would both render.
    val cachedMealIds = (acceptedMeals + backendDrafts).map { meal -> meal.id }.toSet()
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

    val pendingRows = outbox
        .filterNot { item ->
            item.kind is OutboxKind.CapturedMeal &&
                item.state == OutboxState.Confirmed &&
                item.referencedDraftMealId()?.let { it in cachedMealIds } == true
        }
        .mapNotNull { item ->
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
        // The upload's own state only while it is still in flight. It used to
        // be `outboxItem?.state.toMealStatus() ?: estimateStatus…`, but
        // `toMealStatus()` is an extension on a nullable and never returns
        // null, so the elvis never fired and the server's estimate status was
        // unreachable code. A confirmed upload therefore reported "accepted"
        // for a meal the server was still estimating — which also stopped the
        // poller that watches for an estimate in progress, so the row sat at
        // «оценка» until something else happened to refetch the day.
        status = outboxItem?.state
            ?.toMealStatus()
            ?.takeIf { it != TodayMealStatus.Accepted }
            ?: estimateStatus.toBackendDraftStatus(),
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
                recordId = serverIdOnSuccess,
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
                status = toPhotoCaptureMealStatus(),
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
                    // A confirmed capture remains here only while the accepted
                    // server meal has not reached the observable day cache yet.
                    acceptedMealVisible = false,
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

private fun OutboxItem.isConfirmedCreation(): Boolean =
    state == OutboxState.Confirmed &&
        (kind is OutboxKind.CreateMeal || kind is OutboxKind.CapturedMeal)

private fun OutboxItem.isAlreadyAccepted(acceptedMeals: List<Meal>): Boolean {
    val acceptedIds = acceptedMeals.map { it.id }.toSet()
    return when (val outboxKind = kind) {
        is OutboxKind.CapturedMeal -> draft?.id in acceptedIds ||
            (serverIdOnSuccess != null && serverIdOnSuccess in acceptedIds) ||
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

/**
 * A capture that reached the server is being estimated, not finished.
 *
 * `Confirmed` used to fall through to "accepted" here, on the reading that a
 * confirmed upload is a completed record. It is the opposite: the upload
 * finishing is the moment the estimate *starts*. This row now only survives
 * until the meal appears in the day cache, so there is no state in which
 * "estimating" can stick.
 */
private fun OutboxItem.toPhotoCaptureMealStatus(): TodayMealStatus =
    if (linkedMealId != null && state != OutboxState.Stuck) {
        TodayMealStatus.Estimating
    } else {
        state.toMealStatus()
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

private const val TypicalKcalWindowDays = 14
private const val TypicalKcalMinTrackedDays = 7
private const val PhotoEstimateDayRefreshIntervalMs = 4_000L

private fun List<Double>.medianKcalOrNull(minDays: Int): Int? {
    if (size < minDays) return null
    val sorted = sorted()
    val middle = sorted.size / 2
    val median = if (sorted.size % 2 == 0) {
        (sorted[middle - 1] + sorted[middle]) / 2.0
    } else {
        sorted[middle]
    }
    return median.roundToInt()
}
