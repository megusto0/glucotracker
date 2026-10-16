package com.local.glucotracker.ui.feature.glucose

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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.ActiveGlucoseContext
import com.local.glucotracker.domain.model.GlucoseTirDay
import com.local.glucotracker.domain.model.SensorSession
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHintBox
import com.local.glucotracker.ui.design.primitives.GTIconButton
import com.local.glucotracker.ui.design.primitives.GTKicker
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.format.formatClockDuration
import com.local.glucotracker.ui.format.formatGrams
import com.local.glucotracker.ui.format.formatInsulinUnits
import com.local.glucotracker.ui.format.formatMmol
import com.local.glucotracker.ui.format.formatPercent
import com.local.glucotracker.ui.format.formatSignedMmol
import kotlinx.coroutines.delay
import kotlinx.datetime.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

@Composable
fun GlucoseRoute(
    onOpenSensors: () -> Unit = {},
    viewModel: GlucoseViewModel = hiltViewModel(),
) {
    LaunchedEffect(Unit) {
        while (true) {
            viewModel.refresh()
            delay(GlucoseRefreshIntervalMillis)
        }
    }
    val state by viewModel.state.collectAsStateWithLifecycle()
    GlucoseScreen(
        state = state,
        onSelectWindow = viewModel::selectFocusWindow,
        onMoveFocus = viewModel::moveFocusTo,
        onFollowLive = viewModel::followLive,
        onFingerstickSubmit = viewModel::enqueueFingerstick,
        onOpenSensors = onOpenSensors,
    )
}

private const val GlucoseRefreshIntervalMillis = 5 * 60 * 1_000L

/** The focus chart fills whatever the screen leaves; it never shrinks below this. */
private val FocusChartMinHeight = 240.dp

@Composable
fun GlucoseScreen(
    state: GlucoseScreenState,
    onSelectWindow: (FocusWindow) -> Unit,
    onMoveFocus: (Instant) -> Unit,
    onFollowLive: () -> Unit,
    onFingerstickSubmit: (Double) -> Unit,
    onOpenSensors: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    var sheetVisible by remember { mutableStateOf(false) }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg)
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        GlucoseHeader(state = state, onSheetOpen = { sheetVisible = true })
        FocusControls(
            state = state,
            onSelectWindow = onSelectWindow,
            onFollowLive = onFollowLive,
        )
        if (state.readings.isEmpty() && state.meals.isEmpty() && state.insulin.isEmpty()) {
            GTHintBox(text = stringResource(R.string.glucose_empty, stringResource(R.string.glucose_window_24h)))
        } else {
            GlucoseFocusChart(
                state = state,
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .heightIn(min = FocusChartMinHeight),
            )
            GlucoseOverviewChart(
                state = state,
                onMoveFocus = onMoveFocus,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(84.dp),
            )
        }
        state.tirToday?.let { TirTodayLine(it) }
    }

    if (sheetVisible) {
        GlucoseSheet(
            activeSensor = state.activeSensor,
            onDismiss = { sheetVisible = false },
            onSubmit = { value ->
                onFingerstickSubmit(value)
                sheetVisible = false
            },
            onOpenSensors = {
                sheetVisible = false
                onOpenSensors()
            },
        )
    }
}

/**
 * Two balanced columns: the value with its trend and age on the left, the
 * server's IOB/COB right-aligned on the right. Title and the fingerstick
 * button share the line above.
 */
@Composable
private fun GlucoseHeader(
    state: GlucoseScreenState,
    onSheetOpen: () -> Unit,
) {
    val latest = state.latest
    Column(modifier = Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            GTKicker(text = stringResource(R.string.glucose_kicker))
            Text(
                text = stringResource(R.string.glucose_title_age, latestKicker(state)),
                modifier = Modifier.weight(1f),
                color = GT.colors.muted,
                style = GT.type.monoLabel.copy(fontSize = 11.sp),
                maxLines = 1,
            )
            val sheetDescription = stringResource(R.string.glucose_sheet_content_description)
            GTIconButton(
                onClick = onSheetOpen,
                modifier = Modifier.semantics { contentDescription = sheetDescription },
            ) {
                FingerstickGlyph()
            }
        }
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.Bottom,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = latest?.displayValueMmolL?.let(::formatMmol)
                        ?: stringResource(R.string.glucose_value_empty),
                    color = if (state.isStale) GT.colors.ink2 else GT.colors.ink,
                    style = GT.type.monoNumber.copy(fontSize = 48.sp, lineHeight = 52.sp),
                    maxLines = 1,
                )
                Text(
                    text = trendLine(state),
                    modifier = Modifier.padding(top = 2.dp),
                    color = GT.colors.ink2,
                    style = GT.type.monoLabel.copy(fontSize = 12.sp, lineHeight = 16.sp),
                    maxLines = 1,
                )
            }
            state.active?.let { active ->
                ActiveContext(active = active, modifier = Modifier.weight(1f))
            }
        }
    }
}

/** «−0,6 за 15 мин»; nothing to say when the reading is stale or alone. */
@Composable
private fun trendLine(state: GlucoseScreenState): String {
    val delta = state.delta15Mmol?.takeIf { !state.isStale } ?: return stringResource(R.string.glucose_value_empty)
    return stringResource(R.string.glucose_delta_15, formatDelta(delta))
}

@Composable
private fun latestKicker(state: GlucoseScreenState): String =
    when {
        state.latest == null -> stringResource(R.string.glucose_sensor_empty)
        state.isStale -> stringResource(R.string.glucose_last_value, state.latest.readingAt.hourMinute())
        else -> stringResource(R.string.glucose_minutes_ago, state.latestAgeMinutes ?: 0)
    }

/** Nightscout's IOB/COB, as two right-aligned label · value · time-left lines. */
@Composable
private fun ActiveContext(active: ActiveGlucoseContext, modifier: Modifier = Modifier) {
    val units = stringResource(R.string.glucose_unit_insulin_suffix)
    val grams = stringResource(R.string.glucose_unit_grams_suffix)
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.End,
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        ActiveStat(
            label = stringResource(R.string.glucose_iob_label),
            value = formatInsulinUnits(active.iobUnits) + units,
            minutesLeft = active.iobMinutesRemaining,
        )
        ActiveStat(
            label = stringResource(R.string.glucose_cob_label),
            value = formatGrams(active.cobGrams) + grams,
            minutesLeft = active.cobMinutesRemaining,
        )
    }
}

@Composable
private fun ActiveStat(label: String, value: String, minutesLeft: Int?) {
    Row(verticalAlignment = Alignment.Bottom) {
        GTKicker(text = label, modifier = Modifier.padding(bottom = 3.dp))
        Spacer(Modifier.width(6.dp))
        Text(
            text = value,
            color = GT.colors.ink,
            style = GT.type.monoLabel.copy(fontSize = 15.sp, lineHeight = 18.sp),
            maxLines = 1,
        )
        if (minutesLeft != null && minutesLeft > 0) {
            Text(
                text = stringResource(R.string.glucose_remaining, formatClockDuration(minutesLeft)),
                modifier = Modifier.padding(start = 6.dp, bottom = 1.dp),
                color = GT.colors.muted,
                style = GT.type.monoLabel.copy(fontSize = 11.sp),
                maxLines = 1,
            )
        }
    }
}

/** 3 ч / 6 ч chips, the window's time span, and a way back to now. */
@Composable
private fun FocusControls(
    state: GlucoseScreenState,
    onSelectWindow: (FocusWindow) -> Unit,
    onFollowLive: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        FocusWindow.entries.forEach { window ->
            WindowChip(
                text = stringResource(window.labelRes()),
                selected = window == state.focusWindow,
                onClick = { onSelectWindow(window) },
            )
        }
        Spacer(Modifier.weight(1f))
        Text(
            text = stringResource(R.string.glucose_focus_range, state.focusFrom.hourMinute(), state.focusEnd.hourMinute()),
            color = GT.colors.ink2,
            style = GT.type.monoLabel.copy(fontSize = 12.sp),
            maxLines = 1,
        )
        if (!state.isLive) {
            WindowChip(
                text = stringResource(R.string.glucose_follow_live),
                selected = false,
                onClick = onFollowLive,
            )
        }
    }
}

@Composable
private fun WindowChip(text: String, selected: Boolean, onClick: () -> Unit) {
    val shape = RoundedCornerShape(14.dp)
    Box(
        modifier = Modifier
            .heightIn(min = GT.space.touch)
            .clickable(role = Role.Tab, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .height(28.dp)
                .background(if (selected) GT.colors.ink else GT.colors.surface, shape)
                .border(GT.space.hairline, if (selected) GT.colors.ink else GT.colors.hairline2, shape)
                .padding(horizontal = 14.dp),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = text,
                color = if (selected) GT.colors.surface2 else GT.colors.ink2,
                style = GT.type.sansLabel,
                maxLines = 1,
            )
        }
    }
}

/** Today's time in range as the server measured it, in one line. */
@Composable
private fun TirTodayLine(tir: GlucoseTirDay) {
    val low = (tir.veryLowPercent ?: 0.0) + (tir.lowPercent ?: 0.0)
    val high = (tir.highPercent ?: 0.0) + (tir.veryHighPercent ?: 0.0)
    val inRange = tir.inRangePercent
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = inRange?.let(::formatPercent) ?: stringResource(R.string.glucose_value_empty),
            color = GT.colors.ink,
            style = GT.type.monoNumber.copy(fontSize = 18.sp),
            maxLines = 1,
        )
        Column(
            modifier = Modifier
                .weight(1f)
                .padding(start = 10.dp),
        ) {
            Text(
                text = stringResource(R.string.glucose_tir_line, formatPercent(low), formatPercent(high)),
                color = GT.colors.muted,
                style = GT.type.monoLabel.copy(fontSize = 11.sp),
                maxLines = 1,
            )
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 4.dp)
                    .height(5.dp)
                    .background(GT.colors.hairline),
            ) {
                listOf(
                    low to GT.colors.info,
                    (inRange ?: 0.0) to GT.colors.good,
                    high to GT.colors.warn,
                ).forEach { (percent, color) ->
                    if (percent > 0.0) {
                        Box(
                            modifier = Modifier
                                .weight(percent.toFloat())
                                .height(5.dp)
                                .background(color),
                        )
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun GlucoseSheet(
    activeSensor: SensorSession?,
    onDismiss: () -> Unit,
    onSubmit: (Double) -> Unit,
    onOpenSensors: () -> Unit,
) {
    var valueText by remember { mutableStateOf("") }
    val parsedValue = valueText.replace(',', '.').toDoubleOrNull()
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
                text = stringResource(R.string.glucose_sheet_title),
                color = GT.colors.ink,
                style = GT.type.serifSection,
            )
            Text(
                text = stringResource(R.string.glucose_sheet_value_label),
                modifier = Modifier.padding(top = 16.dp),
                color = GT.colors.muted,
                style = GT.type.kicker,
            )
            BasicTextField(
                value = valueText,
                onValueChange = { valueText = it },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(44.dp)
                    .padding(top = 6.dp)
                    .background(GT.colors.surface2, GT.shapes.tag)
                    .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.tag)
                    .padding(horizontal = 12.dp),
                textStyle = GT.type.monoNumber.copy(color = GT.colors.ink),
                singleLine = true,
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Decimal,
                ),
                decorationBox = { inner ->
                    Box(contentAlignment = Alignment.CenterStart) {
                        inner()
                    }
                },
            )
            GTOutlineButton(
                text = stringResource(R.string.glucose_sheet_submit),
                enabled = parsedValue != null,
                onClick = { parsedValue?.let(onSubmit) },
                modifier = Modifier.padding(top = 14.dp),
            )
            Text(
                text = stringResource(R.string.glucose_sensor_title),
                modifier = Modifier.padding(top = 20.dp),
                color = GT.colors.muted,
                style = GT.type.kicker,
            )
            if (activeSensor == null) {
                Text(
                    text = stringResource(R.string.glucose_sensor_empty),
                    modifier = Modifier.padding(top = 6.dp),
                    color = GT.colors.ink2,
                    style = GT.type.sansBody,
                )
            } else {
                Text(
                    text = activeSensor.label ?: stringResource(R.string.sensor_default_name),
                    modifier = Modifier.padding(top = 6.dp),
                    color = GT.colors.ink,
                    style = GT.type.sansBody,
                )
                Text(
                    text = stringResource(
                        R.string.glucose_sensor_active_since,
                        activeSensor.startedAt.shortDateTime(),
                    ),
                    modifier = Modifier.padding(top = 2.dp),
                    color = GT.colors.ink2,
                    style = GT.type.monoLabel,
                )
            }
            GTOutlineButton(
                text = stringResource(R.string.glucose_sensor_manage),
                onClick = onOpenSensors,
                modifier = Modifier.padding(top = 10.dp),
            )
        }
    }
}

@Composable
private fun FingerstickGlyph() {
    val color = GT.colors.ink2
    Canvas(modifier = Modifier.size(16.dp)) {
        val stroke = Stroke(width = 1.4.dp.toPx(), cap = StrokeCap.Round)
        drawLine(
            color = color,
            start = Offset(size.width * 0.25f, size.height * 0.75f),
            end = Offset(size.width * 0.75f, size.height * 0.25f),
            strokeWidth = stroke.width,
            cap = StrokeCap.Round,
        )
        drawCircle(
            color = color,
            radius = 3.dp.toPx(),
            center = Offset(size.width * 0.68f, size.height * 0.32f),
            style = stroke,
        )
    }
}

private fun FocusWindow.labelRes(): Int =
    when (this) {
        FocusWindow.ThreeHours -> R.string.glucose_window_3h
        FocusWindow.SixHours -> R.string.glucose_window_6h
    }

private fun Instant.shortDateTime(): String {
    val local = toLocalDateTime(TimeZone.currentSystemDefault())
    return "%02d.%02d · %02d:%02d".format(local.dayOfMonth, local.monthNumber, local.hour, local.minute)
}

/** Typographical minus via the shared helper, never a hyphen. */
internal fun formatDelta(delta: Double): String = formatSignedMmol(delta)
