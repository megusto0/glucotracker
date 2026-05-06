package com.local.glucotracker.ui.feature.record

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
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import coil3.compose.AsyncImage
import com.local.glucotracker.R
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTIconButton
import com.local.glucotracker.ui.design.primitives.GTKicker
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.design.primitives.GTSectionLabel
import com.local.glucotracker.ui.design.primitives.GTTag
import com.local.glucotracker.ui.format.formatGrams
import com.local.glucotracker.ui.format.formatKcal
import com.local.glucotracker.ui.image.rememberApiImageModel
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlinx.datetime.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

@Composable
fun RecordRoute(
    id: String,
    onOpenGlucose: () -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: RecordViewModel = hiltViewModel(),
) {
    LaunchedEffect(id) {
        viewModel.load(id)
    }

    val state by viewModel.state.collectAsState()
    RecordScreen(
        state = state,
        onClose = onClose,
        onOpenGlucose = onOpenGlucose,
        onSaveTitle = viewModel::updateTitle,
        onSaveTime = viewModel::updateTime,
        onSaveWeight = viewModel::updateWeight,
        onCreatePortion = viewModel::createPortion,
        onDelete = viewModel::deleteRecord,
        onKeepLocal = viewModel::retryConflict,
        onKeepServer = viewModel::dropLocalConflict,
        onKeepBoth = viewModel::keepBothConflict,
        modifier = modifier,
    )
}

@Composable
private fun RecordScreen(
    state: RecordState,
    onClose: () -> Unit,
    onOpenGlucose: () -> Unit,
    onSaveTitle: (String) -> Unit,
    onSaveTime: (String) -> Unit,
    onSaveWeight: (String) -> Unit,
    onCreatePortion: (Double) -> Unit,
    onDelete: () -> Unit,
    onKeepLocal: () -> Unit,
    onKeepServer: () -> Unit,
    onKeepBoth: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var confirmDelete by remember { mutableStateOf(false) }

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg),
    ) {
        Column(Modifier.fillMaxSize()) {
            RecordTopBar(onClose = onClose)
            GTHairlineDivider()
            when (state) {
                RecordState.Loading -> RecordMessage(text = stringResource(R.string.today_loading))
                RecordState.NotFound -> RecordMessage(text = stringResource(R.string.record_not_found))
                is RecordState.Loaded -> RecordContent(
                    loaded = state,
                    onOpenGlucose = onOpenGlucose,
                    onSaveTitle = onSaveTitle,
                    onSaveTime = onSaveTime,
                    onSaveWeight = onSaveWeight,
                    onCreatePortion = onCreatePortion,
                    onDeleteRequest = { confirmDelete = true },
                    onKeepLocal = onKeepLocal,
                    onKeepServer = onKeepServer,
                    onKeepBoth = onKeepBoth,
                    modifier = Modifier.weight(1f),
                )
            }
        }

        if (confirmDelete) {
            DeleteConfirmSheet(
                onDismiss = { confirmDelete = false },
                onConfirm = {
                    confirmDelete = false
                    onDelete()
                    onClose()
                },
                modifier = Modifier.align(Alignment.BottomCenter),
            )
        }
    }
}

@Composable
private fun RecordTopBar(
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
                text = "\u2190",
                color = GT.colors.ink2,
                style = GT.type.sansLabel,
            )
        }
        Text(
            text = stringResource(R.string.record_title),
            modifier = Modifier.align(Alignment.Center),
            color = GT.colors.ink,
            style = GT.type.sansLabel,
            maxLines = 1,
        )
    }
}

@Composable
private fun RecordMessage(
    text: String,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = text,
            color = GT.colors.muted,
            style = GT.type.sansBody,
        )
    }
}

@Composable
private fun RecordContent(
    loaded: RecordState.Loaded,
    onOpenGlucose: () -> Unit,
    onSaveTitle: (String) -> Unit,
    onSaveTime: (String) -> Unit,
    onSaveWeight: (String) -> Unit,
    onCreatePortion: (Double) -> Unit,
    onDeleteRequest: () -> Unit,
    onKeepLocal: () -> Unit,
    onKeepServer: () -> Unit,
    onKeepBoth: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val record = loaded.record
    Column(
        modifier = modifier
            .fillMaxWidth()
            .verticalScroll(rememberScrollState())
            .padding(GT.space.lg),
        verticalArrangement = Arrangement.spacedBy(GT.space.md),
    ) {
        RecordHero(record = record)
        RecordMacros(record = record)

        if (record.status == RecordStatus.Conflict) {
            ConflictPanel(
                errorMessage = loaded.outboxItem?.errorMessage,
                onKeepLocal = onKeepLocal,
                onKeepServer = onKeepServer,
                onKeepBoth = onKeepBoth,
            )
        }

        QuickEditSection(
            record = record,
            onSaveTitle = onSaveTitle,
            onSaveTime = onSaveTime,
            onSaveWeight = onSaveWeight,
            onCreatePortion = onCreatePortion,
        )

        Row(
            horizontalArrangement = Arrangement.spacedBy(GT.space.md),
            modifier = Modifier.fillMaxWidth(),
        ) {
            SourceCard(record = record, modifier = Modifier.weight(1f))
            NightscoutCard(record = record, modifier = Modifier.weight(1f))
        }

        GlucosePanel(
            eatenAt = record.eatenAt,
            onOpenGlucose = onOpenGlucose,
        )

        RecordFooter(onDeleteRequest = onDeleteRequest)
        Spacer(Modifier.height(GT.space.md))
    }
}

@Composable
private fun RecordHero(record: RecordUi) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.Top,
    ) {
        RecordPhoto(model = record.photo)
        Column(
            modifier = Modifier
                .weight(1f)
                .padding(start = GT.space.md),
        ) {
            Text(
                text = record.title.orEmpty().ifBlank { stringResource(R.string.record_title) },
                color = GT.colors.ink,
                style = GT.type.serifSection,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                text = record.kcal?.let { stringResource(R.string.record_kcal_value, formatKcal(it)) }
                    ?: stringResource(R.string.glucose_value_empty),
                modifier = Modifier.padding(top = 3.dp),
                color = GT.colors.ink,
                style = GT.type.monoNumber.copy(fontSize = 22.sp),
                maxLines = 1,
            )
            Row(
                modifier = Modifier.padding(top = GT.space.sm),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                GTTag(text = sourceLabel(record.source))
                GTTag(text = statusLabel(record.status))
                GTTag(text = weightChip(record.weightGrams))
            }
        }
    }
}

@Composable
private fun RecordPhoto(
    model: Any?,
    modifier: Modifier = Modifier,
) {
    val imageModel = rememberApiImageModel(model)
    Box(
        modifier = modifier
            .size(64.dp)
            .clip(GT.shapes.card)
            .background(GT.colors.surface)
            .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.card),
        contentAlignment = Alignment.Center,
    ) {
        if (imageModel != null) {
            AsyncImage(
                model = imageModel,
                contentDescription = null,
                modifier = Modifier.fillMaxSize(),
                contentScale = ContentScale.Crop,
            )
        }
    }
}

@Composable
private fun RecordMacros(record: RecordUi) {
    Text(
        text = stringResource(
            R.string.record_macros_line,
            record.carbsG?.let { formatGrams(it) } ?: stringResource(R.string.glucose_value_empty),
            record.proteinG?.let { formatGrams(it) } ?: stringResource(R.string.glucose_value_empty),
            record.fatG?.let { formatGrams(it) } ?: stringResource(R.string.glucose_value_empty),
            record.fiberG?.let { formatGrams(it) } ?: stringResource(R.string.glucose_value_empty),
        ),
        color = GT.colors.ink2,
        style = GT.type.monoLabel,
        maxLines = 1,
        overflow = TextOverflow.Ellipsis,
    )
}

@Composable
private fun ConflictPanel(
    errorMessage: String?,
    onKeepLocal: () -> Unit,
    onKeepServer: () -> Unit,
    onKeepBoth: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .padding(GT.space.md),
        verticalArrangement = Arrangement.spacedBy(GT.space.sm),
    ) {
        GTKicker(text = stringResource(R.string.record_conflict_kicker))
        Text(
            text = errorMessage ?: stringResource(R.string.record_conflict_body),
            color = GT.colors.warn,
            style = GT.type.sansBody,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(GT.space.sm)) {
            GTOutlineButton(text = stringResource(R.string.record_conflict_keep_local), onClick = onKeepLocal)
            GTOutlineButton(text = stringResource(R.string.record_conflict_keep_server), onClick = onKeepServer)
        }
        GTOutlineButton(text = stringResource(R.string.record_conflict_keep_both), onClick = onKeepBoth)
    }
}

@Composable
private fun QuickEditSection(
    record: RecordUi,
    onSaveTitle: (String) -> Unit,
    onSaveTime: (String) -> Unit,
    onSaveWeight: (String) -> Unit,
    onCreatePortion: (Double) -> Unit,
) {
    var title by remember(record.id, record.title) { mutableStateOf(record.title.orEmpty()) }
    var time by remember(record.id, record.eatenAt) { mutableStateOf(record.eatenAt.timeText()) }
    var weight by remember(record.id, record.weightGrams) { mutableStateOf(editableNumber(record.weightGrams)) }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .padding(GT.space.md),
        verticalArrangement = Arrangement.spacedBy(GT.space.sm),
    ) {
        GTKicker(text = stringResource(R.string.record_quick_edit))
        RecordField(
            label = stringResource(R.string.record_field_name),
            value = title,
            onValueChange = { title = it },
            actionText = stringResource(R.string.record_save),
            onAction = { onSaveTitle(title) },
        )
        RecordField(
            label = stringResource(R.string.record_field_time),
            value = time,
            onValueChange = { time = it },
            actionText = stringResource(R.string.record_save),
            onAction = { onSaveTime(time) },
        )
        RecordField(
            label = stringResource(R.string.record_field_weight),
            value = weight,
            onValueChange = { weight = it },
            actionText = stringResource(R.string.record_recalculate),
            keyboardType = KeyboardType.Number,
            onAction = { onSaveWeight(weight) },
        )
        CreatePortionRow(record = record, onCreatePortion = onCreatePortion)
    }
}

@Composable
private fun RecordField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    actionText: String,
    onAction: () -> Unit,
    modifier: Modifier = Modifier,
    keyboardType: KeyboardType = KeyboardType.Text,
) {
    Column(modifier = modifier.fillMaxWidth()) {
        GTSectionLabel(text = label)
        Row(
            modifier = Modifier.padding(top = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(GT.space.sm),
        ) {
            Box(
                modifier = Modifier
                    .weight(1f)
                    .heightIn(min = 34.dp)
                    .background(GT.colors.surface2, GT.shapes.tag)
                    .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.tag)
                    .padding(horizontal = GT.space.sm, vertical = 8.dp),
                contentAlignment = Alignment.CenterStart,
            ) {
                BasicTextField(
                    value = value,
                    onValueChange = onValueChange,
                    singleLine = true,
                    textStyle = GT.type.sansBody.copy(color = GT.colors.ink),
                    cursorBrush = SolidColor(GT.colors.ink),
                    keyboardOptions = KeyboardOptions(keyboardType = keyboardType),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            GTOutlineButton(text = actionText, onClick = onAction)
        }
    }
}

@Composable
private fun CreatePortionRow(
    record: RecordUi,
    onCreatePortion: (Double) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        GTSectionLabel(text = stringResource(R.string.record_create_portion))
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            PortionChip(
                text = stringResource(R.string.record_chip_100g),
                enabled = record.canCreatePortion,
                onClick = { onCreatePortion(100.0) },
            )
            record.defaultWeightGrams?.let { grams ->
                PortionChip(
                    text = stringResource(R.string.record_chip_template_default, formatGrams(grams)),
                    enabled = record.canCreatePortion,
                    onClick = { onCreatePortion(grams) },
                )
            }
            record.weightGrams?.let { grams ->
                PortionChip(
                    text = stringResource(R.string.record_chip_current_weight, formatGrams(grams)),
                    enabled = record.canCreatePortion,
                    onClick = { onCreatePortion(grams) },
                )
            }
        }
    }
}

@Composable
private fun PortionChip(
    text: String,
    enabled: Boolean,
    onClick: () -> Unit,
) {
    Box(
        modifier = Modifier.clickable(enabled = enabled, onClick = onClick),
    ) {
        GTTag(text = text)
    }
}

@Composable
private fun SourceCard(
    record: RecordUi,
    modifier: Modifier = Modifier,
) {
    val capturedText = record.capturedAt?.takeIf { record.isPending }?.let { capturedAt ->
        stringResource(R.string.record_source_captured, capturedAt.dateTimeSecondsText())
    }
    RecordInfoCard(
        kicker = capturedText ?: stringResource(R.string.record_card_source),
        primary = sourceLabel(record.source),
        secondary = stringResource(R.string.record_source_time, record.eatenAt.timeText()),
        modifier = modifier,
    )
}

@Composable
private fun NightscoutCard(
    record: RecordUi,
    modifier: Modifier = Modifier,
) {
    val status = if (record.isPending) {
        stringResource(R.string.record_nightscout_pending)
    } else {
        record.nightscoutStatus ?: stringResource(R.string.record_nightscout_empty)
    }
    val secondary = record.nightscoutSyncedAt?.let {
        stringResource(R.string.record_nightscout_synced_at, it.dateTimeText())
    } ?: stringResource(R.string.record_nightscout_context_only)
    RecordInfoCard(
        kicker = stringResource(R.string.record_card_nightscout),
        primary = status,
        secondary = secondary,
        modifier = modifier,
    )
}

@Composable
private fun RecordInfoCard(
    kicker: String,
    primary: String,
    secondary: String,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .padding(GT.space.md),
    ) {
        GTKicker(text = kicker)
        Text(
            text = primary,
            modifier = Modifier.padding(top = 6.dp),
            color = GT.colors.ink,
            style = GT.type.sansLabel,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Text(
            text = secondary,
            modifier = Modifier.padding(top = 2.dp),
            color = GT.colors.muted,
            style = GT.type.monoLabel,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun GlucosePanel(
    eatenAt: Instant,
    onOpenGlucose: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .padding(GT.space.md),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            GTKicker(text = stringResource(R.string.record_glucose_kicker))
            Text(
                text = stringResource(R.string.record_glucose_at, eatenAt.timeText()),
                modifier = Modifier.padding(top = 6.dp),
                color = GT.colors.ink2,
                style = GT.type.monoLabel,
            )
        }
        Text(
            text = stringResource(R.string.record_glucose_open),
            modifier = Modifier.clickable(onClick = onOpenGlucose),
            color = GT.colors.info,
            style = GT.type.sansLabel,
        )
    }
}

@Composable
private fun RecordFooter(onDeleteRequest: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        GTOutlineButton(
            text = stringResource(R.string.record_favorite),
            onClick = {},
        )
        Spacer(Modifier.weight(1f))
        Text(
            text = stringResource(R.string.record_delete),
            modifier = Modifier
                .heightIn(min = GT.space.touch)
                .clickable(onClick = onDeleteRequest)
                .padding(horizontal = GT.space.sm, vertical = 12.dp),
            color = GT.colors.warn,
            style = GT.type.sansLabel,
        )
    }
}

@Composable
private fun DeleteConfirmSheet(
    onDismiss: () -> Unit,
    onConfirm: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(GT.colors.surface)
            .border(GT.space.hairline, GT.colors.hairline)
            .navigationBarsPadding()
            .padding(GT.space.lg),
        verticalArrangement = Arrangement.spacedBy(GT.space.sm),
    ) {
        Text(
            text = stringResource(R.string.record_delete_confirm_title),
            color = GT.colors.ink,
            style = GT.type.serifSection,
        )
        Text(
            text = stringResource(R.string.record_delete_confirm_body),
            color = GT.colors.ink2,
            style = GT.type.sansBody,
        )
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(GT.space.md),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            GTOutlineButton(text = stringResource(R.string.record_delete_cancel), onClick = onDismiss)
            Spacer(Modifier.weight(1f))
            Text(
                text = stringResource(R.string.record_delete_confirm),
                modifier = Modifier
                    .heightIn(min = GT.space.touch)
                    .clickable(onClick = onConfirm)
                    .padding(horizontal = GT.space.sm, vertical = 12.dp),
                color = GT.colors.warn,
                style = GT.type.sansLabel,
            )
        }
    }
}

@Composable
private fun sourceLabel(source: String): String =
    when (source.lowercase()) {
        "photo",
        "photo_estimate",
        "gallery",
        -> stringResource(R.string.today_source_photo)
        "pattern",
        "template",
        -> stringResource(R.string.today_source_pattern)
        "text" -> stringResource(R.string.today_source_text)
        "manual" -> stringResource(R.string.today_source_manual)
        else -> stringResource(R.string.today_source_mixed)
    }

@Composable
private fun statusLabel(status: RecordStatus): String =
    when (status) {
        RecordStatus.Accepted -> stringResource(R.string.today_status_accepted)
        RecordStatus.Draft -> stringResource(R.string.today_status_draft)
        RecordStatus.Queued -> stringResource(R.string.today_status_queued)
        RecordStatus.Estimating -> stringResource(R.string.today_status_estimating)
        RecordStatus.EstimateReady -> stringResource(R.string.today_status_estimate_ready)
        RecordStatus.Conflict -> stringResource(R.string.today_status_conflict)
    }

@Composable
private fun weightChip(weightGrams: Double?): String =
    stringResource(R.string.record_weight_chip, weightGrams?.let { formatGrams(it) } ?: formatGrams(100.0))

private fun editableNumber(value: Double?): String =
    value?.let {
        if (it == it.toLong().toDouble()) it.toLong().toString() else formatGrams(it)
    }.orEmpty()

private fun Instant.timeText(): String {
    val time = toLocalDateTime(TimeZone.currentSystemDefault()).time
    return "${time.hour.toString().padStart(2, '0')}:${time.minute.toString().padStart(2, '0')}"
}

private fun Instant.dateTimeText(): String =
    toJavaLocalDateTime().format(DateTimeFormatter.ofPattern("d MMM HH:mm", Locale("ru")))

private fun Instant.dateTimeSecondsText(): String =
    toJavaLocalDateTime().format(DateTimeFormatter.ofPattern("d MMM HH:mm:ss", Locale("ru")))

private fun Instant.toJavaLocalDateTime(): LocalDateTime {
    val local = toLocalDateTime(TimeZone.currentSystemDefault())
    return LocalDateTime.of(
        local.year,
        local.monthNumber,
        local.dayOfMonth,
        local.hour,
        local.minute,
        local.second,
    )
}
