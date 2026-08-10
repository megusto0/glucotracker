package com.local.glucotracker.ui.glucose

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
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
import androidx.compose.ui.res.stringArrayResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.R
import com.local.glucotracker.data.api.GlucoseApi
import com.local.glucotracker.generated.model.ActivityAnnotationPutRequest
import com.local.glucotracker.generated.model.BodyStateBreakdownResponse
import com.local.glucotracker.generated.model.BodyStatePointResponse
import com.local.glucotracker.generated.model.SleepStageResponse
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTHintBox
import com.local.glucotracker.ui.feature.history.FilterChip
import com.local.glucotracker.ui.format.formatMmol
import com.local.glucotracker.ui.format.formatPercent
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import java.util.Locale
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.roundToInt
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.datetime.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

data class BodyStateBreakdownState(
    val value: BodyStateBreakdownResponse? = null,
    val loading: Boolean = false,
    val failed: Boolean = false,
    val saving: Boolean = false,
)

@HiltViewModel
class BodyStateBreakdownViewModel @Inject constructor(
    private val glucoseApi: GlucoseApi,
) : ViewModel() {
    private val mutableState = MutableStateFlow(BodyStateBreakdownState())
    val state: StateFlow<BodyStateBreakdownState> = mutableState.asStateFlow()

    fun load(bodyState: BodyState) {
        if (
            mutableState.value.value?.startAt == bodyState.startAt &&
            mutableState.value.value?.endAt == bodyState.endAt
        ) return
        viewModelScope.launch {
            mutableState.value = BodyStateBreakdownState(loading = true)
            runCatching {
                glucoseApi.bodyStateBreakdown(
                    kind = when (bodyState.kind) {
                        BodyState.Kind.Sleep -> "sleep"
                        BodyState.Kind.Activity -> "activity"
                    },
                    start = bodyState.startAt,
                    end = bodyState.endAt,
                )
            }.onSuccess { response ->
                mutableState.value = BodyStateBreakdownState(value = response)
            }.onFailure {
                mutableState.value = BodyStateBreakdownState(failed = true)
            }
        }
    }

    fun saveActivityType(
        type: ActivityAnnotationPutRequest.ActivityType,
        rememberRule: Boolean,
    ) {
        val current = mutableState.value.value ?: return
        viewModelScope.launch {
            mutableState.value = mutableState.value.copy(saving = true, failed = false)
            runCatching {
                glucoseApi.putActivityAnnotation(
                    ActivityAnnotationPutRequest(
                        activityType = type,
                        startAt = current.startAt,
                        endAt = current.endAt,
                        rememberNoStepsRule = rememberRule,
                    ),
                )
            }.onSuccess { response ->
                mutableState.value = BodyStateBreakdownState(value = response)
            }.onFailure {
                mutableState.value = mutableState.value.copy(saving = false, failed = true)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BodyStateBreakdownSheet(
    bodyState: BodyState,
    onDismiss: () -> Unit,
) {
    val viewModel: BodyStateBreakdownViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    LaunchedEffect(bodyState) { viewModel.load(bodyState) }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = GT.colors.surface,
        contentColor = GT.colors.ink,
    ) {
        when {
            state.loading -> Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(220.dp),
                contentAlignment = Alignment.Center,
            ) {
                CircularProgressIndicator(color = GT.colors.accent)
            }
            state.value != null -> BodyStateBreakdownContent(
                value = requireNotNull(state.value),
                saving = state.saving,
                saveFailed = state.failed,
                onSaveActivityType = viewModel::saveActivityType,
            )
            else -> Column(
                modifier = Modifier.padding(horizontal = 18.dp, vertical = 32.dp),
            ) {
                GTHintBox(text = stringResource(R.string.body_breakdown_unavailable))
            }
        }
    }
}

@Composable
private fun BodyStateBreakdownContent(
    value: BodyStateBreakdownResponse,
    saving: Boolean,
    saveFailed: Boolean,
    onSaveActivityType: (ActivityAnnotationPutRequest.ActivityType, Boolean) -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 18.dp)
            .padding(bottom = 24.dp),
    ) {
        BreakdownHero(value)
        Spacer(Modifier.height(12.dp))
        GTHairlineDivider()
        Spacer(Modifier.height(12.dp))
        if (value.kind == BodyStateBreakdownResponse.Kind.SLEEP) {
            SleepBreakdown(value)
        } else {
            ActivityBreakdown(
                value = value,
                saving = saving,
                saveFailed = saveFailed,
                onSaveActivityType = onSaveActivityType,
            )
        }
        Spacer(Modifier.height(12.dp))
        BreakdownFooter(value)
    }
}

@Composable
private fun BreakdownHero(value: BodyStateBreakdownResponse) {
    val sleep = value.kind == BodyStateBreakdownResponse.Kind.SLEEP
    val markerColor = if (sleep) GT.colors.stateSleep else GT.colors.stateActivity
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier
                .size(6.dp)
                .background(markerColor, CircleShape),
        )
        Spacer(Modifier.width(7.dp))
        Text(
            text = if (sleep) sleepNightKicker(value) else activityKicker(value),
            color = GT.colors.muted,
            style = GT.type.kicker.copy(fontSize = 8.sp, letterSpacing = 1.sp),
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
    Spacer(Modifier.height(4.dp))
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.Bottom,
    ) {
        Text(
            text = heroDuration(value.totalMinutes),
            color = GT.colors.ink,
            style = GT.type.monoNumber.copy(fontSize = 24.sp, lineHeight = 28.sp),
        )
        Text(
            text = "${value.startAt.clockText()}–${value.endAt.clockText()}",
            color = GT.colors.muted,
            style = GT.type.monoLabel,
        )
    }
}

@Composable
private fun SleepBreakdown(value: BodyStateBreakdownResponse) {
    SectionKicker(R.string.body_breakdown_stages)
    val stages = value.sleepStages.orEmpty()
    val detailedStages = stages.any {
        it.stage == SleepStageResponse.Stage.DEEP ||
            it.stage == SleepStageResponse.Stage.REM ||
            it.stage == SleepStageResponse.Stage.AWAKE
    }
    if (stages.isEmpty() || !detailedStages) {
        Text(
            text = stringResource(
                if (stages.isEmpty()) {
                    R.string.body_breakdown_stages_missing
                } else {
                    R.string.body_breakdown_stages_compressed
                },
            ),
            color = GT.colors.muted,
            style = GT.type.sansBody,
        )
    } else {
        SleepStagesChart(
            stages = stages,
            start = value.startAt,
            end = value.endAt,
        )
    }
    Spacer(Modifier.height(12.dp))
    val deepMinutes = stages.filter { it.stage == SleepStageResponse.Stage.DEEP }.sumOf { it.minutes }
    val remMinutes = stages.filter { it.stage == SleepStageResponse.Stage.REM }.sumOf { it.minutes }
    val wakes = stages.count { it.stage == SleepStageResponse.Stage.AWAKE }
    CompactMetricStrip(
        listOf(
            R.string.body_breakdown_deep to if (detailedStages) {
                minutesText(deepMinutes)
            } else {
                stringResource(R.string.body_breakdown_not_available)
            },
            R.string.body_breakdown_stage_rem to if (detailedStages) {
                minutesText(remMinutes)
            } else {
                stringResource(R.string.body_breakdown_not_available)
            },
            R.string.body_breakdown_wakes to if (detailedStages) {
                wakes.toString()
            } else {
                stringResource(R.string.body_breakdown_not_available)
            },
            R.string.body_breakdown_heart_rate to value.meanBpm?.let { bpmText(it.toDouble()) },
        ),
    )
    Spacer(Modifier.height(14.dp))
    SectionHeading(
        labelRes = R.string.body_breakdown_sleep_glucose,
        summary = sleepGlucoseSummary(value),
    )
    CompactLineChart(
        points = value.glucosePoints.orEmpty(),
        start = value.startAt,
        end = value.endAt,
        color = GT.colors.stateSleep,
        baseline = 3.9,
        highlightAt = value.insightAt,
        highlightColor = GT.colors.warn,
        chartKind = ChartKind.Glucose,
        heavySmoothing = true,
    )
    Spacer(Modifier.height(14.dp))
    InsightBlock(value)
}

@Composable
private fun ActivityBreakdown(
    value: BodyStateBreakdownResponse,
    saving: Boolean,
    saveFailed: Boolean,
    onSaveActivityType: (ActivityAnnotationPutRequest.ActivityType, Boolean) -> Unit,
) {
    if (value.activityType == null && value.suggestedActivityType != null) {
        Text(
            text = stringResource(R.string.body_breakdown_activity_guess),
            color = GT.colors.ink2,
            style = GT.type.sansBody,
        )
        Spacer(Modifier.height(8.dp))
    }
    ActivityTypePicker(value, saving, saveFailed, onSaveActivityType)
    Spacer(Modifier.height(12.dp))
    SectionHeading(
        labelRes = R.string.body_breakdown_pulse,
        summary = if (value.stepsAvailable == true) {
            stringResource(R.string.body_breakdown_steps_available, value.steps ?: 0)
        } else {
            stringResource(R.string.body_breakdown_steps_sensor_silent)
        },
    )
    CompactLineChart(
        points = value.heartRatePoints.orEmpty(),
        start = value.startAt,
        end = value.endAt,
        color = GT.colors.stateActivity,
        highlightAt = value.heartRatePoints.orEmpty().maxByOrNull { it.value }?.timestamp,
        highlightColor = GT.colors.warn,
        chartKind = ChartKind.HeartRate,
    )
    Spacer(Modifier.height(10.dp))
    CompactMetricStrip(
        listOf(
            R.string.body_breakdown_mean to value.meanBpm?.let { bpmText(it.toDouble()) },
            R.string.body_breakdown_peak to value.peakBpm?.let { bpmText(it.toDouble()) },
            R.string.body_breakdown_duration_metric to heroDuration(value.totalMinutes),
            R.string.body_breakdown_steady to value.steadyPercent?.let {
                formatPercent(it.toDouble())
            },
        ),
    )
    Spacer(Modifier.height(14.dp))
    SectionHeading(
        labelRes = R.string.body_breakdown_activity_glucose,
        summary = activityGlucoseSummary(value),
    )
    CompactLineChart(
        points = value.glucosePoints.orEmpty(),
        start = value.glucosePoints.orEmpty().minByOrNull { it.timestamp }?.timestamp ?: value.startAt,
        end = value.glucosePoints.orEmpty().maxByOrNull { it.timestamp }?.timestamp ?: value.endAt,
        color = GT.colors.stateActivity,
        baseline = 3.9,
        highlightAt = value.insightAt,
        highlightColor = GT.colors.stateActivity,
        chartKind = ChartKind.Glucose,
    )
    Spacer(Modifier.height(14.dp))
    InsightBlock(value)
}

@Composable
private fun ActivityTypePicker(
    value: BodyStateBreakdownResponse,
    saving: Boolean,
    saveFailed: Boolean,
    onSaveActivityType: (ActivityAnnotationPutRequest.ActivityType, Boolean) -> Unit,
) {
    val suggested = value.suggestedActivityType?.toRequestType()
    var selected by remember(value.activityType, value.suggestedActivityType) {
        mutableStateOf(value.activityType?.toRequestType() ?: suggested)
    }
    var rememberRule by remember(value.rememberNoStepsRule) {
        mutableStateOf(value.rememberNoStepsRule == true)
    }
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        ActivityAnnotationPutRequest.ActivityType.entries.forEach { type ->
            FilterChip(
                label = stringResource(type.labelRes()),
                active = selected == type,
                onClick = {
                    selected = type
                    onSaveActivityType(type, rememberRule)
                },
            )
        }
    }
    if (value.stepsAvailable != true) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = 44.dp)
                .clickable {
                    rememberRule = !rememberRule
                    selected?.let { onSaveActivityType(it, rememberRule) }
                },
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                modifier = Modifier
                    .size(16.dp)
                    .border(1.dp, GT.colors.hairline2, GT.shapes.tag)
                    .background(
                        if (rememberRule) GT.colors.ink else Color.Transparent,
                        GT.shapes.tag,
                ),
                contentAlignment = Alignment.Center,
            ) {
                if (rememberRule) {
                    val checkColor = GT.colors.surface
                    Canvas(Modifier.size(10.dp)) {
                        val check = Path().apply {
                            moveTo(size.width * 0.08f, size.height * 0.52f)
                            lineTo(size.width * 0.38f, size.height * 0.82f)
                            lineTo(size.width * 0.92f, size.height * 0.16f)
                        }
                        drawPath(
                            path = check,
                            color = checkColor,
                            style = Stroke(width = 1.5.dp.toPx(), cap = StrokeCap.Round),
                        )
                    }
                }
            }
            Spacer(Modifier.width(9.dp))
            Text(
                text = stringResource(
                    R.string.body_breakdown_remember_rule,
                    selected?.let { stringResource(it.labelRes()) }.orEmpty(),
                ),
                color = GT.colors.ink2,
                style = GT.type.monoLabel.copy(fontSize = 9.sp),
                maxLines = 2,
            )
        }
    }
    if (saving) {
        Text(
            text = "…",
            color = GT.colors.muted,
            style = GT.type.monoLabel,
        )
    } else if (saveFailed) {
        Text(
            text = stringResource(R.string.body_breakdown_unavailable),
            color = GT.colors.warn,
            style = GT.type.monoLabel,
        )
    }
}

@Composable
private fun SleepStagesChart(
    stages: List<SleepStageResponse>,
    start: Instant,
    end: Instant,
) {
    val lanes = listOf(
        SleepStageResponse.Stage.AWAKE to R.string.body_breakdown_stage_awake,
        SleepStageResponse.Stage.REM to R.string.body_breakdown_stage_rem,
        SleepStageResponse.Stage.LIGHT to R.string.body_breakdown_stage_light,
        SleepStageResponse.Stage.DEEP to R.string.body_breakdown_stage_deep,
    )
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        lanes.forEachIndexed { index, (stage, labelRes) ->
            val laneColor = GT.colors.stateSleep.copy(alpha = 1f - index * 0.16f)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = stringResource(labelRes),
                    modifier = Modifier.width(48.dp),
                    color = GT.colors.muted,
                    style = GT.type.monoLabel.copy(fontSize = 7.sp),
                )
                Canvas(
                    modifier = Modifier
                        .weight(1f)
                        .height(12.dp),
                ) {
                    val total = (end - start).inWholeMilliseconds.coerceAtLeast(1).toFloat()
                    stages.filter { it.stage == stage }.forEach { item ->
                        val left = ((item.startAt - start).inWholeMilliseconds / total)
                            .coerceIn(0f, 1f) * size.width
                        val right = ((item.endAt - start).inWholeMilliseconds / total)
                            .coerceIn(0f, 1f) * size.width
                        drawLine(
                            color = laneColor,
                            start = Offset(left, size.height / 2f),
                            end = Offset(right, size.height / 2f),
                            strokeWidth = size.height * 0.62f,
                            cap = StrokeCap.Square,
                        )
                    }
                }
            }
        }
        ChartTimeAxis(start, end, modifier = Modifier.padding(start = 48.dp))
    }
}

private enum class ChartKind { Glucose, HeartRate }

private data class ChartPoint(val timestamp: Instant, val value: Double)

@Composable
private fun CompactLineChart(
    points: List<BodyStatePointResponse>,
    start: Instant,
    end: Instant,
    color: Color,
    baseline: Double? = null,
    highlightAt: Instant? = null,
    highlightColor: Color,
    chartKind: ChartKind,
    heavySmoothing: Boolean = false,
) {
    if (points.size < 2) {
        GTHintBox(text = stringResource(R.string.body_breakdown_no_glucose))
        return
    }
    val sourcePoints = points.filter { it.timestamp >= start && it.timestamp <= end }
        .ifEmpty { points }
        .sortedBy { it.timestamp }
        .map { ChartPoint(it.timestamp, it.value.toDouble()) }
    val visiblePoints = if (heavySmoothing) heavilySmoothed(sourcePoints) else sourcePoints
    val values = visiblePoints.map { it.value }
    val rawMin = minOf(values.minOrNull() ?: 0.0, baseline ?: Double.MAX_VALUE)
    val rawMax = maxOf(values.maxOrNull() ?: 1.0, baseline ?: -Double.MAX_VALUE)
    val (chartMin, chartMax) = when (chartKind) {
        ChartKind.HeartRate -> {
            val low = floor((rawMin - 5.0) / 10.0) * 10.0
            val high = ceil((rawMax + 5.0) / 10.0) * 10.0
            low to high.coerceAtLeast(low + 20.0)
        }
        ChartKind.Glucose -> {
            val low = floor((rawMin - 0.4) * 2.0) / 2.0
            val high = ceil((rawMax + 0.4) * 2.0) / 2.0
            low to high.coerceAtLeast(low + 2.0)
        }
    }
    val chartBg = GT.colors.bg
    val grid = GT.colors.hairline
    val total = (end - start).inWholeMilliseconds.coerceAtLeast(1).toFloat()
    val spread = (chartMax - chartMin).coerceAtLeast(1.0)
    val highlighted = highlightAt?.let { target ->
        visiblePoints.minByOrNull { point ->
            kotlin.math.abs((point.timestamp - target).inWholeMilliseconds)
        }
    }
    Row(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .width(30.dp)
                .height(78.dp),
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(
                text = chartAxisValue(chartMax, chartKind),
                color = GT.colors.muted,
                style = GT.type.monoLabel.copy(fontSize = 7.sp),
            )
            Text(
                text = chartAxisValue(chartMin, chartKind),
                color = GT.colors.muted,
                style = GT.type.monoLabel.copy(fontSize = 7.sp),
            )
        }
        Column(modifier = Modifier.weight(1f)) {
            Canvas(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(78.dp)
                    .background(chartBg),
            ) {
                repeat(3) { index ->
                    val y = size.height * index / 2f
                    drawLine(grid, Offset(0f, y), Offset(size.width, y), 0.5.dp.toPx())
                }
                baseline?.takeIf { it in chartMin..chartMax }?.let { value ->
                    val y = size.height - (((value - chartMin) / spread).toFloat() * size.height)
                    drawLine(
                        color = grid,
                        start = Offset(0f, y),
                        end = Offset(size.width, y),
                        strokeWidth = 1.dp.toPx(),
                        pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 6f)),
                    )
                }
                val path = Path()
                visiblePoints.forEachIndexed { index, point ->
                    val x = ((point.timestamp - start).inWholeMilliseconds / total)
                        .coerceIn(0f, 1f) * size.width
                    val y = size.height - (((point.value - chartMin) / spread).toFloat() *
                        size.height)
                    if (index == 0) path.moveTo(x, y) else path.lineTo(x, y)
                }
                drawPath(
                    path,
                    color = color,
                    style = Stroke(width = 1.5.dp.toPx(), cap = StrokeCap.Round),
                )
                highlighted?.let { point ->
                    val x = ((point.timestamp - start).inWholeMilliseconds / total)
                        .coerceIn(0f, 1f) * size.width
                    val y = size.height - (((point.value - chartMin) / spread).toFloat() *
                        size.height)
                    drawCircle(chartBg, radius = 4.dp.toPx(), center = Offset(x, y))
                    drawCircle(
                        highlightColor,
                        radius = 4.dp.toPx(),
                        center = Offset(x, y),
                        style = Stroke(1.5.dp.toPx()),
                    )
                }
            }
            ChartTimeAxis(start, end)
        }
    }
}

@Composable
private fun ChartTimeAxis(start: Instant, end: Instant, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(start.clockText(), color = GT.colors.muted, style = GT.type.monoLabel)
        Text(midpoint(start, end).clockText(), color = GT.colors.muted, style = GT.type.monoLabel)
        Text(end.clockText(), color = GT.colors.muted, style = GT.type.monoLabel)
    }
}

@Composable
private fun CompactMetricStrip(values: List<Pair<Int, String?>>) {
    val visible = values.filter { it.second != null }
    Row(modifier = Modifier.fillMaxWidth()) {
        visible.forEach { (label, value) ->
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = stringResource(label),
                    color = GT.colors.muted,
                    style = GT.type.kicker.copy(fontSize = 7.sp, letterSpacing = 0.7.sp),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.height(2.dp))
                Text(
                    text = requireNotNull(value),
                    color = GT.colors.ink,
                    style = GT.type.monoLabel.copy(fontSize = 12.sp, fontWeight = FontWeight.Medium),
                    maxLines = 1,
                )
            }
        }
    }
}

@Composable
private fun InsightBlock(value: BodyStateBreakdownResponse) {
    val insightText = when (value.insightCode) {
        "sleep_low_near_wake" -> stringResource(
            R.string.body_breakdown_sleep_low_wake,
            value.insightAt?.clockText().orEmpty(),
            value.insightValue?.let { formatMmol(it.toDouble()) }.orEmpty(),
        )
        "sleep_low" -> stringResource(
            R.string.body_breakdown_sleep_low,
            value.lowMinutes ?: 0,
            value.insightValue?.let { formatMmol(it.toDouble()) }.orEmpty(),
            value.insightAt?.clockText().orEmpty(),
        )
        "sleep_shorter" -> stringResource(
            R.string.body_breakdown_sleep_shorter,
            kotlin.math.abs(value.insightComparisonMinutes ?: 0),
        )
        "sleep_longer" -> stringResource(
            R.string.body_breakdown_sleep_longer,
            kotlin.math.abs(value.insightComparisonMinutes ?: 0),
        )
        "sleep_summary" -> stringResource(R.string.body_breakdown_sleep_summary)
        "activity_drop_with_iob" -> stringResource(
            R.string.body_breakdown_activity_drop_iob,
            value.insightValue?.let { formatMmol(kotlin.math.abs(it.toDouble())) }.orEmpty(),
            value.iobStartUnits?.let { insulinText(it.toDouble()) }.orEmpty(),
        )
        "activity_drop" -> stringResource(
            R.string.body_breakdown_activity_drop,
            value.insightValue?.let { formatMmol(kotlin.math.abs(it.toDouble())) }.orEmpty(),
        )
        "activity_rise" -> stringResource(
            R.string.body_breakdown_activity_rise,
            value.insightValue?.let { formatMmol(kotlin.math.abs(it.toDouble())) }.orEmpty(),
        )
        "activity_flat" -> stringResource(
            R.string.body_breakdown_activity_flat,
            value.insightValue?.let { formatMmol(it.toDouble()) }.orEmpty(),
        )
        else -> stringResource(R.string.body_breakdown_activity_no_glucose)
    }
    val sleep = value.kind == BodyStateBreakdownResponse.Kind.SLEEP
    val railColor = if (sleep) GT.colors.warn else GT.colors.stateActivity
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(IntrinsicSize.Min)
            .background(GT.colors.bg)
            .padding(vertical = 10.dp),
    ) {
        Box(
            modifier = Modifier
                .fillMaxHeight()
                .width(2.dp)
                .background(railColor),
        )
        Spacer(Modifier.width(12.dp))
        Column(modifier = Modifier.padding(end = 10.dp)) {
            Text(
                text = stringResource(
                    if (sleep) {
                        R.string.body_breakdown_sleep_insight
                    } else {
                        R.string.body_breakdown_insight
                    },
                ),
                color = railColor,
                style = GT.type.kicker,
            )
            Spacer(Modifier.height(5.dp))
            Text(
                text = insightText,
                color = GT.colors.ink2,
                style = GT.type.sansBody,
            )
        }
    }
}

@Composable
private fun BreakdownFooter(value: BodyStateBreakdownResponse) {
    val sleep = value.kind == BodyStateBreakdownResponse.Kind.SLEEP
    val days = value.frequencyDays ?: 30
    val comparison = value.insightComparisonMinutes
    val summary = when {
        sleep && comparison != null && comparison < 0 -> stringResource(
            R.string.body_breakdown_footer_shorter,
            kotlin.math.abs(comparison),
            days,
        )
        sleep && comparison != null && comparison > 0 -> stringResource(
            R.string.body_breakdown_footer_longer,
            comparison,
            days,
        )
        sleep -> stringResource(
            R.string.body_breakdown_footer_sleep_count,
            value.frequencyCount ?: 0,
            days,
        )
        else -> stringResource(
            R.string.body_breakdown_footer_activity_count,
            value.frequencyCount ?: 0,
            days,
        )
    }
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = summary,
            modifier = Modifier.weight(1f),
            color = GT.colors.muted,
            style = GT.type.monoLabel.copy(fontSize = 8.sp),
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        Spacer(Modifier.width(8.dp))
        Text(
            text = stringResource(
                if (sleep) R.string.body_breakdown_all_nights else R.string.body_breakdown_all_activity,
            ),
            color = GT.colors.muted,
            style = GT.type.kicker.copy(fontSize = 8.sp),
            textAlign = TextAlign.End,
        )
    }
}

@Composable
private fun SectionHeading(labelRes: Int, summary: String?) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = stringResource(labelRes),
            color = GT.colors.muted,
            style = GT.type.kicker,
            maxLines = 1,
        )
        summary?.let {
            Text(
                text = it,
                color = GT.colors.muted,
                style = GT.type.monoLabel.copy(fontSize = 8.sp),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
    Spacer(Modifier.height(7.dp))
}

@Composable
private fun SectionKicker(resId: Int) {
    Text(
        text = stringResource(resId),
        color = GT.colors.muted,
        style = GT.type.kicker,
        maxLines = 1,
        overflow = TextOverflow.Ellipsis,
    )
    Spacer(Modifier.height(10.dp))
}

private fun ActivityAnnotationPutRequest.ActivityType.labelRes(): Int = when (this) {
    ActivityAnnotationPutRequest.ActivityType.CYCLING -> R.string.body_breakdown_type_cycling
    ActivityAnnotationPutRequest.ActivityType.GYM -> R.string.body_breakdown_type_gym
    ActivityAnnotationPutRequest.ActivityType.WALKING -> R.string.body_breakdown_type_walking
    ActivityAnnotationPutRequest.ActivityType.OTHER -> R.string.body_breakdown_type_other
}

private fun BodyStateBreakdownResponse.ActivityType.toRequestType() = when (this) {
    BodyStateBreakdownResponse.ActivityType.CYCLING -> ActivityAnnotationPutRequest.ActivityType.CYCLING
    BodyStateBreakdownResponse.ActivityType.GYM -> ActivityAnnotationPutRequest.ActivityType.GYM
    BodyStateBreakdownResponse.ActivityType.WALKING -> ActivityAnnotationPutRequest.ActivityType.WALKING
    BodyStateBreakdownResponse.ActivityType.OTHER -> ActivityAnnotationPutRequest.ActivityType.OTHER
}

private fun BodyStateBreakdownResponse.SuggestedActivityType.toRequestType() = when (this) {
    BodyStateBreakdownResponse.SuggestedActivityType.CYCLING -> {
        ActivityAnnotationPutRequest.ActivityType.CYCLING
    }
    BodyStateBreakdownResponse.SuggestedActivityType.GYM -> ActivityAnnotationPutRequest.ActivityType.GYM
    BodyStateBreakdownResponse.SuggestedActivityType.WALKING -> {
        ActivityAnnotationPutRequest.ActivityType.WALKING
    }
    BodyStateBreakdownResponse.SuggestedActivityType.OTHER -> ActivityAnnotationPutRequest.ActivityType.OTHER
}

@Composable
private fun sleepNightKicker(value: BodyStateBreakdownResponse): String {
    val zone = TimeZone.currentSystemDefault()
    val start = value.startAt.toLocalDateTime(zone).date
    val end = value.endAt.toLocalDateTime(zone).date
    val month = stringArrayResource(R.array.body_breakdown_months_genitive)[end.monthNumber - 1]
    return if (start == end) {
        stringResource(R.string.body_breakdown_sleep_kicker_one_day, end.dayOfMonth, month)
    } else {
        stringResource(
            R.string.body_breakdown_sleep_kicker_two_days,
            start.dayOfMonth,
            end.dayOfMonth,
            month,
        )
    }
}

@Composable
private fun activityKicker(value: BodyStateBreakdownResponse): String {
    val type = value.activityType?.toRequestType()
    return stringResource(
        R.string.body_breakdown_activity_kicker,
        type?.let { stringResource(it.labelRes()) }
            ?: stringResource(R.string.body_breakdown_type_unknown),
    )
}

@Composable
private fun heroDuration(minutes: Int): String = when {
    minutes >= 60 -> stringResource(
        R.string.body_breakdown_duration_hours_minutes,
        minutes / 60,
        minutes % 60,
    )
    else -> stringResource(R.string.body_breakdown_duration_minutes_only, minutes)
}

@Composable
private fun sleepGlucoseSummary(value: BodyStateBreakdownResponse): String? {
    val tir = value.tirPercent
    val low = value.lowMinutes
    return when {
        tir != null && low != null -> stringResource(
            R.string.body_breakdown_sleep_glucose_summary,
            tir,
            low,
        )
        tir != null -> stringResource(R.string.body_breakdown_sleep_tir_summary, tir)
        low != null -> stringResource(R.string.body_breakdown_sleep_low_summary, low)
        else -> null
    }
}

@Composable
private fun activityGlucoseSummary(value: BodyStateBreakdownResponse): String? =
    value.glucoseDeltaTwoHours?.toDouble()?.let { delta ->
        stringResource(R.string.body_breakdown_activity_delta_summary, signedMmol(delta))
    }

private fun signedMmol(value: Double): String {
    val formatted = String.format(Locale.US, "%.1f", kotlin.math.abs(value)).replace('.', ',')
    return when {
        value > 0 -> "+$formatted"
        value < 0 -> "−$formatted"
        else -> formatted
    }
}

private fun chartAxisValue(value: Double, kind: ChartKind): String = when (kind) {
    ChartKind.HeartRate -> value.roundToInt().toString()
    ChartKind.Glucose -> String.format(Locale.US, "%.1f", value).replace('.', ',')
}

/**
 * Sleep-only display smoothing. Clinical summaries still use the unchanged
 * normalized points returned by the backend.
 */
private fun heavilySmoothed(points: List<ChartPoint>): List<ChartPoint> {
    if (points.size < 5) return points
    val medians = points.indices.map { index ->
        val values = points
            .subList((index - 4).coerceAtLeast(0), (index + 5).coerceAtMost(points.size))
            .map { it.value }
            .sorted()
        values[values.size / 2]
    }
    return points.indices.map { index ->
        var weighted = 0.0
        var totalWeight = 0.0
        for (offset in -2..2) {
            val neighbor = (index + offset).coerceIn(medians.indices)
            val weight = (3 - kotlin.math.abs(offset)).toDouble()
            weighted += medians[neighbor] * weight
            totalWeight += weight
        }
        ChartPoint(points[index].timestamp, weighted / totalWeight)
    }
}

private fun midpoint(start: Instant, end: Instant): Instant = start + (end - start) / 2

private fun Instant.clockText(): String {
    val time = toLocalDateTime(TimeZone.currentSystemDefault()).time
    return "%02d:%02d".format(time.hour, time.minute)
}

@Composable
private fun minutesText(minutes: Int): String =
    stringResource(R.string.body_breakdown_minutes, minutes)

@Composable
private fun bpmText(value: Double): String =
    stringResource(R.string.body_breakdown_bpm, value.roundToInt())

private fun insulinText(value: Double): String =
    String.format(Locale.US, "%.1f", value).replace('.', ',')
