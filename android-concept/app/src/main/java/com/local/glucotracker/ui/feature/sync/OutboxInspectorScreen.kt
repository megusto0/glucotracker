package com.local.glucotracker.ui.feature.sync

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.R
import com.local.glucotracker.data.sync.ConnectivityObserver
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.domain.repository.OutboxRepository
import com.local.glucotracker.domain.repository.SyncRepository
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTKicker
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.design.primitives.GTPhotoProcessingPipeline
import com.local.glucotracker.ui.design.primitives.GTPhotoProcessingProgressBar
import com.local.glucotracker.ui.design.primitives.GTPhotoSlot
import com.local.glucotracker.ui.format.PhotoProcessingStage
import com.local.glucotracker.ui.format.PhotoProcessingUiState
import com.local.glucotracker.ui.format.RowState
import com.local.glucotracker.ui.format.computeRowState
import com.local.glucotracker.ui.format.mapOutboxAndMealToPhotoProcessingUiState
import com.local.glucotracker.ui.format.pluralizeRecord
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime
import kotlin.time.Duration.Companion.minutes

data class OutboxInspectorState(
    val active: List<OutboxItem> = emptyList(),
    val stuck: List<OutboxItem> = emptyList(),
    val isOnline: Boolean = true,
) {
    val total: Int = active.size + stuck.size
}

@HiltViewModel
class OutboxInspectorViewModel @Inject constructor(
    private val outboxRepository: OutboxRepository,
    private val syncRepository: SyncRepository,
    private val connectivityObserver: ConnectivityObserver,
) : ViewModel() {
    private val isOnline = connectivityObserver.observe()
        .map { it.isConnected }
        .stateIn(viewModelScope, SharingStarted.Eagerly, true)

    val state = combine(outboxRepository.observe(), isOnline) { items, online ->
        OutboxInspectorState(
            active = items.filter { it.state.isActive && !it.isZombie },
            stuck = items.filter { it.state == OutboxState.Stuck && !it.isZombie },
            isOnline = online,
        )
    }
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5_000),
            initialValue = OutboxInspectorState(),
        )

    fun retry(id: String) {
        viewModelScope.launch {
            outboxRepository.retry(id)
            runCatching { syncRepository.requestSync() }
        }
    }

    fun delete(id: String) {
        viewModelScope.launch { outboxRepository.remove(id) }
    }
}

@Composable
fun OutboxInspectorRoute(
    focusId: String?,
    onBack: () -> Unit,
    onOpenJournal: (LocalDate) -> Unit,
    viewModel: OutboxInspectorViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    OutboxInspectorScreen(
        state = state,
        focusId = focusId,
        onBack = onBack,
        onRetry = viewModel::retry,
        onDelete = viewModel::delete,
        onOpenJournal = onOpenJournal,
    )
}

@Composable
fun OutboxInspectorScreen(
    state: OutboxInspectorState,
    focusId: String?,
    onBack: () -> Unit,
    onRetry: (String) -> Unit,
    onDelete: (String) -> Unit,
    onOpenJournal: (LocalDate) -> Unit,
    modifier: Modifier = Modifier,
) {
    var deleteCandidate by remember { mutableStateOf<OutboxItem?>(null) }
    val listState = rememberLazyListState()
    val allItems = state.active + state.stuck
    val activePhotoQueue = state.active
        .filter { item -> item.kind is OutboxKind.CapturedMeal }
        .sortedBy { item -> item.createdAt }
    val activePhotoQueueSize = activePhotoQueue.size
    val activePhotoQueuePositions = activePhotoQueue
        .mapIndexed { index, item -> item.id to index + 1 }
        .toMap()

    LaunchedEffect(focusId, allItems) {
        val index = allItems.indexOfFirst { it.id == focusId }
        if (index >= 0) listState.animateScrollToItem(index + 2)
    }

    deleteCandidate?.let { item ->
        DeleteOutboxItemSheet(
            onDismiss = { deleteCandidate = null },
            onConfirm = {
                onDelete(item.id)
                deleteCandidate = null
            },
        )
    }

    LazyColumn(
        state = listState,
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg)
            .padding(horizontal = 18.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item {
            OutboxInspectorHeader(
                total = state.total,
                onBack = onBack,
            )
        }
        if (state.total == 0) {
            item {
                Text(
                    text = stringResource(R.string.outbox_empty),
                    color = GT.colors.muted,
                    style = GT.type.sansBody,
                    modifier = Modifier.padding(top = 24.dp),
                )
            }
        }
        if (state.active.isNotEmpty()) {
            item { GTKicker(text = stringResource(R.string.outbox_active_header, state.active.size)) }
            items(state.active, key = { it.id }) { item ->
                OutboxItemRow(
                    item = item,
                    isOnline = state.isOnline,
                    photoProcessing = mapOutboxAndMealToPhotoProcessingUiState(
                        outboxItem = item,
                        queuePosition = activePhotoQueuePositions[item.id],
                        queueSize = activePhotoQueueSize.takeIf { it > 0 },
                    ),
                    onOpenJournal = onOpenJournal,
                    onRetry = onRetry,
                    onDelete = { deleteCandidate = item },
                )
            }
        }
        if (state.stuck.isNotEmpty()) {
            item { GTKicker(text = stringResource(R.string.outbox_stuck_header, state.stuck.size)) }
            items(state.stuck, key = { it.id }) { item ->
                OutboxItemRow(
                    item = item,
                    isOnline = state.isOnline,
                    photoProcessing = mapOutboxAndMealToPhotoProcessingUiState(item),
                    onOpenJournal = onOpenJournal,
                    onRetry = onRetry,
                    onDelete = { deleteCandidate = item },
                )
            }
        }
    }
}

@Composable
private fun OutboxInspectorHeader(total: Int, onBack: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = stringResource(R.string.outbox_back),
            modifier = Modifier
                .heightIn(min = GT.space.touch)
                .clickable(onClick = onBack)
                .padding(end = 12.dp, top = 12.dp, bottom = 12.dp),
            color = GT.colors.ink,
            style = GT.type.sansLabel,
        )
        Text(
            text = stringResource(R.string.outbox_title),
            color = GT.colors.ink,
            style = GT.type.serifSection,
        )
        Spacer(Modifier.weight(1f))
        Text(
            text = pluralizeRecord(total),
            color = GT.colors.muted,
            style = GT.type.monoLabel,
        )
    }
    GTHairlineDivider()
}

@Composable
private fun OutboxItemRow(
    item: OutboxItem,
    isOnline: Boolean,
    photoProcessing: PhotoProcessingUiState?,
    onOpenJournal: (LocalDate) -> Unit,
    onRetry: (String) -> Unit,
    onDelete: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.Top) {
            GTPhotoSlot(model = item.photoModel, modifier = Modifier.size(34.dp))
            Column(
                modifier = Modifier
                    .weight(1f)
                    .padding(start = 10.dp, end = 10.dp),
            ) {
                Text(
                    text = outboxItemName(item),
                    color = GT.colors.ink,
                    style = GT.type.sansLabel,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = photoProcessing?.statusText ?: outboxStateLine(item, isOnline),
                    color = if (photoProcessing?.stage == PhotoProcessingStage.Stuck ||
                        item.state == OutboxState.Stuck
                    ) {
                        GT.colors.warn
                    } else {
                        GT.colors.muted
                    },
                    style = GT.type.monoLabel,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = outboxAgeLine(item),
                    color = GT.colors.muted,
                    style = GT.type.monoLabel,
                )
            }
            Text(
                text = item.captureTimeText,
                color = GT.colors.muted,
                style = GT.type.monoLabel,
            )
        }
        if (photoProcessing != null) {
            if (photoProcessing.stage == PhotoProcessingStage.Uploading) {
                GTPhotoProcessingProgressBar(progress = photoProcessing.uploadProgress)
            }
            GTPhotoProcessingPipeline(state = photoProcessing)
            photoProcessing.helperText?.let { helper ->
                Text(
                    text = helper,
                    color = GT.colors.muted,
                    style = GT.type.sansLabel,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        if (item.state == OutboxState.Stuck || item.state.isActive) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                GTOutlineButton(
                    text = stringResource(R.string.outbox_retry),
                    onClick = { onRetry(item.id) },
                )
                GTOutlineButton(
                    text = stringResource(R.string.outbox_open_journal),
                    onClick = { onOpenJournal(item.captureDate) },
                )
                GTOutlineButton(
                    text = stringResource(R.string.outbox_delete),
                    onClick = onDelete,
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DeleteOutboxItemSheet(
    onDismiss: () -> Unit,
    onConfirm: () -> Unit,
) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(),
        containerColor = GT.colors.surface,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp, vertical = 14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = stringResource(R.string.outbox_delete_confirm_title),
                color = GT.colors.ink,
                style = GT.type.serifSection,
            )
            Text(
                text = stringResource(R.string.outbox_delete_confirm_body),
                color = GT.colors.ink2,
                style = GT.type.sansBody,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                GTOutlineButton(text = stringResource(R.string.record_delete_cancel), onClick = onDismiss)
                GTOutlineButton(text = stringResource(R.string.outbox_delete), onClick = onConfirm)
            }
        }
    }
}

private val OutboxState.isActive: Boolean
    get() = this == OutboxState.Queued || this == OutboxState.Uploading

@Composable
private fun outboxItemName(item: OutboxItem): String =
    when (val itemKind = item.kind) {
        is OutboxKind.CapturedMeal -> itemKind.optimisticName ?: item.draft?.title ?: ""
        is OutboxKind.CreateMeal -> itemKind.payload.title ?: ""
        is OutboxKind.EditMeal -> itemKind.patch.title ?: ""
        else -> ""
    }.ifBlank { stringResource(R.string.outbox_untitled) }

private val OutboxItem.photoModel: Any?
    get() = when (val itemKind = kind) {
        is OutboxKind.CapturedMeal -> itemKind.localPhotoPath
        is OutboxKind.CreateMeal -> itemKind.payload.localPhotoPath
        else -> null
    }

private val OutboxItem.captureInstant: Instant
    get() = when (val itemKind = kind) {
        is OutboxKind.CapturedMeal -> itemKind.capturedAt
        is OutboxKind.CreateMeal -> itemKind.eatenAt
        is OutboxKind.CopyMealItemWeight -> itemKind.eatenAt
        else -> createdAt
    }

private val OutboxItem.captureDate: LocalDate
    get() = captureInstant.toLocalDateTime(TimeZone.currentSystemDefault()).date

private val OutboxItem.captureTimeText: String
    get() = captureInstant.toLocalDateTime(TimeZone.currentSystemDefault()).time.let { time ->
        "${time.hour.toString().padStart(2, '0')}:${time.minute.toString().padStart(2, '0')}"
    }

@Composable
private fun outboxStateLine(item: OutboxItem, isOnline: Boolean): String {
    val rowState = computeRowState(item, isOnline)
    return when (rowState) {
        is RowState.JustQueued -> stringResource(R.string.outbox_state_just_queued)
        is RowState.TryingNow -> stringResource(R.string.outbox_state_trying_now)
        is RowState.RetryInSeconds -> stringResource(R.string.outbox_state_retry_in, rowState.seconds)
        is RowState.RetryInMinutes -> stringResource(R.string.outbox_state_retry_in_min, rowState.minutes)
        is RowState.Estimating -> stringResource(R.string.outbox_state_estimating)
        is RowState.EstimatingSlow -> stringResource(R.string.outbox_state_estimating_slow)
        is RowState.Stuck -> rowState.errorMessage
            ?: stringResource(R.string.outbox_state_stuck)
        is RowState.WaitingNetwork -> stringResource(R.string.outbox_state_waiting)
    }
}

@Composable
private fun outboxAgeLine(item: OutboxItem): String {
    val duration = Clock.System.now() - item.createdAt
    val minutes = duration.inWholeMinutes.coerceAtLeast(0)
    val hours = duration.inWholeHours
    return if (hours >= 1) {
        stringResource(R.string.outbox_age_hours, hours)
    } else {
        stringResource(R.string.outbox_age_minutes, minutes)
    }
}
