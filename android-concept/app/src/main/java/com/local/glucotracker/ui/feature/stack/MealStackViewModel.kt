package com.local.glucotracker.ui.feature.stack

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.data.sync.ConnectivityObserver
import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.DayState
import com.local.glucotracker.domain.model.Meal
import com.local.glucotracker.domain.model.MealItemPatchPayload
import com.local.glucotracker.domain.model.MealPatchPayload
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.domain.model.hasRestaurantSource
import com.local.glucotracker.domain.model.matchesCreateMeal
import com.local.glucotracker.domain.repository.OutboxRepository
import com.local.glucotracker.domain.repository.MealRepository
import com.local.glucotracker.domain.repository.TodayRepository
import com.local.glucotracker.ui.format.RowState
import com.local.glucotracker.ui.format.computeRowState
import com.local.glucotracker.ui.navigation.Route
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.LocalDateTime
import kotlinx.datetime.LocalTime
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toInstant
import kotlinx.datetime.toLocalDateTime
import kotlin.time.Duration.Companion.minutes

sealed interface MealStackUiState {
    data object Loading : MealStackUiState
    data class Empty(val date: LocalDate) : MealStackUiState
    data class Ready(
        val date: LocalDate,
        val cards: List<MealCard>,
        val currentIndex: Int,
        val isOnline: Boolean,
    ) : MealStackUiState
}

data class MealCard(
    val id: String,
    val serverId: String?,
    val outboxId: String?,
    val primaryItemId: String?,
    val outboxItem: OutboxItem?,
    val eatenAt: Instant,
    val title: String?,
    val source: MealCardSource,
    val photo: Any?,
    val kcal: Double?,
    val carbsG: Double?,
    val proteinG: Double?,
    val fatG: Double?,
    val fiberG: Double?,
    val weightGrams: Double?,
    val confidence: Double?,
    val state: MealCardState,
    val statusHint: MealCardStatusHint,
    val errorMessage: String?,
)

enum class MealCardSource {
    Photo,
    Restaurant,
    Pattern,
    Manual,
    Mixed,
    Text,
}

enum class MealCardState {
    Confirmed,
    Pending,
    EstimatingSlow,
    Stuck,
}

enum class MealCardStatusHint {
    None,
    Queued,
    Uploading,
    Estimating,
    EstimatingSlow,
    WaitingNetwork,
    Stuck,
}

@HiltViewModel
class MealStackViewModel @Inject constructor(
    private val todayRepository: TodayRepository,
    private val outboxRepository: OutboxRepository,
    private val mealRepository: MealRepository,
    connectivityObserver: ConnectivityObserver,
    savedStateHandle: SavedStateHandle,
) : ViewModel() {
    private val date = LocalDate.parse(
        checkNotNull(savedStateHandle.get<String>(Route.MealStack.ArgDate)),
    )
    private val focusedId = checkNotNull(savedStateHandle.get<String>(Route.MealStack.ArgFocusedId))
    private val currentCardId = MutableStateFlow(focusedId)

    val state = combine(
        todayRepository.observeDay(date),
        outboxRepository.observe(),
        connectivityObserver.observe(),
        currentCardId,
    ) { cachedDay, outbox, network, selectedId ->
        val cards = buildMealCards(
            date = date,
            cachedDay = cachedDay,
            outbox = outbox,
            isOnline = network.isConnected,
        )
        when {
            cards.isEmpty() && cachedDay.isRefreshing -> MealStackUiState.Loading
            cards.isEmpty() -> MealStackUiState.Empty(date)
            else -> {
                val selectedIndex = cards.indexOfFirst { it.id == selectedId }
                MealStackUiState.Ready(
                    date = date,
                    cards = cards,
                    currentIndex = selectedIndex.takeIf { it >= 0 } ?: 0,
                    isOnline = network.isConnected,
                )
            }
        }
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = MealStackUiState.Loading,
    )

    fun onPageChanged(cardId: String) {
        currentCardId.value = cardId
    }

    fun updateTitle(title: String) {
        val card = currentCard() ?: return
        val cleanTitle = title.trim().ifBlank { null }
        viewModelScope.launch {
            val item = card.outboxItem
            if (card.serverId == null && item != null) {
                outboxRepository.enqueue(item.updatePendingTitle(cleanTitle))
            } else {
                card.serverId?.let { serverId ->
                    outboxRepository.enqueue(
                        OutboxKind.EditMeal(
                            serverId = serverId,
                            patch = MealPatchPayload(title = cleanTitle),
                        ),
                    )
                }
            }
        }
    }

    fun updateTime(value: String) {
        val card = currentCard() ?: return
        val nextInstant = card.eatenAt.replaceTime(value) ?: return
        viewModelScope.launch {
            val item = card.outboxItem
            if (card.serverId == null && item != null) {
                outboxRepository.enqueue(item.updatePendingTime(nextInstant))
            } else {
                card.serverId?.let { serverId ->
                    outboxRepository.enqueue(
                        OutboxKind.EditMeal(
                            serverId = serverId,
                            patch = MealPatchPayload(eatenAt = nextInstant),
                        ),
                    )
                }
            }
        }
    }

    fun updateWeight(value: String) {
        val card = currentCard() ?: return
        val grams = value.replace(',', '.').toDoubleOrNull()?.takeIf { it > 0.0 } ?: return
        viewModelScope.launch {
            val item = card.outboxItem
            if (card.serverId == null && item != null) {
                outboxRepository.enqueue(item.updatePendingWeight(grams))
            } else {
                val serverId = card.serverId ?: return@launch
                val itemId = card.primaryItemId ?: return@launch
                outboxRepository.enqueue(
                    OutboxKind.PatchMealItem(
                        mealId = serverId,
                        itemId = itemId,
                        patch = MealItemPatchPayload(grams = grams),
                    ),
                )
            }
        }
    }

    fun retryCurrent() {
        val card = currentCard() ?: return
        viewModelScope.launch {
            val outboxId = card.outboxId
            if (outboxId != null) {
                outboxRepository.retry(outboxId)
            } else if (card.state == MealCardState.Stuck && card.source == MealCardSource.Photo) {
                card.serverId?.let { mealRepository.retryPhotoEstimate(it) }
            }
        }
    }

    private fun currentCard(): MealCard? =
        (state.value as? MealStackUiState.Ready)?.let { ready ->
            ready.cards.getOrNull(ready.currentIndex)
        }
}

private fun buildMealCards(
    date: LocalDate,
    cachedDay: CachedView<DayState>,
    outbox: List<OutboxItem>,
    isOnline: Boolean,
): List<MealCard> {
    val serverMeals = cachedDay.value?.meals.orEmpty()
    val acceptedMeals = serverMeals.filter { it.status.equals("accepted", ignoreCase = true) }
    val backendDrafts = serverMeals.filter { it.status.equals("draft", ignoreCase = true) }
    val activeOutbox = outbox.filter { it.state.isVisibleQueueState() }
        .filterNot { item -> item.isAlreadyAccepted(acceptedMeals) }
        .filterNot { it.isZombie }

    val deleteItemsByServerId = activeOutbox
        .mapNotNull { item -> (item.kind as? OutboxKind.DeleteMeal)?.serverId?.let { it to item } }
        .toMap()
    val editItemsByServerId = activeOutbox
        .mapNotNull { item -> (item.kind as? OutboxKind.EditMeal)?.serverId?.let { it to item } }
        .toMap()
    val itemPatchItemsByMealId = activeOutbox
        .mapNotNull { item -> (item.kind as? OutboxKind.PatchMealItem)?.mealId?.let { it to item } }
        .toMap()
    val localDraftMealIds = activeOutbox.mapNotNull { item -> item.referencedDraftMealId() }.toSet()

    val acceptedCards = acceptedMeals
        .filterNot { meal -> deleteItemsByServerId[meal.id]?.state?.let { it != OutboxState.Stuck } == true }
        .map { meal ->
            val activeItem = deleteItemsByServerId[meal.id]
                ?: editItemsByServerId[meal.id]
                ?: itemPatchItemsByMealId[meal.id]
            meal.toMealCard(
                activeItem = activeItem,
                isBackendDraft = false,
                isOnline = isOnline,
            )
        }

    val backendDraftCards = backendDrafts
        .filter { meal -> meal.eatenAt.localDate() == date }
        .filterNot { meal -> deleteItemsByServerId[meal.id]?.state?.let { it != OutboxState.Stuck } == true }
        .filterNot { meal -> meal.id in localDraftMealIds }
        .map { meal ->
            val activeItem = deleteItemsByServerId[meal.id]
                ?: editItemsByServerId[meal.id]
                ?: itemPatchItemsByMealId[meal.id]
            meal.toMealCard(
                activeItem = activeItem,
                isBackendDraft = true,
                isOnline = isOnline,
            )
        }

    val pendingCards = activeOutbox.mapNotNull { item -> item.toPendingCard(date, isOnline) }

    return (acceptedCards + backendDraftCards + pendingCards)
        .filter { card -> card.eatenAt.localDate() == date }
        .sortedByDescending { it.eatenAt }
}

private fun Meal.toMealCard(
    activeItem: OutboxItem?,
    isBackendDraft: Boolean,
    isOnline: Boolean,
): MealCard {
    val editPatch = (activeItem?.kind as? OutboxKind.EditMeal)?.patch
    val itemPatch = (activeItem?.kind as? OutboxKind.PatchMealItem)?.patch
    val primaryItem = items.firstOrNull()
    val hint = activeItem?.toStatusHint(isOnline)
        ?: (if (isBackendDraft) backendDraftHint() else null)
        ?: MealCardStatusHint.None
    return MealCard(
        id = id,
        serverId = id,
        outboxId = activeItem?.id,
        primaryItemId = primaryItem?.id,
        outboxItem = activeItem,
        eatenAt = editPatch?.eatenAt ?: eatenAt,
        title = editPatch?.title ?: title,
        source = toMealCardSource(),
        photo = thumbnailUrl,
        kcal = totalKcal,
        carbsG = totalCarbsG,
        proteinG = totalProteinG,
        fatG = totalFatG,
        fiberG = totalFiberG,
        weightGrams = itemPatch?.grams ?: primaryItem?.grams,
        confidence = confidence,
        state = hint.toCardState(isBackendDraft = isBackendDraft),
        statusHint = hint,
        errorMessage = activeItem?.errorMessage ?: estimateError.takeIf { isBackendDraft },
    )
}

private fun OutboxItem.toPendingCard(date: LocalDate, isOnline: Boolean): MealCard? {
    return when (val itemKind = kind) {
        is OutboxKind.CreateMeal -> {
            if (itemKind.eatenAt.localDate() != date) return null
            val draft = itemKind.payload
            MealCard(
                id = id,
                serverId = null,
                outboxId = id,
                primaryItemId = null,
                outboxItem = this,
                eatenAt = itemKind.eatenAt,
                title = draft.title,
                source = itemKind.toMealCardSource(),
                photo = draft.localPhotoPath,
                kcal = draft.totalKcal,
                carbsG = draft.totalCarbsG,
                proteinG = draft.totalProteinG,
                fatG = draft.totalFatG,
                fiberG = draft.totalFiberG,
                weightGrams = draft.weightGrams ?: itemKind.items.firstOrNull()?.grams,
                confidence = null,
                state = toStatusHint(isOnline).toCardState(isBackendDraft = true),
                statusHint = toStatusHint(isOnline),
                errorMessage = errorMessage,
            )
        }
        is OutboxKind.CapturedMeal -> {
            if (itemKind.capturedAt.localDate() != date) return null
            MealCard(
                id = id,
                serverId = null,
                outboxId = id,
                primaryItemId = null,
                outboxItem = this,
                eatenAt = itemKind.capturedAt,
                title = draft?.title ?: itemKind.optimisticName,
                source = MealCardSource.Photo,
                photo = draft?.localPhotoPath ?: itemKind.localPhotoPath,
                kcal = draft?.totalKcal,
                carbsG = draft?.totalCarbsG,
                proteinG = draft?.totalProteinG,
                fatG = draft?.totalFatG,
                fiberG = draft?.totalFiberG,
                weightGrams = draft?.weightGrams ?: itemKind.optimisticWeightG?.toDouble(),
                confidence = null,
                state = toStatusHint(isOnline).toCardState(isBackendDraft = true),
                statusHint = toStatusHint(isOnline),
                errorMessage = errorMessage,
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

private fun OutboxItem.toStatusHint(isOnline: Boolean): MealCardStatusHint =
    when (
        val rowState = computeRowState(
            item = this,
            isOnline = isOnline,
        )
    ) {
        RowState.JustQueued -> MealCardStatusHint.Queued
        RowState.TryingNow -> MealCardStatusHint.Uploading
        is RowState.RetryInSeconds,
        is RowState.RetryInMinutes,
        -> MealCardStatusHint.Queued
        RowState.Estimating -> MealCardStatusHint.Estimating
        RowState.EstimatingSlow -> MealCardStatusHint.EstimatingSlow
        is RowState.Stuck -> MealCardStatusHint.Stuck
        RowState.WaitingNetwork -> MealCardStatusHint.WaitingNetwork
    }

private fun Meal.backendDraftHint(): MealCardStatusHint? =
    when (estimateStatus?.lowercase()) {
        "estimating" -> {
            if (Clock.System.now() - updatedAt > 10.minutes) {
                MealCardStatusHint.EstimatingSlow
            } else {
                MealCardStatusHint.Estimating
            }
        }
        "failed",
        "timeout",
        "error",
        -> MealCardStatusHint.Stuck
        else -> null
    }

private fun MealCardStatusHint.toCardState(isBackendDraft: Boolean): MealCardState =
    when (this) {
        MealCardStatusHint.None -> if (isBackendDraft) MealCardState.Pending else MealCardState.Confirmed
        MealCardStatusHint.Stuck -> MealCardState.Stuck
        MealCardStatusHint.EstimatingSlow -> MealCardState.EstimatingSlow
        else -> MealCardState.Pending
    }

private fun OutboxState.isVisibleQueueState(): Boolean =
    this == OutboxState.Queued ||
        this == OutboxState.Uploading ||
        this == OutboxState.Stuck

private fun OutboxItem.isAlreadyAccepted(acceptedMeals: List<Meal>): Boolean {
    val acceptedIds = acceptedMeals.map { it.id }.toSet()
    return when (val itemKind = kind) {
        is OutboxKind.CapturedMeal -> draft?.id in acceptedIds ||
            (attempts > 0 && acceptedMeals.any { meal -> meal.matchesPhotoCapture(itemKind.capturedAt) })
        is OutboxKind.CreateMeal -> (serverIdOnSuccess != null && serverIdOnSuccess in acceptedIds) ||
            (attempts > 0 && acceptedMeals.any { meal -> meal.matchesCreateMeal(itemKind) })
        else -> false
    }
}

private fun OutboxItem.referencedDraftMealId(): String? =
    when (val itemKind = kind) {
        is OutboxKind.CapturedMeal -> draft?.id ?: serverIdOnSuccess
        else -> null
    }

private fun String.toMealCardSource(): MealCardSource =
    when (lowercase()) {
        "photo",
        "photo_estimate",
        "gallery",
        -> MealCardSource.Photo
        "restaurant",
        "restaurant_db",
        -> MealCardSource.Restaurant
        "pattern",
        "template",
        -> MealCardSource.Pattern
        "manual" -> MealCardSource.Manual
        "text" -> MealCardSource.Text
        else -> MealCardSource.Mixed
    }

private fun Meal.toMealCardSource(): MealCardSource =
    if (hasRestaurantSource()) {
        MealCardSource.Restaurant
    } else {
        source.toMealCardSource()
    }

private fun OutboxKind.CreateMeal.toMealCardSource(): MealCardSource =
    if (hasRestaurantSource()) {
        MealCardSource.Restaurant
    } else {
        source.toMealCardSource()
    }

private fun Meal.matchesPhotoCapture(capturedAt: Instant): Boolean =
    source.toMealCardSource() == MealCardSource.Photo &&
        eatenAt.toLocalDateTime(TimeZone.currentSystemDefault()).let { mealTime ->
            val capturedTime = capturedAt.toLocalDateTime(TimeZone.currentSystemDefault())
            mealTime.date == capturedTime.date &&
                mealTime.hour == capturedTime.hour &&
                mealTime.minute == capturedTime.minute
        }

private fun OutboxItem.updatePendingTitle(title: String?): OutboxItem {
    val nextKind = when (val itemKind = kind) {
        is OutboxKind.CreateMeal -> itemKind.copy(payload = itemKind.payload.copy(title = title))
        is OutboxKind.CapturedMeal -> itemKind.copy(optimisticName = title)
        is OutboxKind.CopyMealItemWeight,
        is OutboxKind.DeleteMeal,
        is OutboxKind.EditMeal,
        is OutboxKind.PatchMealItem,
        -> itemKind
        else -> itemKind
    }
    return copy(kind = nextKind, draft = draft?.copy(title = title))
}

private fun OutboxItem.updatePendingTime(eatenAt: Instant): OutboxItem {
    val nextKind = when (val itemKind = kind) {
        is OutboxKind.CreateMeal -> itemKind.copy(
            eatenAt = eatenAt,
            payload = itemKind.payload.copy(eatenAt = eatenAt),
        )
        is OutboxKind.CapturedMeal -> itemKind.copy(capturedAt = eatenAt)
        is OutboxKind.CopyMealItemWeight,
        is OutboxKind.DeleteMeal,
        is OutboxKind.EditMeal,
        is OutboxKind.PatchMealItem,
        -> itemKind
        else -> itemKind
    }
    return copy(kind = nextKind, draft = draft?.copy(eatenAt = eatenAt))
}

private fun OutboxItem.updatePendingWeight(grams: Double): OutboxItem {
    val nextKind = when (val itemKind = kind) {
        is OutboxKind.CreateMeal -> itemKind.copy(
            payload = itemKind.payload.copy(weightGrams = grams),
            items = itemKind.items.mapFirst { mealItem -> mealItem.copy(grams = grams) },
        )
        is OutboxKind.CapturedMeal,
        is OutboxKind.CopyMealItemWeight,
        is OutboxKind.DeleteMeal,
        is OutboxKind.EditMeal,
        is OutboxKind.PatchMealItem,
        -> itemKind
        else -> itemKind
    }
    return copy(kind = nextKind, draft = draft?.copy(weightGrams = grams))
}

private fun <T> List<T>.mapFirst(transform: (T) -> T): List<T> =
    mapIndexed { index, item -> if (index == 0) transform(item) else item }

private fun Instant.replaceTime(value: String): Instant? {
    val parts = value.trim().split(':')
    if (parts.size != 2) return null
    val hour = parts[0].toIntOrNull()?.takeIf { it in 0..23 } ?: return null
    val minute = parts[1].toIntOrNull()?.takeIf { it in 0..59 } ?: return null
    val zone = TimeZone.currentSystemDefault()
    val date = toLocalDateTime(zone).date
    return LocalDateTime(date, LocalTime(hour, minute)).toInstant(zone)
}

private fun Instant.localDate(): LocalDate =
    toLocalDateTime(TimeZone.currentSystemDefault()).date
