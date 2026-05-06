package com.local.glucotracker.ui.feature.capture

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import coil3.compose.AsyncImage
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTHintBox
import com.local.glucotracker.ui.design.primitives.GTIconButton
import com.local.glucotracker.ui.design.primitives.GTKicker
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.design.primitives.GTPrimaryButton
import com.local.glucotracker.ui.format.formatGrams
import com.local.glucotracker.ui.format.formatKcal
import java.io.File
import kotlinx.datetime.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

@Composable
fun DraftRoute(
    outboxId: String,
    onFinished: () -> Unit,
    modifier: Modifier = Modifier,
    draftViewModel: DraftViewModel = hiltViewModel(),
    captureViewModel: CaptureViewModel = hiltViewModel(),
) {
    LaunchedEffect(outboxId) {
        draftViewModel.loadDraft(outboxId)
    }

    val draftState by draftViewModel.draftState.collectAsState()

    DraftScreen(
        draftState = draftState,
        onAccept = { estimateId, eatenAt, weightOverride ->
            captureViewModel.acceptDraft(outboxId, estimateId, eatenAt, weightOverride)
            onFinished()
        },
        onReject = {
            captureViewModel.rejectDraft(outboxId)
            onFinished()
        },
        onRetry = draftViewModel::retryCurrent,
        onClose = onFinished,
        modifier = modifier,
    )
}

@Composable
private fun DraftScreen(
    draftState: DraftUiState,
    onAccept: (estimateId: String, eatenAt: Instant, weightOverride: Double?) -> Unit,
    onReject: () -> Unit,
    onRetry: () -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier.fillMaxSize().background(GT.colors.bg)) {
        DraftTopBar(onClose = onClose)
        GTHairlineDivider()

        when (draftState) {
            DraftUiState.Loading -> {
                DraftMessage(
                    title = stringResource(R.string.draft_loading_title),
                    body = stringResource(R.string.draft_loading_body),
                    modifier = Modifier.weight(1f),
                )
            }
            DraftUiState.NotFound -> {
                DraftMessage(
                    title = stringResource(R.string.draft_not_found),
                    body = stringResource(R.string.draft_can_close_hint),
                    action = onClose,
                    modifier = Modifier.weight(1f),
                )
            }
            is DraftUiState.Loaded -> {
                val draft = draftState.draft
                val outboxItem = draftState.outboxItem
                if (draft != null) {
                    DraftContent(
                        draft = draft,
                        isEstimateReady = draftState.isEstimateReady,
                        photoPath = draft.localPhotoPath
                            ?: (outboxItem.kind as? OutboxKind.PhotoEstimateRequest)?.localPhotoPath,
                        onAccept = onAccept,
                        onReject = onReject,
                        modifier = Modifier.weight(1f),
                    )
                } else {
                    DraftWaitingContent(
                        outboxItem = outboxItem,
                        photoPath = (outboxItem.kind as? OutboxKind.PhotoEstimateRequest)?.localPhotoPath,
                        onReject = onReject,
                        onRetry = onRetry,
                        onClose = onClose,
                        modifier = Modifier.weight(1f),
                    )
                }
            }
        }
    }
}

@Composable
private fun DraftTopBar(
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(GT.space.touch)
            .background(GT.colors.surface)
            .padding(horizontal = GT.space.sm),
        contentAlignment = Alignment.CenterStart,
    ) {
        GTIconButton(onClick = onClose) {
            Text(
                text = stringResource(R.string.draft_close_icon),
                color = GT.colors.ink2,
                style = GT.type.sansLabel,
            )
        }
        Text(
            text = stringResource(R.string.draft_title),
            modifier = Modifier.align(Alignment.Center),
            color = GT.colors.ink,
            style = GT.type.sansLabel,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun DraftMessage(
    title: String,
    body: String,
    modifier: Modifier = Modifier,
    action: (() -> Unit)? = null,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(GT.space.lg),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = title,
            color = GT.colors.ink,
            style = GT.type.serifSection,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        Text(
            text = body,
            modifier = Modifier.padding(top = GT.space.sm),
            color = GT.colors.muted,
            style = GT.type.sansBody,
        )
        if (action != null) {
            GTOutlineButton(
                text = stringResource(R.string.draft_close_to_journal),
                onClick = action,
                modifier = Modifier
                    .padding(top = GT.space.lg)
                    .widthIn(min = 160.dp),
            )
        }
    }
}

@Composable
private fun DraftWaitingContent(
    outboxItem: OutboxItem,
    photoPath: String?,
    onReject: () -> Unit,
    onRetry: () -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val photoRequest = outboxItem.kind as? OutboxKind.PhotoEstimateRequest
    val canRetry = outboxItem.errorMessage != null ||
        (outboxItem.state == OutboxState.Queued && outboxItem.attempts > 0)

    Column(
        modifier = modifier
            .fillMaxWidth()
            .verticalScroll(rememberScrollState())
            .padding(GT.space.lg),
        verticalArrangement = Arrangement.spacedBy(GT.space.md),
    ) {
        DraftPhotoPreview(photoPath = photoPath, height = 230.dp)

        photoRequest?.capturedAt?.let { capturedAt ->
            GTKicker(text = stringResource(R.string.draft_captured_at, formatDateTime(capturedAt)))
        }

        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(GT.colors.surface, GT.shapes.card)
                .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
                .padding(GT.space.md),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(GT.space.sm)) {
                DraftEstimateProgress(state = outboxItem.state)
                Text(
                    text = draftStatusTitle(outboxItem.state),
                    color = GT.colors.ink,
                    style = GT.type.serifSection,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = draftStatusBody(outboxItem.state),
                    color = GT.colors.ink2,
                    style = GT.type.sansBody,
                )
                DraftAttemptMeta(outboxItem = outboxItem)
            }
        }

        outboxItem.errorMessage?.takeIf { it.isNotBlank() }?.let { message ->
            Text(
                text = stringResource(R.string.draft_error, message),
                color = GT.colors.warn,
                style = GT.type.sansLabel,
            )
        }

        GTHintBox(text = stringResource(R.string.draft_can_close_hint))

        if (canRetry) {
            GTOutlineButton(
                text = stringResource(R.string.draft_retry),
                onClick = onRetry,
                modifier = Modifier.fillMaxWidth(),
            )
        }

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(GT.space.md),
        ) {
            GTOutlineButton(
                text = stringResource(R.string.draft_close_to_journal),
                onClick = onClose,
                modifier = Modifier.weight(1f),
            )
            GTOutlineButton(
                text = stringResource(R.string.draft_reject),
                onClick = onReject,
                modifier = Modifier.weight(1f),
            )
        }
    }
}

@Composable
private fun DraftPhotoPreview(
    photoPath: String?,
    height: androidx.compose.ui.unit.Dp,
    modifier: Modifier = Modifier,
) {
    if (photoPath == null) return
    AsyncImage(
        model = File(photoPath),
        contentDescription = null,
        modifier = modifier
            .fillMaxWidth()
            .height(height)
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card),
        contentScale = ContentScale.Crop,
    )
}

@Composable
private fun DraftEstimateProgress(state: OutboxState) {
    val completedSteps = state.completedEstimateSteps()
    val activeColor = if (state == OutboxState.Conflict) GT.colors.warn else GT.colors.accent

    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        repeat(4) { index ->
            Box(
                modifier = Modifier
                    .weight(1f)
                    .height(2.dp)
                    .background(
                        if (index < completedSteps) activeColor else GT.colors.hairline,
                        GT.shapes.tag,
                    ),
            )
        }
    }
}

@Composable
private fun DraftAttemptMeta(outboxItem: OutboxItem) {
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(
            text = stringResource(R.string.draft_attempts, outboxItem.attempts),
            color = GT.colors.muted,
            style = GT.type.monoLabel,
            maxLines = 1,
        )
        outboxItem.lastAttemptAt?.let { lastAttemptAt ->
            Text(
                text = stringResource(R.string.draft_last_attempt, formatClock(lastAttemptAt)),
                color = GT.colors.muted,
                style = GT.type.monoLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun draftStatusTitle(state: OutboxState): String = when (state) {
    OutboxState.Queued -> stringResource(R.string.draft_status_queued)
    OutboxState.Sending -> stringResource(R.string.draft_status_sending)
    OutboxState.Sent -> stringResource(R.string.draft_status_sent)
    OutboxState.Conflict -> stringResource(R.string.draft_status_conflict)
    OutboxState.Estimating -> stringResource(R.string.draft_status_estimating)
    OutboxState.EstimateReady -> stringResource(R.string.draft_status_ready)
}

@Composable
private fun draftStatusBody(state: OutboxState): String = when (state) {
    OutboxState.Queued -> stringResource(R.string.draft_body_queued)
    OutboxState.Sending -> stringResource(R.string.draft_body_sending)
    OutboxState.Sent -> stringResource(R.string.draft_body_sent)
    OutboxState.Conflict -> stringResource(R.string.draft_body_conflict)
    OutboxState.Estimating -> stringResource(R.string.draft_body_estimating)
    OutboxState.EstimateReady -> stringResource(R.string.draft_body_ready)
}

private fun OutboxState.completedEstimateSteps(): Int = when (this) {
    OutboxState.Queued -> 1
    OutboxState.Sending -> 2
    OutboxState.Estimating -> 3
    OutboxState.EstimateReady,
    OutboxState.Sent -> 4
    OutboxState.Conflict -> 1
}

@Composable
private fun DraftContent(
    draft: com.local.glucotracker.domain.model.MealDraft?,
    isEstimateReady: Boolean,
    photoPath: String?,
    onAccept: (estimateId: String, eatenAt: Instant, weightOverride: Double?) -> Unit,
    onReject: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var weightText by remember { mutableStateOf("") }

    Column(
        modifier = modifier
            .fillMaxWidth()
            .verticalScroll(rememberScrollState())
            .padding(GT.space.lg),
        verticalArrangement = Arrangement.spacedBy(GT.space.md),
    ) {
        if (photoPath != null) {
            AsyncImage(
                model = File(photoPath),
                contentDescription = null,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(200.dp)
                    .background(GT.colors.surface, GT.shapes.card)
                    .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card),
                contentScale = ContentScale.Fit,
            )
        }

        if (!isEstimateReady) {
            Text(
                text = stringResource(R.string.draft_no_estimate),
                color = GT.colors.muted,
                style = GT.type.sansBody,
            )
        }

        if (draft != null) {
            if (!draft.title.isNullOrBlank()) {
                Text(
                    text = draft.title,
                    color = GT.colors.ink,
                    style = GT.type.sansBody,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = stringResource(R.string.draft_time_label),
                    color = GT.colors.muted,
                    style = GT.type.sansLabel,
                )
                Spacer(Modifier.weight(1f))
                Text(
                    text = formatTime(draft.eatenAt),
                    color = GT.colors.ink2,
                    style = GT.type.monoLabel,
                    maxLines = 1,
                )
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = stringResource(R.string.draft_weight_label),
                    color = GT.colors.muted,
                    style = GT.type.sansLabel,
                )
                Spacer(Modifier.width(GT.space.sm))
                OutlinedTextField(
                    value = weightText,
                    onValueChange = { weightText = it },
                    modifier = Modifier.weight(1f),
                    textStyle = GT.type.monoLabel.copy(color = GT.colors.ink2),
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = GT.colors.hairline2,
                        unfocusedBorderColor = GT.colors.hairline,
                        cursorColor = GT.colors.ink,
                    ),
                    shape = GT.shapes.tag,
                )
            }

            GTHairlineDivider()

            Text(
                text = stringResource(
                    R.string.draft_macros_line,
                    formatGrams(draft.totalProteinG),
                    formatGrams(draft.totalFatG),
                    formatGrams(draft.totalCarbsG),
                ),
                color = GT.colors.ink,
                style = GT.type.monoLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )

            Text(
                text = stringResource(R.string.draft_kcal_label, formatKcal(draft.totalKcal)),
                color = GT.colors.ink,
                style = GT.type.monoLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }

        Spacer(Modifier.weight(1f))

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(GT.space.md),
        ) {
            GTOutlineButton(
                text = stringResource(R.string.draft_reject),
                onClick = onReject,
                modifier = Modifier.weight(1f),
            )
            GTPrimaryButton(
                text = stringResource(R.string.draft_accept),
                onClick = {
                    if (draft != null) {
                        val override = weightText.toDoubleOrNull()
                        onAccept(draft.id, draft.eatenAt, override)
                    }
                },
                modifier = Modifier.weight(1f),
                enabled = isEstimateReady && draft != null,
            )
        }
    }
}

private fun formatTime(instant: Instant): String {
    val time = instant.toLocalDateTime(TimeZone.currentSystemDefault()).time
    return "${time.hour.twoDigits()}:${time.minute.twoDigits()}"
}

private fun formatClock(instant: Instant): String {
    val time = instant.toLocalDateTime(TimeZone.currentSystemDefault()).time
    return "${time.hour.twoDigits()}:${time.minute.twoDigits()}:${time.second.twoDigits()}"
}

private fun formatDateTime(instant: Instant): String {
    val dateTime = instant.toLocalDateTime(TimeZone.currentSystemDefault())
    return "${dateTime.dayOfMonth.twoDigits()}.${dateTime.monthNumber.twoDigits()} " +
        "${dateTime.hour.twoDigits()}:${dateTime.minute.twoDigits()}:${dateTime.second.twoDigits()}"
}

private fun Int.twoDigits(): String = toString().padStart(2, '0')
