package com.local.glucotracker.ui.feature.insulin

import android.app.DatePickerDialog
import android.app.TimePickerDialog
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.DeleteNightscoutInsulinOutboxKind
import com.local.glucotracker.domain.model.InsulinEvent
import com.local.glucotracker.domain.model.UpdateNightscoutInsulinOutboxKind
import com.local.glucotracker.domain.repository.OutboxRepository
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import dagger.hilt.android.lifecycle.HiltViewModel
import java.time.format.DateTimeFormatter
import javax.inject.Inject
import kotlinx.coroutines.launch
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.LocalDateTime
import kotlinx.datetime.LocalTime
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toInstant
import kotlinx.datetime.toJavaLocalDate
import kotlinx.datetime.toJavaLocalTime
import kotlinx.datetime.toLocalDateTime

@HiltViewModel
class InsulinManagementViewModel @Inject constructor(
    private val outboxRepository: OutboxRepository,
) : ViewModel() {
    fun update(event: InsulinEvent, units: Double, recordedAt: Instant, onQueued: () -> Unit) {
        viewModelScope.launch {
            outboxRepository.enqueue(
                UpdateNightscoutInsulinOutboxKind(
                    eventId = event.id,
                    originalRecordedAt = event.timestamp,
                    recordedAt = recordedAt,
                    insulinUnits = units,
                ),
            )
            onQueued()
        }
    }

    fun delete(event: InsulinEvent, onQueued: () -> Unit) {
        viewModelScope.launch {
            outboxRepository.enqueue(
                DeleteNightscoutInsulinOutboxKind(
                    eventId = event.id,
                    recordedAt = event.timestamp,
                ),
            )
            onQueued()
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun InsulinManagementSheet(
    event: InsulinEvent,
    onDismiss: () -> Unit,
    viewModel: InsulinManagementViewModel = hiltViewModel(),
) {
    val zone = TimeZone.currentSystemDefault()
    val initial = remember(event.id) { event.timestamp.toLocalDateTime(zone) }
    var date by remember(event.id) { mutableStateOf(initial.date) }
    var time by remember(event.id) { mutableStateOf(initial.time) }
    var unitsText by remember(event.id) {
        mutableStateOf(formatEditableInsulin(event.doseUnits))
    }
    var confirmDelete by remember(event.id) { mutableStateOf(false) }
    val units = unitsText.replace(',', '.').toDoubleOrNull()
        ?.takeIf { it > 0.0 && it <= 100.0 }
    val recordedAt = remember(date, time) {
        LocalDateTime(date, time).toInstant(zone)
    }
    val changed = units != null &&
        (kotlin.math.abs(units - event.doseUnits) >= 0.01 || recordedAt != event.timestamp)

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = GT.colors.bg,
        contentColor = GT.colors.ink,
        tonalElevation = 0.dp,
        scrimColor = GT.colors.ink.copy(alpha = 0.55f),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp, vertical = 20.dp)
                .testTag("insulin-management-sheet"),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = stringResource(R.string.insulin_manage_title),
                    color = GT.colors.ink,
                    style = GT.type.serifSection,
                )
                Spacer(Modifier.weight(1f))
                Text(
                    text = stringResource(R.string.insulin_entry_cancel),
                    modifier = Modifier
                        .heightIn(min = 44.dp)
                        .clickable(onClick = onDismiss)
                        .padding(horizontal = 4.dp, vertical = 12.dp),
                    color = GT.colors.muted,
                    style = GT.type.sansLabel,
                )
            }

            Row(
                verticalAlignment = Alignment.Bottom,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                BasicTextField(
                    value = unitsText,
                    onValueChange = { unitsText = sanitizeUnitsInput(it) },
                    modifier = Modifier
                        .weight(1f)
                        .height(64.dp)
                        .background(GT.colors.surface2, GT.shapes.card)
                        .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.card)
                        .padding(horizontal = 14.dp),
                    textStyle = GT.type.monoNumber.copy(
                        color = GT.colors.ink,
                        textAlign = TextAlign.Start,
                    ),
                    cursorBrush = SolidColor(GT.colors.ink),
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    decorationBox = { inner ->
                        Box(contentAlignment = Alignment.CenterStart) { inner() }
                    },
                )
                Text(
                    text = stringResource(R.string.insulin_entry_label),
                    modifier = Modifier.padding(bottom = 12.dp),
                    color = GT.colors.muted,
                    style = GT.type.kicker,
                )
            }

            InsulinDateTimeRow(
                date = date,
                time = time,
                onDateChange = { date = it },
                onTimeChange = { time = it },
            )

            GTOutlineButton(
                text = stringResource(R.string.insulin_manage_save),
                enabled = changed,
                onClick = {
                    units?.let { value ->
                        viewModel.update(event, value, recordedAt, onQueued = onDismiss)
                    }
                },
                modifier = Modifier.fillMaxWidth(),
            )

            if (confirmDelete) {
                Text(
                    text = stringResource(R.string.insulin_manage_delete_confirm),
                    color = GT.colors.ink2,
                    style = GT.type.sansBody,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    GTOutlineButton(
                        text = stringResource(R.string.insulin_manage_keep),
                        onClick = { confirmDelete = false },
                        modifier = Modifier.weight(1f),
                    )
                    GTOutlineButton(
                        text = stringResource(R.string.insulin_manage_delete_action),
                        onClick = { viewModel.delete(event, onQueued = onDismiss) },
                        modifier = Modifier.weight(1f),
                    )
                }
            } else {
                GTOutlineButton(
                    text = stringResource(R.string.insulin_manage_delete),
                    onClick = { confirmDelete = true },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            Text(
                text = stringResource(R.string.insulin_manage_nightscout_note),
                color = GT.colors.muted,
                style = GT.type.sansLabel,
            )
        }
    }
}

@Composable
private fun InsulinDateTimeRow(
    date: LocalDate,
    time: LocalTime,
    onDateChange: (LocalDate) -> Unit,
    onTimeChange: (LocalTime) -> Unit,
) {
    val context = LocalContext.current
    val dateText = date.toJavaLocalDate().format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))
    val timeText = time.toJavaLocalTime().format(DateTimeFormatter.ofPattern("HH:mm"))
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        DateTimeCell(
            label = stringResource(R.string.insulin_manage_date),
            value = dateText,
            modifier = Modifier.weight(1f),
            onClick = {
                DatePickerDialog(
                    context,
                    { _, year, month, day -> onDateChange(LocalDate(year, month + 1, day)) },
                    date.year,
                    date.monthNumber - 1,
                    date.dayOfMonth,
                ).show()
            },
        )
        DateTimeCell(
            label = stringResource(R.string.insulin_manage_time),
            value = timeText,
            modifier = Modifier.weight(1f),
            onClick = {
                TimePickerDialog(
                    context,
                    { _, hour, minute -> onTimeChange(LocalTime(hour, minute)) },
                    time.hour,
                    time.minute,
                    true,
                ).show()
            },
        )
    }
}

@Composable
private fun DateTimeCell(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    Column(
        modifier = modifier
            .heightIn(min = 52.dp)
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 8.dp),
    ) {
        Text(text = label, color = GT.colors.muted, style = GT.type.kicker)
        Text(text = value, color = GT.colors.ink, style = GT.type.monoLabel)
    }
}

private fun formatEditableInsulin(value: Double): String =
    if (value % 1.0 == 0.0) value.toInt().toString() else value.toString().replace('.', ',')
