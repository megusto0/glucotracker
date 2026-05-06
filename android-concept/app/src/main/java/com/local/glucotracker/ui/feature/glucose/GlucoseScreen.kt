package com.local.glucotracker.ui.feature.glucose

import androidx.compose.foundation.Canvas
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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.GlucoseReading
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHintBox
import com.local.glucotracker.ui.design.primitives.GTIconButton
import com.local.glucotracker.ui.design.primitives.GTKicker
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.design.primitives.GTSegmented
import com.local.glucotracker.ui.format.formatMmol
import com.local.glucotracker.ui.format.formatPercent
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlinx.coroutines.launch
import kotlinx.datetime.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

@Composable
fun GlucoseRoute(
    viewModel: GlucoseViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsState()
    GlucoseScreen(
        state = state,
        onSelectWindow = viewModel::selectWindow,
        onFingerstickSubmit = viewModel::enqueueFingerstick,
    )
}

@Composable
fun GlucoseScreen(
    state: GlucoseScreenState,
    onSelectWindow: (GlucoseWindow) -> Unit,
    onFingerstickSubmit: (Double) -> Unit,
    modifier: Modifier = Modifier,
) {
    var sheetVisible by remember { mutableStateOf(false) }
    val selectedState = state.windows.firstOrNull { it.window == state.selectedWindow }
        ?: state.windows.first()
    val pagerState = rememberPagerState(
        initialPage = state.windows.indexOfFirst { it.window == state.selectedWindow }.coerceAtLeast(0),
        pageCount = { state.windows.size },
    )
    val scope = rememberCoroutineScope()
    val windowOptions = state.windows.map { windowState ->
        windowState.window to stringResource(windowState.window.labelRes())
    }

    LaunchedEffect(state.selectedWindow) {
        val index = state.windows.indexOfFirst { it.window == state.selectedWindow }
        if (index >= 0 && pagerState.currentPage != index) {
            pagerState.scrollToPage(index)
        }
    }
    LaunchedEffect(pagerState, state.windows) {
        snapshotFlow { pagerState.currentPage }.collect { page ->
            state.windows.getOrNull(page)?.window?.let(onSelectWindow)
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 18.dp, vertical = 12.dp),
    ) {
        GlucoseHeader(
            state = selectedState,
            onSheetOpen = { sheetVisible = true },
        )
        GTSegmented(
            options = windowOptions.map { it.second },
            selected = windowOptions.firstOrNull { it.first == state.selectedWindow }?.second.orEmpty(),
            onSelect = { selected ->
                windowOptions
                    .firstOrNull { it.second == selected }
                    ?.let { (window, _) ->
                        onSelectWindow(window)
                        val index = state.windows.indexOfFirst { it.window == window }
                        if (index >= 0) {
                            scope.launch {
                                pagerState.scrollToPage(index)
                            }
                        }
                    }
            },
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 18.dp),
        )
        HorizontalPager(
            state = pagerState,
            userScrollEnabled = true,
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = 520.dp)
                .padding(top = 14.dp),
        ) { page ->
            GlucoseWindowPage(
                state = state.windows[page],
                dayparts = state.dayparts,
            )
        }
    }

    if (sheetVisible) {
        GlucoseSheet(
            onDismiss = { sheetVisible = false },
            onSubmit = { value ->
                onFingerstickSubmit(value)
                sheetVisible = false
            },
        )
    }
}

@Composable
private fun GlucoseHeader(
    state: GlucoseWindowState,
    onSheetOpen: () -> Unit,
) {
    val latest = state.latest
    val stale = state.latestAgeMinutes != null && state.latestAgeMinutes > 15
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.Top,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            GTKicker(text = stringResource(R.string.glucose_kicker))
            Row(
                modifier = Modifier.padding(top = 4.dp),
                verticalAlignment = Alignment.Bottom,
            ) {
                Text(
                    text = latest?.displayValueMmolL?.let(::formatMmol)
                        ?: stringResource(R.string.glucose_value_empty),
                    color = if (stale) GT.colors.ink2 else GT.colors.ink,
                    style = GT.type.monoNumber.copy(fontSize = 44.sp, lineHeight = 48.sp),
                    maxLines = 1,
                )
                if (!stale && state.delta15Mmol != null) {
                    Text(
                        text = formatDelta(state.delta15Mmol),
                        modifier = Modifier.padding(start = 10.dp, bottom = 7.dp),
                        color = GT.colors.muted,
                        style = GT.type.monoLabel,
                        maxLines = 1,
                    )
                }
            }
            Text(
                text = latestKicker(state),
                color = GT.colors.muted,
                style = GT.type.monoLabel,
                maxLines = 1,
            )
        }
        val sheetDescription = stringResource(R.string.glucose_sheet_content_description)
        GTIconButton(
            onClick = onSheetOpen,
            modifier = Modifier.semantics { contentDescription = sheetDescription },
        ) {
            FingerstickGlyph()
        }
    }
}

@Composable
private fun latestKicker(state: GlucoseWindowState): String =
    when {
        state.latest == null -> stringResource(R.string.glucose_sensor_empty)
        state.latestAgeMinutes != null && state.latestAgeMinutes > 15 ->
            stringResource(R.string.glucose_last_value, state.latest.readingAt.hourMinute())
        else -> stringResource(R.string.glucose_minutes_ago, state.latestAgeMinutes ?: 0)
    }

@Composable
private fun GlucoseWindowPage(
    state: GlucoseWindowState,
    dayparts: List<GlucoseDaypartUi>,
) {
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        if (state.readings.isEmpty()) {
            GTHintBox(text = stringResource(R.string.glucose_empty, stringResource(state.window.labelRes())))
        } else {
            if (state.hasGap) {
                Text(
                    text = stringResource(R.string.glucose_gap, state.readings.last().readingAt.hourMinute()),
                    color = GT.colors.muted,
                    style = GT.type.monoLabel,
                )
            }
            GlucoseChart(
                state = state,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(180.dp),
            )
            TirStrip(state = state)
            DaypartGrid(dayparts = dayparts)
        }
    }
}

@Composable
private fun GlucoseChart(
    state: GlucoseWindowState,
    modifier: Modifier = Modifier,
) {
    val chartPoints = remember(state.window, state.readings) {
        state.readings.toChartPoints(state.window)
    }
    val description = chartDescription(state)
    val surface = GT.colors.surface
    val shape = GT.shapes.card
    val hairline = GT.space.hairline
    val hairlineColor = GT.colors.hairline
    val good = GT.colors.good
    val ink = GT.colors.ink
    val ink2 = GT.colors.ink2
    Canvas(
        modifier = modifier
            .background(surface, shape)
            .border(hairline, hairlineColor, shape)
            .semantics { contentDescription = description }
            .padding(12.dp),
    ) {
        if (chartPoints.size < 2) return@Canvas
        val minValue = min(3.5, chartPoints.minOf { it.valueMmol })
        val maxValue = max(10.5, chartPoints.maxOf { it.valueMmol })
        val range = (maxValue - minValue).takeIf { it > 0.01 } ?: 1.0
        fun y(value: Double): Float =
            size.height - ((value - minValue) / range * size.height).toFloat()
        fun x(at: Instant): Float {
            val total = state.to.toEpochMilliseconds() - state.from.toEpochMilliseconds()
            val offset = at.toEpochMilliseconds() - state.from.toEpochMilliseconds()
            return (offset.toDouble() / total.toDouble() * size.width).toFloat().coerceIn(0f, size.width)
        }

        val bandTop = y(10.0)
        val bandBottom = y(4.0)
        drawRect(
            color = good.copy(alpha = 0.18f),
            topLeft = Offset(0f, bandTop),
            size = Size(size.width, bandBottom - bandTop),
        )
        val boundaryStroke = Stroke(
            width = 1.dp.toPx(),
            pathEffect = PathEffect.dashPathEffect(floatArrayOf(4.dp.toPx(), 4.dp.toPx())),
        )
        drawLine(
            color = good.copy(alpha = 0.58f),
            start = Offset(0f, bandTop),
            end = Offset(size.width, bandTop),
            strokeWidth = boundaryStroke.width,
            pathEffect = boundaryStroke.pathEffect,
        )
        drawLine(
            color = good.copy(alpha = 0.58f),
            start = Offset(0f, bandBottom),
            end = Offset(size.width, bandBottom),
            strokeWidth = boundaryStroke.width,
            pathEffect = boundaryStroke.pathEffect,
        )
        val path = Path().apply {
            chartPoints.forEachIndexed { index, point ->
                val pointOffset = Offset(x(point.at), y(point.valueMmol))
                if (index == 0) moveTo(pointOffset.x, pointOffset.y) else lineTo(pointOffset.x, pointOffset.y)
            }
        }
        drawPath(
            path = path,
            color = ink2,
            style = Stroke(
                width = 2.dp.toPx(),
                cap = StrokeCap.Round,
                join = StrokeJoin.Round,
            ),
        )
        state.mealMarkers.forEach { marker ->
            drawCircle(
                color = ink,
                radius = 2.4.dp.toPx(),
                center = Offset(x(marker), 5.dp.toPx()),
            )
        }
        state.latest?.let { latest ->
            drawCircle(
                color = surface,
                radius = 4.5.dp.toPx(),
                center = Offset(x(latest.readingAt), y(latest.displayValueMmolL)),
            )
            drawCircle(
                color = ink,
                radius = 4.5.dp.toPx(),
                center = Offset(x(latest.readingAt), y(latest.displayValueMmolL)),
                style = Stroke(width = 1.5.dp.toPx()),
            )
        }
    }
}

@Composable
private fun chartDescription(state: GlucoseWindowState): String {
    if (state.readings.isEmpty()) return stringResource(R.string.glucose_chart_empty_description)
    val minValue = state.readings.minOf { it.displayValueMmolL }
    val maxValue = state.readings.maxOf { it.displayValueMmolL }
    val trend = state.delta15Mmol?.let(::formatDelta) ?: stringResource(R.string.glucose_value_empty)
    return stringResource(
        R.string.glucose_chart_description,
        formatMmol(minValue),
        formatMmol(maxValue),
        trend,
    )
}

@Composable
private fun TirStrip(state: GlucoseWindowState) {
    val emptyValue = stringResource(R.string.glucose_value_empty)
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .padding(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            GTKicker(text = stringResource(R.string.glucose_tir_title))
            Spacer(Modifier.weight(1f))
            if (state.tirFetchedAt != null && state.latestAgeMinutes != null && state.latestAgeMinutes > 15) {
                Text(
                    text = stringResource(R.string.glucose_tir_cached_at, state.tirFetchedAt.hourMinute()),
                    color = GT.colors.muted,
                    style = GT.type.monoLabel,
                )
            }
        }
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(10.dp)
                .padding(top = 6.dp)
                .background(GT.colors.hairline),
        ) {
            val knownTotal = state.tirSegments.sumOf { it.percent ?: 0 }
            state.tirSegments.forEach { segment ->
                if (knownTotal > 0 && segment.percent != null) {
                    Box(
                        modifier = Modifier
                            .weight(segment.percent.toFloat())
                            .height(10.dp)
                            .background(segment.bucket.color()),
                    )
                }
            }
        }
        Row(
            modifier = Modifier.padding(top = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            state.tirSegments.forEach { segment ->
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = segment.bucket.label(),
                        color = GT.colors.muted,
                        style = GT.type.kicker,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        text = segment.percent?.let { formatPercent(it.toDouble()) } ?: emptyValue,
                        color = GT.colors.ink,
                        style = GT.type.monoLabel,
                        maxLines = 1,
                    )
                }
            }
        }
    }
}

@Composable
private fun DaypartGrid(dayparts: List<GlucoseDaypartUi>) {
    Column {
        GTKicker(text = stringResource(R.string.glucose_dayparts_title))
        dayparts.chunked(2).forEachIndexed { index, row ->
            Row(
                modifier = Modifier.padding(top = if (index == 0) 8.dp else 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                row.forEach { daypart ->
                    DaypartCard(
                        daypart = daypart,
                        modifier = Modifier.weight(1f),
                    )
                }
            }
        }
    }
}

@Composable
private fun DaypartCard(
    daypart: GlucoseDaypartUi,
    modifier: Modifier = Modifier,
) {
    val emptyValue = stringResource(R.string.glucose_value_empty)
    val value = daypart.valueMmol?.let(::formatMmol) ?: emptyValue
    val description = if (daypart.valueMmol != null) {
        stringResource(R.string.glucose_daypart_description, daypart.label, value)
    } else {
        "${daypart.label}, ${stringResource(R.string.glucose_sensor_empty)}"
    }
    Column(
        modifier = modifier
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .semantics { contentDescription = description }
            .padding(12.dp),
    ) {
        Text(
            text = daypart.label,
            color = GT.colors.muted,
            style = GT.type.kicker,
            maxLines = 1,
        )
        Text(
            text = if (daypart.valueMmol != null) {
                stringResource(R.string.glucose_daypart_value, value)
            } else {
                value
            },
            modifier = Modifier.padding(top = 6.dp),
            color = GT.colors.ink,
            style = GT.type.monoLabel,
            maxLines = 1,
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun GlucoseSheet(
    onDismiss: () -> Unit,
    onSubmit: (Double) -> Unit,
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
            Text(
                text = stringResource(R.string.glucose_sensor_empty),
                modifier = Modifier.padding(top = 6.dp),
                color = GT.colors.ink2,
                style = GT.type.sansBody,
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

@Composable
private fun GlucoseTirBucket.label(): String =
    when (this) {
        GlucoseTirBucket.Low -> stringResource(R.string.glucose_tir_low)
        GlucoseTirBucket.InRange -> stringResource(R.string.glucose_tir_range)
        GlucoseTirBucket.High -> stringResource(R.string.glucose_tir_high)
        GlucoseTirBucket.VeryHigh -> stringResource(R.string.glucose_tir_very_high)
    }

@Composable
private fun GlucoseTirBucket.color(): Color =
    when (this) {
        GlucoseTirBucket.Low -> GT.colors.info
        GlucoseTirBucket.InRange -> GT.colors.good
        GlucoseTirBucket.High -> GT.colors.warn
        GlucoseTirBucket.VeryHigh -> GT.colors.bad
    }

private fun GlucoseWindow.labelRes(): Int =
    when (this) {
        GlucoseWindow.ThreeHours -> R.string.glucose_window_3h
        GlucoseWindow.SixHours -> R.string.glucose_window_6h
        GlucoseWindow.Day -> R.string.glucose_window_24h
        GlucoseWindow.Week -> R.string.glucose_window_7d
    }

private data class ChartPoint(
    val at: Instant,
    val valueMmol: Double,
)

private fun List<GlucoseReading>.toChartPoints(window: GlucoseWindow): List<ChartPoint> {
    val bucketMinutes = when (window) {
        GlucoseWindow.ThreeHours,
        GlucoseWindow.SixHours,
        -> 0
        GlucoseWindow.Day -> 30
        GlucoseWindow.Week -> 180
    }
    if (bucketMinutes == 0) {
        return map { ChartPoint(at = it.readingAt, valueMmol = it.displayValueMmolL) }
    }
    return groupBy { reading ->
        reading.readingAt.toEpochMilliseconds() / (bucketMinutes * 60_000L)
    }.values.map { bucket ->
        val avgTime = bucket.map { it.readingAt.toEpochMilliseconds() }.average().toLong()
        ChartPoint(
            at = Instant.fromEpochMilliseconds(avgTime),
            valueMmol = bucket.map { it.displayValueMmolL }.average(),
        )
    }.sortedBy { it.at }
}

private fun Instant.hourMinute(): String {
    val time = toLocalDateTime(TimeZone.currentSystemDefault()).time
    return "${time.hour.toString().padStart(2, '0')}:${time.minute.toString().padStart(2, '0')}"
}

private fun formatDelta(delta: Double): String {
    val sign = if (delta < 0) "−" else "+"
    return "$sign${formatMmol(abs(delta))}"
}
