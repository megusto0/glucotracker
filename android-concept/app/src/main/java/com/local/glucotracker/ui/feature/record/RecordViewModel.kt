package com.local.glucotracker.ui.feature.record

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.Meal
import com.local.glucotracker.domain.model.MealDraft
import com.local.glucotracker.domain.model.MealItem
import com.local.glucotracker.domain.model.MealItemPatchPayload
import com.local.glucotracker.domain.model.MealPatchPayload
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.domain.model.PostprandialResponse
import com.local.glucotracker.domain.model.hasRestaurantSource
import com.local.glucotracker.domain.repository.MealRepository
import com.local.glucotracker.domain.repository.OutboxRepository
import com.local.glucotracker.ui.format.PhotoProcessingUiState
import com.local.glucotracker.ui.format.mapOutboxAndMealToPhotoProcessingUiState
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDateTime
import kotlinx.datetime.LocalTime
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toInstant
import kotlinx.datetime.toLocalDateTime

sealed interface RecordState {
    data object Loading : RecordState
    data object NotFound : RecordState
    data class Loaded(
        val record: RecordUi,
        val outboxItem: OutboxItem?,
    ) : RecordState
}

data class RecordUi(
    val id: String,
    val serverId: String?,
    val outboxId: String?,
    val primaryItemId: String?,
    val isPending: Boolean,
    val title: String?,
    val eatenAt: Instant,
    val capturedAt: Instant?,
    val photo: Any?,
    val source: String,
    val status: RecordStatus,
    val kcal: Double?,
    val carbsG: Double?,
    val proteinG: Double?,
    val fatG: Double?,
    val fiberG: Double?,
    val weightGrams: Double?,
    val defaultWeightGrams: Double?,
    val nightscoutStatus: String?,
    val nightscoutSyncedAt: Instant?,
    val nightscoutLastAttemptAt: Instant?,
    val nightscoutError: String?,
    val postprandialResponse: PostprandialResponse?,
    val canCreatePortion: Boolean,
    val photoProcessing: PhotoProcessingUiState? = null,
)

enum class RecordStatus {
    Accepted,
    Draft,
    Queued,
    Uploading,
    Estimating,
    Stuck,
}

@HiltViewModel
@OptIn(ExperimentalCoroutinesApi::class)
class RecordViewModel @Inject constructor(
    private val mealRepository: MealRepository,
    private val outboxRepository: OutboxRepository,
) : ViewModel() {
    private val recordId = MutableStateFlow<String?>(null)

    val state = recordId
        .flatMapLatest { id ->
            if (id == null) {
                flowOf<RecordState>(RecordState.Loading)
            } else {
                outboxRepository.observe().flatMapLatest { outbox ->
                    val directOutboxItem = outbox.firstOrNull { it.id == id }
                    if (directOutboxItem?.isStandaloneRecord() == true) {
                        flowOf(directOutboxItem.toRecordState())
                    } else {
                        mealRepository.observeMeal(id).map { mealView ->
                            mealView.toRecordState(id = id, outbox = outbox)
                        }
                    }
                }
            }
        }
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5_000),
            initialValue = RecordState.Loading,
        )

    fun load(id: String) {
        recordId.value = id
    }

    fun updateTitle(title: String) {
        val loaded = state.value as? RecordState.Loaded ?: return
        val cleanTitle = title.trim().ifBlank { null }
        viewModelScope.launch {
            if (loaded.record.isPending) {
                loaded.outboxItem?.let { item ->
                    outboxRepository.enqueue(item.updatePendingDraft { draft -> draft.copy(title = cleanTitle) })
                }
            } else {
                loaded.record.serverId?.let { serverId ->
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
        val loaded = state.value as? RecordState.Loaded ?: return
        val nextInstant = loaded.record.eatenAt.replaceTime(value) ?: return
        viewModelScope.launch {
            if (loaded.record.isPending) {
                loaded.outboxItem?.let { item ->
                    outboxRepository.enqueue(item.updatePendingTime(nextInstant))
                }
            } else {
                loaded.record.serverId?.let { serverId ->
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
        val loaded = state.value as? RecordState.Loaded ?: return
        val grams = value.replace(',', '.').toDoubleOrNull()?.takeIf { it > 0.0 } ?: return
        viewModelScope.launch {
            if (loaded.record.isPending) {
                loaded.outboxItem?.let { item ->
                    outboxRepository.enqueue(item.updatePendingWeight(grams))
                }
            } else {
                val serverId = loaded.record.serverId ?: return@launch
                val itemId = loaded.record.primaryItemId ?: return@launch
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

    fun createPortion(grams: Double) {
        val record = (state.value as? RecordState.Loaded)?.record ?: return
        val serverId = record.serverId ?: return
        val itemId = record.primaryItemId ?: return
        viewModelScope.launch {
            outboxRepository.enqueue(
                OutboxKind.CopyMealItemWeight(
                    mealId = serverId,
                    itemId = itemId,
                    grams = grams,
                    eatenAt = Clock.System.now(),
                ),
            )
        }
    }

    fun deleteRecord() {
        val loaded = state.value as? RecordState.Loaded ?: return
        viewModelScope.launch {
            if (loaded.record.isPending) {
                loaded.record.outboxId?.let { outboxRepository.remove(it) }
            } else {
                loaded.record.serverId?.let { outboxRepository.enqueue(OutboxKind.DeleteMeal(serverId = it)) }
            }
        }
    }

    fun retryStuck() {
        val loaded = state.value as? RecordState.Loaded ?: return
        val item = loaded.outboxItem
        viewModelScope.launch {
            if (item != null) {
                outboxRepository.retry(item.id)
            } else if (loaded.record.photoProcessing?.canRetry == true) {
                loaded.record.serverId?.let { mealRepository.retryPhotoEstimate(it) }
            }
        }
    }
}

private fun CachedView<Meal>.toRecordState(id: String, outbox: List<OutboxItem>): RecordState {
    val meal = value ?: return if (isRefreshing) RecordState.Loading else RecordState.NotFound
    val activeOutboxItem = outbox.firstOrNull { item ->
        when (val kind = item.kind) {
            is OutboxKind.DeleteMeal -> kind.serverId == id
            is OutboxKind.EditMeal -> kind.serverId == id
            is OutboxKind.PatchMealItem -> kind.mealId == id
            is OutboxKind.CopyMealItemWeight -> false
            is OutboxKind.CreateMeal,
            is OutboxKind.CapturedMeal,
            -> false
            else -> false
        }
    }
    return RecordState.Loaded(
        record = meal.toRecordUi(activeOutboxItem),
        outboxItem = activeOutboxItem,
    )
}

private fun Meal.toRecordUi(activeOutboxItem: OutboxItem?): RecordUi {
    val editPatch = (activeOutboxItem?.kind as? OutboxKind.EditMeal)?.patch
    val itemPatch = (activeOutboxItem?.kind as? OutboxKind.PatchMealItem)?.patch
    val primaryItem = items.firstOrNull()
    val defaultStatus = if (status.equals("draft", ignoreCase = true)) {
        RecordStatus.Draft
    } else {
        RecordStatus.Accepted
    }
    return RecordUi(
        id = id,
        serverId = id,
        outboxId = activeOutboxItem?.id,
        primaryItemId = primaryItem?.id,
        isPending = false,
        title = editPatch?.title ?: title,
        eatenAt = editPatch?.eatenAt ?: eatenAt,
        capturedAt = null,
        photo = thumbnailUrl,
        source = displaySource(),
        status = activeOutboxItem?.state.toRecordStatus(defaultStatus = defaultStatus),
        kcal = totalKcal,
        carbsG = totalCarbsG,
        proteinG = totalProteinG,
        fatG = totalFatG,
        fiberG = totalFiberG,
        weightGrams = itemPatch?.grams ?: primaryItem?.grams,
        defaultWeightGrams = primaryItem?.grams ?: 100.0,
        nightscoutStatus = nightscoutSyncStatus,
        nightscoutSyncedAt = nightscoutSyncedAt,
        nightscoutLastAttemptAt = nightscoutLastAttemptAt,
        nightscoutError = nightscoutSyncError,
        postprandialResponse = postprandialResponse,
        canCreatePortion = defaultStatus == RecordStatus.Accepted && primaryItem != null,
        photoProcessing = mapOutboxAndMealToPhotoProcessingUiState(this),
    )
}

private fun OutboxItem.toRecordState(): RecordState =
    RecordState.Loaded(
        record = toRecordUi(),
        outboxItem = this,
    )

private fun OutboxItem.toRecordUi(): RecordUi {
    val draft = draftForDisplay()
    val capturedMeal = kind as? OutboxKind.CapturedMeal
    val createMeal = kind as? OutboxKind.CreateMeal
    val eatenAt = when (kind) {
        is OutboxKind.CreateMeal -> createMeal?.eatenAt
        is OutboxKind.CapturedMeal -> capturedMeal?.capturedAt
        is OutboxKind.CopyMealItemWeight,
        is OutboxKind.DeleteMeal,
        is OutboxKind.EditMeal,
        is OutboxKind.PatchMealItem,
        -> null
        else -> null
    } ?: draft?.eatenAt ?: createdAt
    return RecordUi(
        id = id,
        serverId = serverIdOnSuccess,
        outboxId = id,
        primaryItemId = null,
        isPending = true,
        title = draft?.title ?: capturedMeal?.optimisticName,
        eatenAt = eatenAt,
        capturedAt = capturedMeal?.capturedAt,
        photo = draft?.localPhotoPath ?: capturedMeal?.localPhotoPath,
        source = when (kind) {
            is OutboxKind.CapturedMeal -> capturedMeal?.source ?: "photo"
            is OutboxKind.CreateMeal -> createMeal?.displaySource() ?: "manual"
            is OutboxKind.CopyMealItemWeight,
            is OutboxKind.DeleteMeal,
            is OutboxKind.EditMeal,
            is OutboxKind.PatchMealItem,
            -> "manual"
            else -> "manual"
        },
        status = state.toRecordStatus(defaultStatus = RecordStatus.Queued),
        kcal = draft?.totalKcal,
        carbsG = draft?.totalCarbsG,
        proteinG = draft?.totalProteinG,
        fatG = draft?.totalFatG,
        fiberG = draft?.totalFiberG,
        weightGrams = draft?.weightGrams ?: createMeal?.items?.firstOrNull()?.grams,
        defaultWeightGrams = draft?.weightGrams ?: createMeal?.items?.firstOrNull()?.grams ?: 100.0,
        nightscoutStatus = null,
        nightscoutSyncedAt = null,
        nightscoutLastAttemptAt = null,
        nightscoutError = null,
        postprandialResponse = null,
        canCreatePortion = false,
        photoProcessing = mapOutboxAndMealToPhotoProcessingUiState(this),
    )
}

private fun OutboxItem.isStandaloneRecord(): Boolean =
    kind is OutboxKind.CreateMeal ||
        kind is OutboxKind.CapturedMeal

private fun OutboxItem.draftForDisplay(): MealDraft? =
    draft ?: (kind as? OutboxKind.CreateMeal)?.payload

private fun Meal.displaySource(): String =
    if (hasRestaurantSource()) {
        "restaurant"
    } else {
        source
    }

private fun OutboxKind.CreateMeal.displaySource(): String =
    if (hasRestaurantSource()) {
        "restaurant"
    } else {
        source
    }

private fun OutboxState?.toRecordStatus(defaultStatus: RecordStatus): RecordStatus =
    when (this) {
        OutboxState.Stuck -> RecordStatus.Stuck
        OutboxState.Uploading -> RecordStatus.Uploading
        OutboxState.Queued -> RecordStatus.Queued
        else -> defaultStatus
    }

private fun OutboxItem.updatePendingDraft(transform: (MealDraft) -> MealDraft): OutboxItem {
    val currentDraft = draftForDisplay() ?: return this
    val nextDraft = transform(currentDraft)
    val nextKind = when (val itemKind = kind) {
        is OutboxKind.CreateMeal -> itemKind.copy(payload = nextDraft)
        else -> itemKind
    }
    return copy(kind = nextKind, draft = nextDraft)
}

@Suppress("REDUNDANT_ELSE_IN_WHEN")
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
    val nextDraft = draft?.copy(eatenAt = eatenAt)
    return copy(kind = nextKind, draft = nextDraft)
}

@Suppress("REDUNDANT_ELSE_IN_WHEN")
private fun OutboxItem.updatePendingWeight(grams: Double): OutboxItem =
    updatePendingDraft { draft ->
        draft.copy(weightGrams = grams)
    }.let { item ->
        val nextKind = when (val itemKind = item.kind) {
            is OutboxKind.CreateMeal -> itemKind.copy(
                payload = itemKind.payload.copy(weightGrams = grams),
                items = itemKind.items.mapFirst { mealItem -> mealItem.copy(grams = grams) },
            )
            is OutboxKind.CopyMealItemWeight,
            is OutboxKind.DeleteMeal,
            is OutboxKind.EditMeal,
            is OutboxKind.PatchMealItem,
            is OutboxKind.CapturedMeal,
            -> itemKind
            else -> itemKind
        }
        item.copy(kind = nextKind)
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
