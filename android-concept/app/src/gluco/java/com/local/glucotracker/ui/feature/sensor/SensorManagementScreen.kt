package com.local.glucotracker.ui.feature.sensor

import androidx.compose.foundation.Canvas
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.SensorPhase
import com.local.glucotracker.domain.model.SensorQuality
import com.local.glucotracker.domain.model.SensorQualityConfidence
import com.local.glucotracker.domain.model.SensorSession
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHintBox
import com.local.glucotracker.ui.design.primitives.GTIconButton
import com.local.glucotracker.ui.design.primitives.GTKicker
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.design.primitives.GTTag
import com.local.glucotracker.ui.format.formatGrams
import com.local.glucotracker.ui.format.formatMmol
import com.local.glucotracker.ui.format.formatPercent
import kotlinx.datetime.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

@Composable
fun SensorManagementRoute(
    onBack: () -> Unit,
    viewModel: SensorManagementViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val exclusionReason = stringResource(R.string.sensor_exclusion_reason_mobile)
    SensorManagementScreen(
        state = state,
        onBack = onBack,
        onRefresh = viewModel::refresh,
        onFingerstickSubmit = viewModel::enqueueFingerstick,
        onStartSensor = viewModel::startSensor,
        onSelectSensor = viewModel::selectSensor,
        onFinishSensor = viewModel::finishSensor,
        onSetExcluded = { id, excluded ->
            viewModel.setExcluded(id, excluded, exclusionReason)
        },
    )
}

@Composable
fun SensorManagementScreen(
    state: SensorManagementState,
    onBack: () -> Unit,
    onRefresh: () -> Unit,
    onFingerstickSubmit: (Double) -> Unit,
    onStartSensor: (String?, String?, String?, Double) -> Unit,
    onSelectSensor: (String) -> Unit,
    onFinishSensor: (String) -> Unit,
    onSetExcluded: (String, Boolean) -> Unit,
    modifier: Modifier = Modifier,
) {
    var addSheetVisible by remember { mutableStateOf(false) }
    var fingerstickText by remember { mutableStateOf("") }
    val fingerstickValue = fingerstickText.replace(',', '.').toDoubleOrNull()
    val selected = state.sensors.firstOrNull { it.id == state.selectedSensorId }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 18.dp, vertical = 12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            GTIconButton(onClick = onBack) { BackGlyph() }
            Column(modifier = Modifier.padding(start = 8.dp)) {
                Text(
                    text = stringResource(R.string.sensor_management_title),
                    color = GT.colors.ink,
                    style = GT.type.serifTitle,
                )
                Text(
                    text = stringResource(R.string.sensor_management_subtitle),
                    color = GT.colors.muted,
                    style = GT.type.sansLabel,
                )
            }
        }

        FingerstickCard(
            value = fingerstickText,
            onValueChange = { fingerstickText = it },
            enabled = fingerstickValue != null && fingerstickValue > 0.0,
            onSubmit = {
                fingerstickValue?.let(onFingerstickSubmit)
                fingerstickText = ""
            },
            modifier = Modifier.padding(top = 18.dp),
        )

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 22.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            GTKicker(text = stringResource(R.string.sensor_list_title))
            Spacer(Modifier.weight(1f))
            GTOutlineButton(
                text = stringResource(R.string.sensor_add),
                onClick = { addSheetVisible = true },
            )
        }

        if (state.pendingCreateCount > 0 || state.pendingSensorIds.isNotEmpty()) {
            GTHintBox(
                text = stringResource(
                    R.string.sensor_pending_changes,
                    state.pendingCreateCount + state.pendingSensorIds.size,
                ),
                modifier = Modifier.padding(top = 8.dp),
            )
        }

        when {
            state.sensors.isEmpty() && state.isRefreshing -> {
                Text(
                    text = stringResource(R.string.sensor_loading),
                    modifier = Modifier.padding(top = 14.dp),
                    color = GT.colors.muted,
                    style = GT.type.sansBody,
                )
            }
            state.sensors.isEmpty() && state.loadFailed -> {
                GTHintBox(
                    text = stringResource(R.string.sensor_load_failed),
                    modifier = Modifier.padding(top = 10.dp),
                )
                GTOutlineButton(
                    text = stringResource(R.string.sensor_retry),
                    onClick = onRefresh,
                    modifier = Modifier.padding(top = 4.dp),
                )
            }
            state.sensors.isEmpty() -> {
                GTHintBox(
                    text = stringResource(R.string.sensor_empty),
                    modifier = Modifier.padding(top = 10.dp),
                )
            }
            else -> {
                Column(
                    modifier = Modifier.padding(top = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    state.sensors.forEach { sensor ->
                        SensorRow(
                            sensor = sensor,
                            selected = sensor.id == state.selectedSensorId,
                            pending = sensor.id in state.pendingSensorIds,
                            onClick = { onSelectSensor(sensor.id) },
                        )
                    }
                }
            }
        }

        if (selected != null) {
            QualityCard(
                sensor = selected,
                quality = state.quality,
                loading = state.qualityLoading,
                pending = selected.id in state.pendingSensorIds,
                onFinish = { onFinishSensor(selected.id) },
                onSetExcluded = { excluded -> onSetExcluded(selected.id, excluded) },
                modifier = Modifier.padding(top = 18.dp, bottom = 20.dp),
            )
        }
    }

    if (addSheetVisible) {
        AddSensorSheet(
            onDismiss = { addSheetVisible = false },
            onSubmit = { label, vendor, model, days ->
                onStartSensor(label, vendor, model, days)
                addSheetVisible = false
            },
        )
    }
}

@Composable
private fun FingerstickCard(
    value: String,
    onValueChange: (String) -> Unit,
    enabled: Boolean,
    onSubmit: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .padding(14.dp),
    ) {
        GTKicker(text = stringResource(R.string.fingerstick_add_title))
        Text(
            text = stringResource(R.string.fingerstick_add_desc),
            modifier = Modifier.padding(top = 5.dp),
            color = GT.colors.muted,
            style = GT.type.sansBody,
        )
        Row(
            modifier = Modifier.padding(top = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            SensorTextField(
                value = value,
                onValueChange = onValueChange,
                keyboardType = KeyboardType.Decimal,
                modifier = Modifier.weight(1f),
            )
            Text(
                text = stringResource(R.string.glucose_sheet_value_label),
                modifier = Modifier.padding(start = 8.dp),
                color = GT.colors.muted,
                style = GT.type.monoLabel,
            )
            GTOutlineButton(
                text = stringResource(R.string.glucose_sheet_submit),
                enabled = enabled,
                onClick = onSubmit,
                modifier = Modifier.padding(start = 8.dp),
            )
        }
    }
}

@Composable
private fun SensorRow(
    sensor: SensorSession,
    selected: Boolean,
    pending: Boolean,
    onClick: () -> Unit,
) {
    val status = when {
        pending -> stringResource(R.string.sensor_status_pending)
        sensor.excludedFromAnalytics -> stringResource(R.string.sensor_status_excluded)
        sensor.endedAt == null -> stringResource(R.string.sensor_status_active)
        else -> stringResource(R.string.sensor_status_finished)
    }
    val title = sensor.label
        ?: listOfNotNull(sensor.vendor, sensor.model).joinToString(" ").ifBlank {
            stringResource(R.string.sensor_default_name)
        }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = 64.dp)
            .background(if (selected) GT.colors.surface2 else GT.colors.surface, GT.shapes.card)
            .border(
                GT.space.hairline,
                if (selected) GT.colors.hairline2 else GT.colors.hairline,
                GT.shapes.card,
            )
            .clickable(role = Role.Button, onClick = onClick)
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = title,
                color = GT.colors.ink,
                style = GT.type.sansLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                text = stringResource(R.string.sensor_started_at, sensor.startedAt.shortDateTime()),
                modifier = Modifier.padding(top = 4.dp),
                color = GT.colors.muted,
                style = GT.type.monoLabel,
            )
        }
        GTTag(text = status, active = sensor.endedAt == null && !sensor.excludedFromAnalytics && !pending)
    }
}

@Composable
private fun QualityCard(
    sensor: SensorSession,
    quality: SensorQuality?,
    loading: Boolean,
    pending: Boolean,
    onFinish: () -> Unit,
    onSetExcluded: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .padding(14.dp),
    ) {
        GTKicker(text = stringResource(R.string.sensor_quality_title))
        when {
            loading -> Text(
                text = stringResource(R.string.sensor_quality_loading),
                modifier = Modifier.padding(top = 10.dp),
                color = GT.colors.muted,
                style = GT.type.sansBody,
            )
            quality == null -> GTHintBox(
                text = stringResource(R.string.sensor_quality_unavailable),
                modifier = Modifier.padding(top = 10.dp),
            )
            else -> {
                Row(
                    modifier = Modifier.padding(top = 8.dp),
                    verticalAlignment = Alignment.Bottom,
                ) {
                    Text(
                        text = formatPercent(quality.qualityScore.toDouble()),
                        color = GT.colors.ink,
                        style = GT.type.monoNumber,
                    )
                    Text(
                        text = stringResource(R.string.sensor_quality_score_label),
                        modifier = Modifier.padding(start = 8.dp, bottom = 2.dp),
                        color = GT.colors.muted,
                        style = GT.type.sansLabel,
                    )
                    Spacer(Modifier.weight(1f))
                    GTTag(text = quality.confidence.label())
                }
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 8.dp)
                        .height(2.dp)
                        .background(GT.colors.hairline),
                ) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth((quality.qualityScore / 100f).coerceIn(0f, 1f))
                            .height(2.dp)
                            .background(GT.colors.info.copy(alpha = 0.65f)),
                    )
                }
                Row(
                    modifier = Modifier.padding(top = 12.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    QualityMetric(
                        label = stringResource(R.string.sensor_metric_phase),
                        value = quality.sensorPhase.label(),
                        modifier = Modifier.weight(1f),
                    )
                    QualityMetric(
                        label = stringResource(R.string.sensor_metric_age),
                        value = quality.sensorAgeDays?.let {
                            stringResource(R.string.sensor_days_value, formatGrams(it))
                        } ?: stringResource(R.string.glucose_value_empty),
                        modifier = Modifier.weight(1f),
                    )
                }
                Row(
                    modifier = Modifier.padding(top = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    QualityMetric(
                        label = stringResource(R.string.sensor_metric_fingersticks),
                        value = quality.fingerstickCount.toString(),
                        modifier = Modifier.weight(1f),
                    )
                    QualityMetric(
                        label = stringResource(R.string.sensor_metric_calibration),
                        value = quality.validCalibrationPoints.toString(),
                        modifier = Modifier.weight(1f),
                    )
                }
                Row(
                    modifier = Modifier.padding(top = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    QualityMetric(
                        label = stringResource(R.string.sensor_metric_missing),
                        value = quality.missingDataPercent?.let(::formatPercent)
                            ?: stringResource(R.string.glucose_value_empty),
                        modifier = Modifier.weight(1f),
                    )
                    QualityMetric(
                        label = stringResource(R.string.sensor_metric_mard),
                        value = quality.mardPercent?.let(::formatPercent)
                            ?: stringResource(R.string.glucose_value_empty),
                        modifier = Modifier.weight(1f),
                    )
                }
                if (quality.suspectedCompressionCount > 0) {
                    Text(
                        text = stringResource(
                            R.string.sensor_compression_note,
                            quality.suspectedCompressionCount,
                        ),
                        modifier = Modifier.padding(top = 10.dp),
                        color = GT.colors.warn,
                        style = GT.type.monoLabel,
                    )
                }
            }
        }
        Text(
            text = stringResource(R.string.sensor_quality_informational),
            modifier = Modifier.padding(top = 12.dp),
            color = GT.colors.muted,
            style = GT.type.sansLabel,
        )
        Row(
            modifier = Modifier.padding(top = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            if (sensor.endedAt == null) {
                GTOutlineButton(
                    text = stringResource(R.string.sensor_finish),
                    enabled = !pending,
                    onClick = onFinish,
                )
            }
            GTOutlineButton(
                text = if (sensor.excludedFromAnalytics) {
                    stringResource(R.string.sensor_include_analytics)
                } else {
                    stringResource(R.string.sensor_exclude_analytics)
                },
                enabled = !pending,
                onClick = { onSetExcluded(!sensor.excludedFromAnalytics) },
            )
        }
    }
}

@Composable
private fun QualityMetric(label: String, value: String, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .background(GT.colors.surface2, GT.shapes.tag)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.tag)
            .padding(10.dp),
    ) {
        Text(text = label, color = GT.colors.muted, style = GT.type.kicker, maxLines = 1)
        Text(
            text = value,
            modifier = Modifier.padding(top = 5.dp),
            color = GT.colors.ink,
            style = GT.type.monoLabel,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AddSensorSheet(
    onDismiss: () -> Unit,
    onSubmit: (String?, String?, String?, Double) -> Unit,
) {
    var label by remember { mutableStateOf("") }
    var vendor by remember { mutableStateOf("") }
    var model by remember { mutableStateOf("") }
    var lifeDays by remember { mutableStateOf("15") }
    val parsedDays = lifeDays.replace(',', '.').toDoubleOrNull()
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        containerColor = GT.colors.surface,
        contentColor = GT.colors.ink,
        tonalElevation = 0.dp,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .navigationBarsPadding()
                .padding(horizontal = 18.dp, vertical = 20.dp),
        ) {
            Text(
                text = stringResource(R.string.sensor_add_title),
                color = GT.colors.ink,
                style = GT.type.serifSection,
            )
            SensorFieldLabel(R.string.sensor_label)
            SensorTextField(value = label, onValueChange = { label = it })
            SensorFieldLabel(R.string.sensor_vendor)
            SensorTextField(value = vendor, onValueChange = { vendor = it })
            SensorFieldLabel(R.string.sensor_model)
            SensorTextField(value = model, onValueChange = { model = it })
            SensorFieldLabel(R.string.sensor_expected_life)
            SensorTextField(
                value = lifeDays,
                onValueChange = { lifeDays = it },
                keyboardType = KeyboardType.Decimal,
            )
            Text(
                text = stringResource(R.string.sensor_starts_now),
                modifier = Modifier.padding(top = 10.dp),
                color = GT.colors.muted,
                style = GT.type.sansLabel,
            )
            GTOutlineButton(
                text = stringResource(R.string.sensor_start),
                enabled = parsedDays != null && parsedDays > 0.0,
                onClick = {
                    parsedDays?.let { onSubmit(label, vendor, model, it) }
                },
                modifier = Modifier.padding(top = 10.dp),
            )
        }
    }
}

@Composable
private fun SensorFieldLabel(labelRes: Int) {
    Text(
        text = stringResource(labelRes),
        modifier = Modifier.padding(top = 12.dp, bottom = 5.dp),
        color = GT.colors.muted,
        style = GT.type.kicker,
    )
}

@Composable
private fun SensorTextField(
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    keyboardType: KeyboardType = KeyboardType.Text,
) {
    BasicTextField(
        value = value,
        onValueChange = onValueChange,
        modifier = modifier
            .fillMaxWidth()
            .height(44.dp)
            .background(GT.colors.surface2, GT.shapes.tag)
            .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.tag)
            .padding(horizontal = 12.dp),
        textStyle = GT.type.monoLabel.copy(color = GT.colors.ink),
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = keyboardType),
        decorationBox = { inner -> Box(contentAlignment = Alignment.CenterStart) { inner() } },
    )
}

@Composable
private fun SensorQualityConfidence.label(): String = when (this) {
    SensorQualityConfidence.None -> stringResource(R.string.sensor_confidence_none)
    SensorQualityConfidence.Low -> stringResource(R.string.sensor_confidence_low)
    SensorQualityConfidence.Medium -> stringResource(R.string.sensor_confidence_medium)
    SensorQualityConfidence.High -> stringResource(R.string.sensor_confidence_high)
}

@Composable
private fun SensorPhase?.label(): String = when (this) {
    SensorPhase.Warmup -> stringResource(R.string.sensor_phase_warmup)
    SensorPhase.Stable -> stringResource(R.string.sensor_phase_stable)
    SensorPhase.EndOfLife -> stringResource(R.string.sensor_phase_end_of_life)
    null -> stringResource(R.string.glucose_value_empty)
}

private fun Instant.shortDateTime(): String {
    val local = toLocalDateTime(TimeZone.currentSystemDefault())
    return buildString {
        append(local.dayOfMonth.toString().padStart(2, '0'))
        append('.')
        append(local.monthNumber.toString().padStart(2, '0'))
        append('.')
        append(local.year)
        append(" · ")
        append(local.hour.toString().padStart(2, '0'))
        append(':')
        append(local.minute.toString().padStart(2, '0'))
    }
}

@Composable
private fun BackGlyph() {
    val color: Color = GT.colors.ink2
    Canvas(modifier = Modifier.size(16.dp)) {
        val stroke = 1.4.dp.toPx()
        drawLine(
            color,
            Offset(size.width * 0.75f, size.height * 0.18f),
            Offset(size.width * 0.25f, size.height * 0.5f),
            stroke,
            StrokeCap.Round,
        )
        drawLine(
            color,
            Offset(size.width * 0.25f, size.height * 0.5f),
            Offset(size.width * 0.75f, size.height * 0.82f),
            stroke,
            StrokeCap.Round,
        )
    }
}
