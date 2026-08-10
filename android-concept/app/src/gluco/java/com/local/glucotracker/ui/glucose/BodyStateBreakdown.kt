package com.local.glucotracker.ui.glucose

import androidx.compose.foundation.Canvas
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
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.res.stringResource
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
            .padding(horizontal = 20.dp)
            .padding(bottom = 32.dp),
    ) {
        Text(
            text = stringResource(
                if (value.kind == BodyStateBreakdownResponse.Kind.SLEEP) {
                    R.string.body_breakdown_sleep_title
                } else {
                    R.string.body_breakdown_activity_title
                },
            ),
            style = GT.type.serifTitle,
            color = GT.colors.ink,
        )
        Spacer(Modifier.height(5.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(
                text = stringResource(
                    if (value.source == BodyStateBreakdownResponse.Source.RECORDED) {
                        R.string.body_breakdown_recorded
                    } else {
                        R.string.body_breakdown_inferred
                    },
                ),
                color = GT.colors.muted,
                style = GT.type.kicker,
            )
            Text(
                text = stringResource(
                    R.string.body_breakdown_duration,
                    breakdownDuration(value.totalMinutes),
                    value.startAt.clockText(),
                    value.endAt.clockText(),
                ),
                color = GT.colors.muted,
                style = GT.type.monoLabel,
            )
        }
        Spacer(Modifier.height(22.dp))
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
        value.averageDurationMinutes?.let { average ->
            Spacer(Modifier.height(18.dp))
            Text(
                text = stringResource(
                    if (value.kind == BodyStateBreakdownResponse.Kind.SLEEP) {
                        R.string.body_breakdown_frequency_sleep
                    } else {
                        R.string.body_breakdown_frequency_activity
                    },
                    value.frequencyCount ?: 0,
                    value.frequencyDays ?: 30,
                    breakdownDuration(average),
                ),
                color = GT.colors.muted,
                style = GT.type.monoLabel,
            )
        }
    }
}

@Composable
private fun SleepBreakdown(value: BodyStateBreakdownResponse) {
    SectionKicker(R.string.body_breakdown_stages)
    val stages = value.sleepStages.orEmpty()
    if (stages.isEmpty()) {
        Text(
            text = stringResource(R.string.body_breakdown_stages_missing),
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
    Spacer(Modifier.height(18.dp))
    val deepMinutes = stages.filter { it.stage == SleepStageResponse.Stage.DEEP }.sumOf { it.minutes }
    val remMinutes = stages.filter { it.stage == SleepStageResponse.Stage.REM }.sumOf { it.minutes }
    val wakes = stages.count { it.stage == SleepStageResponse.Stage.AWAKE }
    MetricGrid(
        listOf(
            R.string.body_breakdown_deep to minutesText(deepMinutes),
            R.string.body_breakdown_stage_rem to minutesText(remMinutes),
            R.string.body_breakdown_wakes to wakes.toString(),
            R.string.body_breakdown_heart_rate to value.meanBpm?.let { bpmText(it.toDouble()) },
        ),
    )
    Spacer(Modifier.height(22.dp))
    SectionKicker(R.string.body_breakdown_sleep_glucose)
    PointChart(
        points = value.glucosePoints.orEmpty(),
        start = value.startAt,
        end = value.endAt,
        color = GT.colors.stateSleep,
    )
    Spacer(Modifier.height(12.dp))
    MetricGrid(
        listOf(
            R.string.body_breakdown_tir to value.tirPercent?.let { formatPercent(it.toDouble()) },
            R.string.body_breakdown_low to value.lowMinutes?.let { minutesText(it) },
        ),
    )
    Spacer(Modifier.height(22.dp))
    InsightBlock(value)
}

@Composable
private fun ActivityBreakdown(
    value: BodyStateBreakdownResponse,
    saving: Boolean,
    saveFailed: Boolean,
    onSaveActivityType: (ActivityAnnotationPutRequest.ActivityType, Boolean) -> Unit,
) {
    ActivityTypePicker(value, saving, saveFailed, onSaveActivityType)
    Spacer(Modifier.height(22.dp))
    SectionKicker(R.string.body_breakdown_hr_steps)
    PointChart(
        points = value.heartRatePoints.orEmpty(),
        start = value.startAt,
        end = value.endAt,
        color = GT.colors.stateActivity,
    )
    if (value.stepsAvailable != true) {
        Spacer(Modifier.height(8.dp))
        Text(
            text = stringResource(R.string.body_breakdown_steps_missing),
            color = GT.colors.muted,
            style = GT.type.sansBody,
        )
        Text(
            text = stringResource(R.string.body_breakdown_training_missing),
            color = GT.colors.muted,
            style = GT.type.monoLabel.copy(fontSize = 10.sp),
        )
    }
    Spacer(Modifier.height(12.dp))
    MetricGrid(
        listOf(
            R.string.body_breakdown_mean to value.meanBpm?.let { bpmText(it.toDouble()) },
            R.string.body_breakdown_peak to value.peakBpm?.let { bpmText(it.toDouble()) },
            if (value.stepsAvailable == true) {
                R.string.body_breakdown_steps to value.steps?.toString()
            } else {
                R.string.body_breakdown_steady to value.steadyPercent?.let {
                    formatPercent(it.toDouble())
                }
            },
        ),
    )
    Spacer(Modifier.height(22.dp))
    SectionKicker(R.string.body_breakdown_activity_glucose)
    PointChart(
        points = value.glucosePoints.orEmpty(),
        start = value.startAt,
        end = value.endAt,
        color = GT.colors.stateActivity,
    )
    Spacer(Modifier.height(12.dp))
    MetricRows(
        listOf(
            R.string.body_breakdown_before_activity to value.glucoseStart?.let {
                formatMmol(it.toDouble())
            },
            R.string.body_breakdown_after_activity to value.glucoseAfter?.let {
                formatMmol(it.toDouble())
            },
            R.string.body_breakdown_two_hours to value.glucoseTwoHourMinimum?.let {
                formatMmol(it.toDouble())
            },
            R.string.body_breakdown_iob_start to value.iobStartUnits?.let {
                stringResource(R.string.body_breakdown_units, insulinText(it.toDouble()))
            },
        ),
    )
    Spacer(Modifier.height(22.dp))
    InsightBlock(value)
}

@Composable
private fun ActivityTypePicker(
    value: BodyStateBreakdownResponse,
    saving: Boolean,
    saveFailed: Boolean,
    onSaveActivityType: (ActivityAnnotationPutRequest.ActivityType, Boolean) -> Unit,
) {
    var selected by remember(value.activityType) {
        mutableStateOf(value.activityType?.toRequestType())
    }
    var rememberRule by remember(value.rememberNoStepsRule) {
        mutableStateOf(value.rememberNoStepsRule == true)
    }
    val suggested = value.suggestedActivityType?.toRequestType()
    if (selected == null && suggested != null) {
        Text(
            text = stringResource(R.string.body_breakdown_activity_guess),
            color = GT.colors.ink2,
            style = GT.type.sansBody,
        )
        Spacer(Modifier.height(10.dp))
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
                    .size(18.dp)
                    .border(1.dp, GT.colors.hairline2, GT.shapes.tag)
                    .background(
                        if (rememberRule) GT.colors.ink else Color.Transparent,
                        GT.shapes.tag,
                    ),
                contentAlignment = Alignment.Center,
            ) {
                if (rememberRule) Text("✓", color = GT.colors.surface, fontSize = 12.sp)
            }
            Spacer(Modifier.width(9.dp))
            Text(
                text = stringResource(
                    R.string.body_breakdown_remember_rule,
                    selected?.let { stringResource(it.labelRes()) }.orEmpty(),
                ),
                color = GT.colors.ink2,
                style = GT.type.sansBody,
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
    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
        lanes.forEachIndexed { index, (stage, labelRes) ->
            val laneColor = GT.colors.stateSleep.copy(alpha = 1f - index * 0.16f)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = stringResource(labelRes),
                    modifier = Modifier.width(72.dp),
                    color = GT.colors.muted,
                    style = GT.type.monoLabel.copy(fontSize = 9.sp),
                )
                Canvas(
                    modifier = Modifier
                        .weight(1f)
                        .height(14.dp),
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
                            strokeWidth = size.height,
                            cap = StrokeCap.Round,
                        )
                    }
                }
            }
        }
        ChartTimeAxis(start, end, modifier = Modifier.padding(start = 72.dp))
    }
}

@Composable
private fun PointChart(
    points: List<BodyStatePointResponse>,
    start: Instant,
    end: Instant,
    color: Color,
) {
    if (points.size < 2) {
        GTHintBox(text = stringResource(R.string.body_breakdown_no_glucose))
        return
    }
    val values = points.map { it.value.toDouble() }
    val minValue = values.minOrNull() ?: 0.0
    val maxValue = values.maxOrNull() ?: 1.0
    Canvas(
        modifier = Modifier
            .fillMaxWidth()
            .height(118.dp)
            .background(GT.colors.bg),
    ) {
        val total = (end - start).inWholeMilliseconds.coerceAtLeast(1).toFloat()
        val spread = (maxValue - minValue).coerceAtLeast(1.0)
        val path = Path()
        points.sortedBy { it.timestamp }.forEachIndexed { index, point ->
            val x = ((point.timestamp - start).inWholeMilliseconds / total)
                .coerceIn(0f, 1f) * size.width
            val y = size.height - (((point.value.toDouble() - minValue) / spread).toFloat() *
                size.height * 0.72f + size.height * 0.14f)
            if (index == 0) path.moveTo(x, y) else path.lineTo(x, y)
        }
        drawPath(path, color = color, style = Stroke(width = 2.dp.toPx()))
        points.forEach { point ->
            val x = ((point.timestamp - start).inWholeMilliseconds / total)
                .coerceIn(0f, 1f) * size.width
            val y = size.height - (((point.value.toDouble() - minValue) / spread).toFloat() *
                size.height * 0.72f + size.height * 0.14f)
            drawCircle(color = color, radius = 2.4.dp.toPx(), center = Offset(x, y))
        }
    }
    ChartTimeAxis(start, end)
}

@Composable
private fun ChartTimeAxis(start: Instant, end: Instant, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(start.clockText(), color = GT.colors.muted, style = GT.type.monoLabel)
        Text(end.clockText(), color = GT.colors.muted, style = GT.type.monoLabel)
    }
}

@Composable
private fun MetricGrid(values: List<Pair<Int, String?>>) {
    val visible = values.filter { it.second != null }
    visible.chunked(2).forEach { row ->
        Row(modifier = Modifier.fillMaxWidth()) {
            row.forEach { (label, value) ->
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .padding(vertical = 5.dp),
                ) {
                    Text(
                        text = stringResource(label),
                        color = GT.colors.muted,
                        style = GT.type.kicker,
                    )
                    Text(
                        text = requireNotNull(value),
                        color = GT.colors.ink,
                        style = GT.type.monoNumber,
                        maxLines = 1,
                    )
                }
            }
            if (row.size == 1) Spacer(Modifier.weight(1f))
        }
    }
}

@Composable
private fun MetricRows(values: List<Pair<Int, String?>>) {
    values.filter { it.second != null }.forEachIndexed { index, (label, value) ->
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 7.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(stringResource(label), color = GT.colors.ink2, style = GT.type.sansBody)
            Text(requireNotNull(value), color = GT.colors.ink, style = GT.type.monoLabel)
        }
        if (index < values.lastIndex) GTHairlineDivider()
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
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(GT.colors.bg)
            .border(GT.space.hairline, GT.colors.hairline)
            .padding(14.dp),
    ) {
        Text(
            text = stringResource(R.string.body_breakdown_insight),
            color = GT.colors.muted,
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

private fun Instant.clockText(): String {
    val time = toLocalDateTime(TimeZone.currentSystemDefault()).time
    return "%02d:%02d".format(time.hour, time.minute)
}

private fun breakdownDuration(minutes: Int): String =
    "%d:%02d".format(minutes / 60, minutes % 60)

@Composable
private fun minutesText(minutes: Int): String =
    stringResource(R.string.body_breakdown_minutes, minutes)

@Composable
private fun bpmText(value: Double): String =
    stringResource(R.string.body_breakdown_bpm, value.roundToInt())

private fun insulinText(value: Double): String =
    String.format(Locale.US, "%.1f", value).replace('.', ',')
