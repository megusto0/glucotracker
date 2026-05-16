package com.local.glucotracker.ui.glucose

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.GlucoseReading
import com.local.glucotracker.domain.model.GlucoseRange
import com.local.glucotracker.domain.model.InsulinEvent
import com.local.glucotracker.domain.model.InsulinEventType
import com.local.glucotracker.domain.model.NightscoutConnectionState
import com.local.glucotracker.domain.model.PairableMeal
import com.local.glucotracker.domain.model.pairInsulinWithMeals
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTHintBox
import com.local.glucotracker.ui.design.primitives.GTKicker
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.design.tokens.GTColors
import com.local.glucotracker.ui.feature.history.HistoryMealRowUi
import com.local.glucotracker.ui.feature.today.TodayMealRowUi
import com.local.glucotracker.ui.format.formatMmol
import java.text.DecimalFormat
import java.text.DecimalFormatSymbols
import java.util.Locale
import javax.inject.Inject
import kotlinx.datetime.Clock
import kotlinx.datetime.DatePeriod
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.atStartOfDayIn
import kotlinx.datetime.plus
import kotlinx.datetime.toLocalDateTime
import kotlinx.coroutines.delay
import kotlin.math.abs
import kotlin.math.sqrt

class GlucoseSurfacesReal @Inject constructor() : GlucoseSurfaces {
    @Composable
    override fun MiniGlucoseCard(modifier: Modifier) {
        MiniGlucoseSurface(modifier)
    }

    @Composable
    override fun StatsTirSection() {
        GlucoseNoteCard(
            title = stringResource(R.string.stats_chart_tir),
            text = stringResource(R.string.stats_tir_empty),
        )
    }

    @Composable
    override fun StatsDaypartSection() {
        GlucoseNoteCard(
            title = stringResource(R.string.stats_chart_dayparts),
            text = stringResource(R.string.stats_daypart_caption),
        )
    }

    @Composable
    override fun RecordGlucoseAtMealPanel(eatenAt: Instant) {
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
                color = GT.colors.info,
                style = GT.type.sansLabel,
            )
        }
    }

    @Composable
    override fun StackMealGlucoseMetaRow(eatenAt: Instant) {
        StackGlucoseMetaRow(eatenAt)
    }

    @Composable
    override fun StackMealContextMetaRows(
        mealId: String?,
        eatenAt: Instant,
        meals: List<MealContextAnchor>,
    ) {
        val viewModel: InsulinContextViewModel = hiltViewModel()
        val date = eatenAt.toLocalDateTime(TimeZone.currentSystemDefault()).date
        val events by viewModel.events(date).collectAsStateWithLifecycle(initialValue = emptyList())
        val paired = remember(date, mealId, eatenAt, meals, events) {
            pairInsulinWithMeals(
                date = date,
                meals = (meals.ifEmpty {
                    listOf(MealContextAnchor(id = mealId.orEmpty(), eatenAt = eatenAt))
                }).map { meal ->
                    PairableMeal(
                        value = meal,
                        id = meal.id,
                        eatenAt = meal.eatenAt,
                    )
                },
                insulinEvents = events,
            ).mealsWithInsulin
                .firstOrNull { item -> item.meal.id == mealId }
                ?.pairedInsulin
                .orEmpty()
        }
        if (paired.isNotEmpty()) {
            InsulinMetaRow(events = paired)
        }
    }

    @Composable
    override fun TodayRows(
        date: LocalDate,
        rows: List<TodayMealRowUi>,
        rowContent: @Composable (
            row: TodayMealRowUi,
            extraMetaContent: @Composable ColumnScope.() -> Unit,
        ) -> Unit,
    ) {
        val viewModel: InsulinContextViewModel = hiltViewModel()
        val events by viewModel.events(date).collectAsStateWithLifecycle(initialValue = emptyList())
        InsulinAwareRows(
            date = date,
            rows = rows,
            events = events,
            rowId = { row -> row.id },
            rowTime = { row -> row.eatenAt },
            rowContent = rowContent,
        )
    }

    @Composable
    override fun HistoryRows(
        date: LocalDate,
        rows: List<HistoryMealRowUi>,
        rowContent: @Composable (
            row: HistoryMealRowUi,
            extraMetaContent: @Composable ColumnScope.() -> Unit,
        ) -> Unit,
        divider: @Composable () -> Unit,
    ) {
        val viewModel: InsulinContextViewModel = hiltViewModel()
        val events by viewModel.events(date).collectAsStateWithLifecycle(initialValue = emptyList())
        InsulinAwareRows(
            date = date,
            rows = rows,
            events = events,
            rowId = { row -> row.id },
            rowTime = { row -> row.eatenAt },
            rowContent = rowContent,
            separator = divider,
        )
    }

    @Composable
    override fun HistoryDayTimeline(
        date: LocalDate,
        meals: List<HistoryTimelineMeal>,
        onMealTap: (String) -> Unit,
        modifier: Modifier,
    ) {
        val viewModel: GlucoseSparklineViewModel = hiltViewModel()
        val readings by viewModel.readings(date).collectAsStateWithLifecycle(initialValue = emptyList())
        DayTimelineGluco(
            meals = meals,
            readings = readings,
            onMealTap = onMealTap,
            modifier = modifier,
        )
    }

    @Composable
    override fun MoreNightscoutSection() {
        MoreNightscoutSurface()
        GTHairlineDivider()
    }
}

@Composable
private fun StackGlucoseMetaRow(eatenAt: Instant) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 3.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = stringResource(R.string.record_glucose_kicker),
            color = GT.colors.muted,
            style = GT.type.kicker.copy(fontSize = 8.sp),
            maxLines = 1,
        )
        Text(
            text = stringResource(R.string.stack_glucose_meta_value, eatenAt.timeText()),
            modifier = Modifier.padding(start = 10.dp),
            color = GT.colors.ink2,
            style = GT.type.monoLabel.copy(fontSize = 10.sp),
            maxLines = 1,
        )
    }
}

@Composable
private fun <T> InsulinAwareRows(
    date: LocalDate,
    rows: List<T>,
    events: List<InsulinEvent>,
    rowId: (T) -> String,
    rowTime: (T) -> Instant,
    rowContent: @Composable (
        row: T,
        extraMetaContent: @Composable ColumnScope.() -> Unit,
    ) -> Unit,
    separator: @Composable () -> Unit = { Spacer(Modifier.height(14.dp)) },
) {
    val dayContent = remember(date, rows, events) {
        pairInsulinWithMeals(
            date = date,
            meals = rows.map { row ->
                PairableMeal(
                    value = row,
                    id = rowId(row),
                    eatenAt = rowTime(row),
                )
            },
            insulinEvents = events,
        )
    }
    val timeline = remember(dayContent) {
        (
            dayContent.mealsWithInsulin.map { item ->
                InsulinTimelineItem.Meal(
                    row = item.meal,
                    paired = item.pairedInsulin,
                    timestamp = rowTime(item.meal),
                )
            } +
                dayContent.orphanInsulin.map { event ->
                    InsulinTimelineItem.Orphan(event = event, timestamp = event.timestamp)
                }
            ).sortedByDescending { item -> item.timestamp }
    }

    timeline.forEachIndexed { index, item ->
        when (item) {
            is InsulinTimelineItem.Meal -> {
                rowContent(item.row) {
                    item.paired.forEach { event ->
                        InlineInsulinLine(event = event)
                    }
                }
            }
            is InsulinTimelineItem.Orphan -> OrphanInsulinRow(event = item.event)
        }
        if (index < timeline.lastIndex) separator()
    }
}

private sealed interface InsulinTimelineItem<out T> {
    val timestamp: Instant

    data class Meal<T>(
        val row: T,
        val paired: List<InsulinEvent>,
        override val timestamp: Instant,
    ) : InsulinTimelineItem<T>

    data class Orphan(
        val event: InsulinEvent,
        override val timestamp: Instant,
    ) : InsulinTimelineItem<Nothing>
}

@Composable
private fun InlineInsulinLine(event: InsulinEvent) {
    var showTooltip by remember(event.id) { mutableStateOf(false) }
    LaunchedEffect(showTooltip) {
        if (showTooltip) {
            delay(1_500)
            showTooltip = false
        }
    }
    Column(modifier = Modifier.padding(top = 3.dp)) {
        Row(
            modifier = Modifier.pointerInput(event.id) {
                detectTapGestures(
                    onTap = {},
                    onLongPress = { showTooltip = true },
                )
            },
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "+ ${formatInsulinDose(event.doseUnits)} ${stringResource(R.string.insulin_units_short)} · ${event.timestamp.timeText()}",
                color = GT.colors.ink2.copy(alpha = 0.72f),
                style = GT.type.monoLabel.copy(fontSize = 10.sp),
                maxLines = 1,
            )
            Spacer(Modifier.width(6.dp))
            Text(
                text = event.sourceSuffix(),
                color = GT.colors.ink2.copy(alpha = 0.46f),
                style = GT.type.monoLabel.copy(fontSize = 10.sp),
                maxLines = 1,
            )
        }
        if (showTooltip) {
            InsulinTooltip(event = event)
        }
    }
}

@Composable
private fun OrphanInsulinRow(event: InsulinEvent) {
    var showTooltip by remember(event.id) { mutableStateOf(false) }
    LaunchedEffect(showTooltip) {
        if (showTooltip) {
            delay(1_500)
            showTooltip = false
        }
    }
    Column(modifier = Modifier.padding(horizontal = 18.dp)) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = 28.dp)
                .pointerInput(event.id) {
                    detectTapGestures(
                        onTap = {},
                        onLongPress = { showTooltip = true },
                    )
                }
                .padding(vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = event.timestamp.timeText(),
                modifier = Modifier.width(36.dp),
                color = GT.colors.muted,
                style = GT.type.monoLabel.copy(fontSize = 10.sp),
                maxLines = 1,
            )
            Text(
                text = "+",
                modifier = Modifier.width(32.dp),
                color = GT.colors.ink2.copy(alpha = 0.7f),
                style = GT.type.monoLabel.copy(fontSize = 12.sp),
                maxLines = 1,
            )
            Text(
                text = listOfNotNull(
                    "${formatInsulinDose(event.doseUnits)} ${stringResource(R.string.insulin_units_short)}",
                    stringResource(R.string.insulin_correction).takeIf {
                        event.eventType == InsulinEventType.Correction
                    },
                ).joinToString("  "),
                modifier = Modifier.weight(1f),
                color = GT.colors.ink2.copy(alpha = 0.72f),
                style = GT.type.monoLabel.copy(fontSize = 10.sp),
                maxLines = 1,
            )
            Text(
                text = event.displaySource(),
                color = GT.colors.ink2.copy(alpha = 0.46f),
                style = GT.type.monoLabel.copy(fontSize = 10.sp),
                maxLines = 1,
            )
        }
        if (showTooltip) {
            InsulinTooltip(event = event)
        }
    }
}

@Composable
private fun InsulinMetaRow(events: List<InsulinEvent>) {
    val unit = stringResource(R.string.insulin_units_short)
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 3.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = stringResource(R.string.stack_meta_insulin),
            color = GT.colors.muted,
            style = GT.type.kicker.copy(fontSize = 8.sp),
            maxLines = 1,
        )
        Text(
            text = events.joinToString("; ") { event ->
                "${formatInsulinDose(event.doseUnits)} $unit · ${event.timestamp.timeText()}"
            },
            modifier = Modifier.padding(start = 10.dp),
            color = GT.colors.ink2,
            style = GT.type.monoLabel.copy(fontSize = 10.sp),
            maxLines = 1,
        )
    }
}

@Composable
private fun InsulinTooltip(event: InsulinEvent) {
    Box(
        modifier = Modifier
            .padding(top = 4.dp)
            .background(GT.colors.surface2, GT.shapes.tag)
            .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.tag)
            .padding(horizontal = 8.dp, vertical = 5.dp),
    ) {
        Text(
            text = stringResource(
                R.string.insulin_attribution_tooltip,
                event.displaySource(),
                event.sourceEventId ?: event.id,
            ),
            color = GT.colors.ink2,
            style = GT.type.monoLabel.copy(fontSize = 10.sp),
            maxLines = 1,
        )
    }
}

@Composable
private fun InsulinEvent.sourceSuffix(): String =
    if (eventType == InsulinEventType.Correction) {
        "${stringResource(R.string.insulin_correction)} · ${displaySource()}"
    } else {
        displaySource()
    }

@Composable
private fun InsulinEvent.displaySource(): String =
    if (source.equals("nightscout", ignoreCase = true)) {
        stringResource(R.string.insulin_source_nightscout)
    } else {
        source
    }

private fun formatInsulinDose(value: Double): String =
    InsulinDoseFormat.format(value)

private val InsulinDoseFormat = DecimalFormat(
    "0.0",
    DecimalFormatSymbols(Locale("ru")),
)

@Composable
private fun DayTimelineGluco(
    meals: List<HistoryTimelineMeal>,
    readings: List<GlucoseReading>,
    onMealTap: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = GT.colors
    val sortedMeals = androidx.compose.runtime.remember(meals) { meals.sortedBy { it.minutesOfDay } }
    val sortedReadings = androidx.compose.runtime.remember(readings) { readings.sortedBy { it.readingAt } }
    val hasReadings = sortedReadings.isNotEmpty()
    val scale = androidx.compose.runtime.remember(sortedReadings) { glucoseScale(sortedReadings) }
    Canvas(
        modifier = modifier
            .height(if (hasReadings) 48.dp else 28.dp)
            .pointerInput(sortedMeals, sortedReadings, scale) {
                detectTapGestures { offset ->
                    val baselineY = size.height / 2f
                    val laidOut = layoutHistoryTimelineCircles(
                        meals = sortedMeals.map { meal ->
                            val x = size.width * (meal.minutesOfDay / TimelineMinutesPerDay)
                            val y = glucoseYAtMeal(
                                meal = meal,
                                readings = sortedReadings,
                                baselineY = baselineY,
                                height = size.height.toFloat(),
                                scale = scale,
                            )
                            HistoryTimelineCircleInput(
                                id = meal.id,
                                x = x.coerceIn(0f, size.width.toFloat()),
                                naturalY = y,
                                radius = computeTimelineRadiusPx(meal.kcal),
                            )
                        },
                        padding = 2.dp.toPx(),
                    )
                    val tapped = laidOut
                        .asReversed()
                        .firstOrNull { layout ->
                            val hitRadius = maxOf(layout.radius, 12.dp.toPx())
                            (offset - Offset(layout.x, layout.y)).getDistance() <= hitRadius
                        }
                    tapped?.let { layout -> onMealTap(layout.id) }
                }
            },
    ) {
        val baselineY = size.height / 2f
        drawLine(
            color = colors.muted.copy(alpha = 0.2f),
            start = Offset(0f, baselineY),
            end = Offset(size.width, baselineY),
            strokeWidth = 1.dp.toPx(),
            cap = StrokeCap.Round,
        )

        if (sortedReadings.size >= 2 && scale != null) {
            val stroke = Stroke(width = 1.5.dp.toPx(), cap = StrokeCap.Round)
            splitContinuousReadings(sortedReadings).forEach { segment ->
                if (segment.size >= 2) {
                    drawPath(
                        path = buildGlucosePath(segment, size.width, size.height, scale),
                        color = colors.ink2.copy(alpha = 0.7f),
                        style = stroke,
                    )
                }
            }
            sortedReadings.zipWithNext()
                .filter { (a, b) -> minutesBetween(a.readingAt, b.readingAt) >= CgmGapMinutes }
                .forEach { (a, b) ->
                    drawPath(
                        path = buildGlucosePath(listOf(a, b), size.width, size.height, scale),
                        color = colors.muted.copy(alpha = 0.4f),
                        style = Stroke(
                            width = 1.dp.toPx(),
                            cap = StrokeCap.Round,
                            pathEffect = PathEffect.dashPathEffect(
                                floatArrayOf(4.dp.toPx(), 4.dp.toPx()),
                            ),
                        ),
                    )
                }
        }

        val mealsById = sortedMeals.associateBy { it.id }
        val laidOut = layoutHistoryTimelineCircles(
            meals = sortedMeals.map { meal ->
                val x = size.width * (meal.minutesOfDay / TimelineMinutesPerDay)
                val y = glucoseYAtMeal(
                    meal = meal,
                    readings = sortedReadings,
                    baselineY = baselineY,
                    height = size.height,
                    scale = scale,
                )
                HistoryTimelineCircleInput(
                    id = meal.id,
                    x = x.coerceIn(0f, size.width),
                    naturalY = y,
                    radius = computeTimelineRadiusPx(meal.kcal),
                )
            },
            padding = 2.dp.toPx(),
        )
        laidOut.forEach { layout ->
            val meal = mealsById.getValue(layout.id)
            val center = Offset(layout.x, layout.y)
            drawCircle(
                color = responseColor(
                    responseKey = meal.responseKey,
                    colors = colors,
                    alpha = 0.5f,
                ),
                radius = layout.radius,
                center = center,
            )
            drawCircle(
                color = if (meal.stuck) {
                    colors.warn.copy(alpha = 0.8f)
                } else {
                    responseColor(
                        responseKey = meal.responseKey,
                        colors = colors,
                        alpha = 0.8f,
                    )
                },
                radius = layout.radius,
                center = center,
                style = Stroke(width = 1.dp.toPx()),
            )
        }
    }
}

@Composable
private fun MiniGlucoseSurface(
    modifier: Modifier = Modifier,
    viewModel: MiniGlucoseViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    Row(
        modifier = modifier
            .fillMaxWidth()
            .height(88.dp)
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .padding(14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        when (val mini = state) {
            MiniGlucoseUiState.Empty -> {
                Text(
                    text = stringResource(R.string.today_glucose_no_fresh),
                    color = GT.colors.muted,
                    style = GT.type.sansBody,
                )
            }
            is MiniGlucoseUiState.Reading -> {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = formatMmol(mini.valueMmol),
                        color = GT.colors.ink,
                        style = GT.type.monoNumber,
                    )
                    Text(
                        text = if (mini.minutesAgo > 10) {
                            stringResource(R.string.today_glucose_stale, mini.minutesAgo)
                        } else {
                            mini.deltaMmol?.let { formatGlucoseDelta(it) }.orEmpty()
                        },
                        color = GT.colors.muted,
                        style = GT.type.monoLabel,
                    )
                }
                Sparkline(
                    points = mini.points,
                    modifier = Modifier.size(width = 112.dp, height = 42.dp),
                    color = GT.colors.info,
                )
            }
        }
    }
}

@Composable
private fun MoreNightscoutSurface(
    viewModel: MoreNightscoutViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    Column {
        GTKicker(text = stringResource(R.string.more_section_nightscout))
        Row(
            modifier = Modifier.padding(top = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            val connected = state.status.connectionState == NightscoutConnectionState.Connected
            Text(
                text = when {
                    state.isRefreshing -> stringResource(R.string.more_ns_checking)
                    connected -> stringResource(R.string.more_ns_connected)
                    else -> stringResource(R.string.more_ns_disconnected)
                },
                color = GT.colors.ink2,
                style = GT.type.sansBody,
                modifier = Modifier.weight(1f),
            )
            GTOutlineButton(
                text = if (state.isRefreshing) {
                    stringResource(R.string.more_ns_checking)
                } else {
                    stringResource(R.string.more_ns_sync_now)
                },
                onClick = viewModel::syncNow,
                enabled = !state.isRefreshing,
            )
        }
        if (state.status.queueDepth > 0) {
            Text(
                text = stringResource(R.string.more_ns_unsynced, state.status.queueDepth),
                modifier = Modifier.padding(top = 6.dp),
                color = GT.colors.warn,
                style = GT.type.monoLabel,
            )
        }
        GTHintBox(
            text = stringResource(R.string.more_ns_hint),
            modifier = Modifier.padding(top = 10.dp),
        )
    }
}

@Composable
private fun GlucoseNoteCard(
    title: String,
    text: String,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .padding(14.dp),
    ) {
        GTKicker(text = title)
        Text(
            text = text,
            modifier = Modifier.padding(top = 14.dp),
            color = GT.colors.muted,
            style = GT.type.sansBody,
        )
    }
}

@Composable
private fun Sparkline(
    points: List<Double>,
    modifier: Modifier = Modifier,
    color: Color,
) {
    Canvas(modifier = modifier) {
        if (points.size < 2) return@Canvas
        val min = points.minOrNull() ?: return@Canvas
        val max = points.maxOrNull() ?: return@Canvas
        val range = (max - min).takeIf { it > 0.01 } ?: 1.0
        val step = size.width / (points.size - 1)
        points.zipWithNext().forEachIndexed { index, pair ->
            val y1 = size.height - ((pair.first - min) / range * size.height).toFloat()
            val y2 = size.height - ((pair.second - min) / range * size.height).toFloat()
            drawLine(
                color = color,
                start = Offset(index * step, y1),
                end = Offset((index + 1) * step, y2),
                strokeWidth = 1.4.dp.toPx(),
                cap = StrokeCap.Round,
            )
        }
    }
}

private fun glucoseScale(readings: List<GlucoseReading>): Pair<Double, Double>? {
    val values = readings.map { it.displayValueMmolL }
    val min = values.minOrNull() ?: return null
    val max = values.maxOrNull() ?: return null
    val yMin = min.coerceIn(DisplayGlucoseMin, DisplayGlucoseMax)
    val yMax = max.coerceIn(DisplayGlucoseMin, DisplayGlucoseMax)
    return if (yMax - yMin >= 0.1) {
        yMin to yMax
    } else {
        DisplayGlucoseMin to DisplayGlucoseMax
    }
}

private fun splitContinuousReadings(readings: List<GlucoseReading>): List<List<GlucoseReading>> {
    if (readings.isEmpty()) return emptyList()
    val segments = mutableListOf<MutableList<GlucoseReading>>()
    readings.forEach { reading ->
        val current = segments.lastOrNull()
        if (current == null || minutesBetween(current.last().readingAt, reading.readingAt) >= CgmGapMinutes) {
            segments += mutableListOf(reading)
        } else {
            current += reading
        }
    }
    return segments
}

private fun buildGlucosePath(
    readings: List<GlucoseReading>,
    width: Float,
    height: Float,
    scale: Pair<Double, Double>,
): Path {
    val path = Path()
    val points = readings.map { reading ->
        Offset(
            x = width * (reading.minutesOfDay() / TimelineMinutesPerDay),
            y = glucoseY(reading.displayValueMmolL, height, scale),
        )
    }
    points.firstOrNull()?.let { first -> path.moveTo(first.x.coerceIn(0f, width), first.y) }
    points.zipWithNext().forEach { (a, b) ->
        val ax = a.x.coerceIn(0f, width)
        val bx = b.x.coerceIn(0f, width)
        val midX = (ax + bx) / 2f
        path.cubicTo(midX, a.y, midX, b.y, bx, b.y)
    }
    return path
}

private fun glucoseYAtMeal(
    meal: HistoryTimelineMeal,
    readings: List<GlucoseReading>,
    baselineY: Float,
    height: Float,
    scale: Pair<Double, Double>?,
): Float {
    if (readings.isEmpty() || scale == null) return baselineY
    val nearest = readings.minByOrNull { reading ->
        abs(reading.minutesOfDay() - meal.minutesOfDay)
    } ?: return baselineY
    return if (abs(nearest.minutesOfDay() - meal.minutesOfDay) <= CgmGapMinutes) {
        glucoseY(nearest.displayValueMmolL, height, scale)
    } else {
        baselineY
    }
}

private fun glucoseY(value: Double, height: Float, scale: Pair<Double, Double>): Float {
    val (yMin, yMax) = scale
    val range = (yMax - yMin).takeIf { it > 0.01 } ?: (DisplayGlucoseMax - DisplayGlucoseMin)
    val normalized = ((value.coerceIn(yMin, yMax) - yMin) / range).coerceIn(0.0, 1.0)
    return height - (normalized.toFloat() * height)
}

private fun GlucoseReading.minutesOfDay(): Int {
    val time = readingAt.toLocalDateTime(TimeZone.currentSystemDefault()).time
    return (time.hour * 60 + time.minute).coerceIn(0, TimelineMinutesPerDayInt - 1)
}

private fun minutesBetween(a: Instant, b: Instant): Long =
    abs(b.toEpochMilliseconds() - a.toEpochMilliseconds()) / 60_000L

private fun Density.computeTimelineRadiusPx(kcal: Int?): Float {
    val normalized = sqrt(((kcal ?: 0) / TimelineKcalNormalization).coerceIn(0f, 1f))
    return TimelineMinRadius.toPx() + normalized * (TimelineMaxRadius.toPx() - TimelineMinRadius.toPx())
}

private fun responseColor(
    responseKey: String?,
    colors: GTColors,
    alpha: Float,
): Color =
    when (responseKey?.lowercase()) {
        "spike" -> colors.warn.copy(alpha = alpha)
        "unstable" -> colors.warn.copy(alpha = alpha * 0.75f)
        "moderate" -> colors.info.copy(alpha = alpha)
        "gentle" -> colors.accent.copy(alpha = alpha)
        else -> colors.muted.copy(alpha = alpha)
    }

internal fun CachedView<GlucoseRange>.toMiniGlucose(): MiniGlucoseUiState {
    val readings = value?.readings.orEmpty()
    val latest = readings.lastOrNull() ?: return MiniGlucoseUiState.Empty
    val now = Clock.System.now()
    val ageMinutes = ((now.toEpochMilliseconds() - latest.readingAt.toEpochMilliseconds()) / 60_000L)
        .coerceAtLeast(0L)
        .toInt()
    if (ageMinutes > 60) return MiniGlucoseUiState.Empty
    val previous = readings.dropLast(1).lastOrNull()
    return MiniGlucoseUiState.Reading(
        valueMmol = latest.displayValueMmolL,
        deltaMmol = previous?.let { latest.displayValueMmolL - it.displayValueMmolL },
        minutesAgo = ageMinutes,
        points = readings.takeLast(24).map { it.displayValueMmolL },
    )
}

internal fun LocalDate.dayBounds(): Pair<Instant, Instant> {
    val from = atStartOfDayIn(TimeZone.currentSystemDefault())
    val to = plus(DatePeriod(days = 1)).atStartOfDayIn(TimeZone.currentSystemDefault())
    return from to to
}

private fun Instant.timeText(): String {
    val time = toLocalDateTime(TimeZone.currentSystemDefault()).time
    return "${time.hour.toString().padStart(2, '0')}:${time.minute.toString().padStart(2, '0')}"
}

private fun formatGlucoseDelta(delta: Double): String {
    val sign = if (delta < 0) "\u2212" else "+"
    return "$sign${formatMmol(abs(delta))}"
}

private val TimelineMinRadius = 4.dp
private val TimelineMaxRadius = 14.dp
private const val TimelineKcalNormalization = 700f
private const val TimelineMinutesPerDay = 1_440f
private const val TimelineMinutesPerDayInt = 1_440
private const val CgmGapMinutes = 10L
private const val DisplayGlucoseMin = 3.0
private const val DisplayGlucoseMax = 12.0
