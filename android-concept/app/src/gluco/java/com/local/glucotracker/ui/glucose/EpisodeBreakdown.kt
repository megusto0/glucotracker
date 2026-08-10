package com.local.glucotracker.ui.glucose

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.R
import com.local.glucotracker.data.api.GlucoseApi
import com.local.glucotracker.ui.design.GT
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.datetime.DatePeriod
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.atStartOfDayIn
import kotlinx.datetime.plus
import kotlinx.datetime.toLocalDateTime

/**
 * One episode taken apart, as the backend read it.
 *
 * Nothing here is computed on the client. The anchors, the per-gram figure, the
 * crossings and the interpretation all arrive already decided, because they are
 * the same judgements the diary colours rows by — recomputing them here would
 * be a second opinion that could disagree with the row that opened this sheet.
 */
data class EpisodeBreakdownUi(
    val classification: String,
    val title: String,
    val subtitle: String?,
    val startAt: Instant,
    val windowFrom: Instant,
    val windowTo: Instant,
    val lowThreshold: Double,
    val points: List<BreakdownPointUi>,
    val anchors: List<BreakdownAnchorUi>,
    val derived: List<BreakdownDerivedUi>,
    val crossings: List<BreakdownCrossingUi>,
    val causeText: String?,
    val frequencyLabel: String?,
)

data class BreakdownPointUi(val at: Instant, val value: Double, val isLow: Boolean)

data class BreakdownAnchorUi(
    val role: String,
    val label: String,
    val at: Instant,
    val value: Double,
    val caption: String?,
)

data class BreakdownDerivedUi(
    val label: String,
    val value: Double,
    val perValue: Double?,
    val perUnit: String?,
)

data class BreakdownCrossingUi(
    val kind: String,
    val therapyClass: String?,
    val label: String,
    val at: Instant,
    val offsetMinutes: Int,
    val detail: String?,
)

@HiltViewModel
class EpisodeBreakdownViewModel @Inject constructor(
    private val glucoseApi: GlucoseApi,
) : ViewModel() {

    private val _state = MutableStateFlow<EpisodeBreakdownUi?>(null)
    val state: StateFlow<EpisodeBreakdownUi?> = _state.asStateFlow()

    private val _failed = MutableStateFlow(false)
    val failed: StateFlow<Boolean> = _failed.asStateFlow()

    /**
     * Load the episode [key] as listed on [date].
     *
     * The day is sent as the range because the key was produced by grouping
     * exactly that range; asking with any other span can resolve it to a
     * different episode or to nothing at all.
     */
    fun load(key: String, date: LocalDate) {
        val zone = TimeZone.currentSystemDefault()
        viewModelScope.launch {
            _failed.value = false
            runCatching {
                glucoseApi.episodeBreakdown(
                    key = key,
                    from = date.atStartOfDayIn(zone),
                    to = date.plus(DatePeriod(days = 1)).atStartOfDayIn(zone),
                )
            }.onSuccess { response ->
                _state.value = EpisodeBreakdownUi(
                    classification = response.classification.value,
                    title = response.title,
                    subtitle = response.subtitle,
                    startAt = response.startAt,
                    windowFrom = response.windowFrom,
                    windowTo = response.windowTo,
                    lowThreshold = response.lowThreshold.toDouble(),
                    points = response.points.orEmpty().map {
                        BreakdownPointUi(it.timestamp, it.value.toDouble(), it.isLow == true)
                    },
                    anchors = response.anchors.orEmpty().map {
                        BreakdownAnchorUi(
                            role = it.role.value,
                            label = it.label,
                            at = it.at,
                            value = it.value.toDouble(),
                            caption = it.caption,
                        )
                    },
                    derived = response.derived.orEmpty().map {
                        BreakdownDerivedUi(
                            label = it.label,
                            value = it.value.toDouble(),
                            perValue = it.perValue?.toDouble(),
                            perUnit = it.perUnit,
                        )
                    },
                    crossings = response.crossings.orEmpty().map {
                        BreakdownCrossingUi(
                            kind = it.kind.value,
                            therapyClass = it.therapyClass,
                            label = it.label,
                            at = it.at,
                            offsetMinutes = it.offsetMinutes,
                            detail = it.detail,
                        )
                    },
                    causeText = response.cause?.text,
                    frequencyLabel = response.frequency?.label,
                )
            }.onFailure {
                _failed.value = true
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EpisodeBreakdownSheet(
    episodeKey: String,
    date: LocalDate,
    onDismiss: () -> Unit,
) {
    val viewModel: EpisodeBreakdownViewModel = hiltViewModel()
    LaunchedEffect(episodeKey, date) { viewModel.load(episodeKey, date) }
    val breakdown by viewModel.state.collectAsStateWithLifecycle()
    val failed by viewModel.failed.collectAsStateWithLifecycle()

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = GT.colors.surface,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 26.dp),
        ) {
            @Suppress("UNUSED_EXPRESSION")
            when {
                breakdown != null -> EpisodeBreakdownContent(breakdown!!)
                failed -> Text(
                    text = stringResource(R.string.episode_breakdown_unavailable),
                    modifier = Modifier.padding(horizontal = 20.dp, vertical = 24.dp),
                    color = GT.colors.muted,
                    style = GT.type.sansLabel,
                )
                else -> Spacer(Modifier.height(180.dp))
            }
        }
    }
}

/**
 * The sheet without its loading, so a snapshot can render it.
 *
 * Splitting the content off is not decoration: the fake surface the snapshot
 * suite renders returns Unit for every gluco section, so a sheet that only
 * existed inside its own loader would never appear in a golden and could lose a
 * whole block without a test noticing.
 */
@Composable
internal fun EpisodeBreakdownContent(breakdown: EpisodeBreakdownUi) {
    val kindColor = breakdownKindColor(breakdown.classification)
    val zone = TimeZone.currentSystemDefault()

    // Its own column and its own fill: the sheet is a stack of blocks, and a
    // caller that merely hands it a slot must not have to know that. The fill
    // matters more than it looks — without it the text sits on whatever is
    // behind, and ink on an unpainted surface is ink on nothing.
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(GT.colors.surface),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp)
                .padding(top = 4.dp, bottom = 12.dp),
        ) {
            Row(verticalAlignment = Alignment.Bottom) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = breakdownKindLabel(breakdown.classification),
                        color = kindColor,
                        style = GT.type.kicker,
                        maxLines = 1,
                    )
                    Spacer(Modifier.height(3.dp))
                    Text(
                        text = breakdown.title,
                        color = GT.colors.ink,
                        style = GT.type.serifSection,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    breakdown.subtitle?.let { subtitle ->
                        Spacer(Modifier.height(3.dp))
                        Text(
                            text = subtitle,
                            color = GT.colors.muted,
                            style = GT.type.monoLabel,
                            maxLines = 1,
                        )
                    }
                }
                Spacer(Modifier.width(10.dp))
                Text(
                    text = clock(breakdown.startAt, zone),
                    color = GT.colors.muted,
                    style = GT.type.monoLabel,
                    maxLines = 1,
                )
            }
        }

        BreakdownChart(breakdown = breakdown)

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp)
                .padding(top = 4.dp, bottom = 12.dp),
            verticalArrangement = Arrangement.spacedBy(7.dp),
        ) {
            breakdown.anchors.forEachIndexed { index, anchor ->
                AnchorRow(number = index + 1, anchor = anchor, zone = zone)
            }
            breakdown.derived.forEach { derived ->
                DerivedRow(derived = derived, kindColor = kindColor)
            }
        }

        if (breakdown.crossings.isNotEmpty()) {
            Text(
                text = stringResource(R.string.episode_breakdown_crossings),
                modifier = Modifier.padding(horizontal = 20.dp).padding(top = 9.dp, bottom = 4.dp),
                color = GT.colors.muted,
                style = GT.type.kicker,
            )
            val markedCrossings = breakdown.crossings.filter {
                it.kind != "sleep" && it.kind != "insulin"
            }
            breakdown.crossings.forEach { crossing ->
                CrossingRow(
                    crossing = crossing,
                    markerIndex = markedCrossings.indexOf(crossing).takeIf { it >= 0 },
                )
            }
        }

        breakdown.causeText?.let { text ->
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 20.dp)
                    .padding(top = 13.dp)
                    .height(IntrinsicSize.Min),
            ) {
                Box(
                    modifier = Modifier
                        .width(3.dp)
                        .fillMaxHeight()
                        .background(kindColor),
                )
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .background(GT.colors.bg)
                        .padding(horizontal = 13.dp, vertical = 11.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Text(
                        text = episodeInterpretationTitle(breakdown.classification),
                        color = kindColor,
                        style = GT.type.kicker,
                    )
                    Text(text = text, color = GT.colors.ink2, style = GT.type.sansLabel)
                }
            }
        }

        breakdown.frequencyLabel?.let { label ->
            Text(
                text = label,
                modifier = Modifier.padding(horizontal = 20.dp).padding(top = 12.dp),
                color = GT.colors.muted,
                style = GT.type.monoLabel.copy(fontSize = 10.sp),
            )
        }
    }
}

/**
 * Sensor points with gap-aware segments.
 *
 * A faint segment helps the eye follow adjacent reports, but a missing interval
 * remains visibly missing instead of becoming an invented glucose trajectory.
 */
@Composable
private fun BreakdownChart(breakdown: EpisodeBreakdownUi) {
    val points = breakdown.points
    if (points.isEmpty()) return
    val anchors = breakdown.anchors
    val crossings = breakdown.crossings
    val lowThreshold = breakdown.lowThreshold.toFloat()
    val lowColor = GT.colors.kindCarbRescue
    val inkColor = GT.colors.ink2
    val hairline = GT.colors.hairline2
    val band = GT.colors.bg
    val sleepColor = GT.colors.stateSleep
    val surfaceColor = GT.colors.surface

    val crossingColors = crossings.associateWith { crossingColor(it) }
    val anchorRingColors = anchors.associate { it.role to anchorColor(it.role) }

    val from = breakdown.windowFrom.toEpochMilliseconds().toFloat()
    val to = breakdown.windowTo.toEpochMilliseconds().toFloat()
    val values = points.map { it.value.toFloat() }
    val low = minOf(values.min(), lowThreshold) - 0.6f
    val high = maxOf(values.max(), 10f) + 0.6f

    Canvas(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 20.dp)
            .height(132.dp),
    ) {
        fun x(at: Instant): Float =
            ((at.toEpochMilliseconds().toFloat() - from) / (to - from)) * size.width

        fun y(value: Float): Float = ((high - value) / (high - low)) * size.height

        drawRect(
            color = band,
            topLeft = androidx.compose.ui.geometry.Offset(0f, y(10f)),
            size = androidx.compose.ui.geometry.Size(size.width, y(lowThreshold) - y(10f)),
        )
        drawLine(
            color = hairline,
            start = androidx.compose.ui.geometry.Offset(0f, y(lowThreshold)),
            end = androidx.compose.ui.geometry.Offset(size.width, y(lowThreshold)),
            strokeWidth = 1.dp.toPx(),
            pathEffect = PathEffect.dashPathEffect(floatArrayOf(3.dp.toPx(), 3.dp.toPx())),
        )
        crossings.filter { it.kind == "sleep" }.forEach { sleep ->
            drawRect(
                color = sleepColor.copy(alpha = 0.3f),
                topLeft = androidx.compose.ui.geometry.Offset(x(sleep.at).coerceAtLeast(0f), 0f),
                size = androidx.compose.ui.geometry.Size(
                    (size.width - x(sleep.at)).coerceAtLeast(0f),
                    4.dp.toPx(),
                ),
            )
        }
        crossings
            .filter { it.kind != "sleep" && it.kind != "insulin" }
            .forEachIndexed { index, crossing ->
                val rawX = x(crossing.at)
                if (rawX < 0f || rawX > size.width) return@forEachIndexed
                val at = rawX.coerceIn(7.dp.toPx(), size.width - 7.dp.toPx())
                val color = crossingColors[crossing] ?: inkColor
                drawLine(
                    color = color.copy(alpha = 0.6f),
                    start = androidx.compose.ui.geometry.Offset(at, 14.dp.toPx()),
                    end = androidx.compose.ui.geometry.Offset(at, size.height),
                    strokeWidth = 1.dp.toPx(),
                    pathEffect = PathEffect.dashPathEffect(
                        floatArrayOf(2.dp.toPx(), 3.dp.toPx()),
                    ),
                )
                drawNumberedMarker(
                    label = crossingMarker(index),
                    centerX = at,
                    centerY = 7.dp.toPx(),
                    color = color,
                    surfaceColor = surfaceColor,
                    radiusPx = 6.dp.toPx(),
                    textSizePx = 7.sp.toPx(),
                )
            }
        // A faint segment is drawn only between adjacent sensor reports. This
        // makes the shape readable without bridging a real CGM gap — the reason
        // ADR-020 §4 rejected a single uninterrupted path here.
        points.zipWithNext().forEach { (first, second) ->
            val gapMinutes = (
                second.at.toEpochMilliseconds() - first.at.toEpochMilliseconds()
            ) / 60_000
            if (
                gapMinutes in 0..10 &&
                first.at >= breakdown.windowFrom &&
                second.at <= breakdown.windowTo
            ) {
                drawLine(
                    color = inkColor.copy(alpha = 0.18f),
                    start = androidx.compose.ui.geometry.Offset(
                        x(first.at),
                        y(first.value.toFloat()),
                    ),
                    end = androidx.compose.ui.geometry.Offset(
                        x(second.at),
                        y(second.value.toFloat()),
                    ),
                    strokeWidth = 0.7.dp.toPx(),
                )
            }
        }
        points.forEach { point ->
            if (point.at < breakdown.windowFrom || point.at > breakdown.windowTo) {
                return@forEach
            }
            drawCircle(
                color = if (point.isLow) lowColor else inkColor,
                radius = if (point.isLow) 2.4.dp.toPx() else 1.9.dp.toPx(),
                center = androidx.compose.ui.geometry.Offset(
                    x(point.at),
                    y(point.value.toFloat()),
                ),
                alpha = if (point.isLow) 1f else 0.75f,
            )
        }
        anchors.forEachIndexed { index, anchor ->
            drawNumberedMarker(
                label = (index + 1).toString(),
                centerX = x(anchor.at),
                centerY = y(anchor.value.toFloat()),
                color = anchorRingColors[anchor.role] ?: inkColor,
                surfaceColor = surfaceColor,
                radiusPx = 7.dp.toPx(),
                textSizePx = 8.sp.toPx(),
            )
        }
    }
}

@Composable
private fun AnchorRow(number: Int, anchor: BreakdownAnchorUi, zone: TimeZone) {
    val ringColor = anchorColor(anchor.role)
    Row(verticalAlignment = Alignment.CenterVertically) {
        NumberedMarker(
            label = number.toString(),
            color = ringColor,
        )
        Spacer(Modifier.width(8.dp))
        Text(
            text = anchor.label,
            modifier = Modifier.weight(1f),
            color = GT.colors.ink2,
            style = GT.type.sansLabel,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        anchor.caption?.let { caption ->
            Text(
                text = caption,
                color = GT.colors.muted,
                style = GT.type.monoLabel.copy(fontSize = 10.sp),
                maxLines = 1,
            )
            Spacer(Modifier.width(6.dp))
        }
        Text(
            text = formatMmol(anchor.value),
            color = GT.colors.ink,
            style = GT.type.monoLabel,
            maxLines = 1,
        )
        Spacer(Modifier.width(5.dp))
        Text(
            text = clock(anchor.at, zone),
            color = GT.colors.muted,
            style = GT.type.monoLabel.copy(fontSize = 10.sp),
            maxLines = 1,
        )
    }
}

@Composable
private fun DerivedRow(derived: BreakdownDerivedUi, kindColor: Color) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Spacer(Modifier.width(18.dp))
        Text(
            text = derived.label,
            modifier = Modifier.weight(1f),
            color = kindColor,
            style = GT.type.sansLabel,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Text(
            text = signedMmol(derived.value),
            color = kindColor,
            style = GT.type.monoLabel,
            maxLines = 1,
        )
        derived.perValue?.let { per ->
            Spacer(Modifier.width(6.dp))
            Text(
                text = stringResource(
                    R.string.episode_breakdown_per_unit,
                    formatPer(per),
                    derived.perUnit.orEmpty(),
                ),
                color = GT.colors.muted,
                style = GT.type.monoLabel.copy(fontSize = 10.sp),
                maxLines = 1,
            )
        }
    }
}

@Composable
private fun CrossingRow(crossing: BreakdownCrossingUi, markerIndex: Int?) {
    val color = crossingColor(crossing)
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 20.dp, vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (crossing.kind == "sleep") {
            Box(
                modifier = Modifier
                    .width(12.dp)
                    .height(4.dp)
                    .background(color.copy(alpha = 0.35f)),
            )
        } else if (crossing.kind == "insulin") {
            InsulinMarker(color = color)
        } else {
            NumberedMarker(
                label = crossingMarker(markerIndex ?: 0),
                color = color,
            )
        }
        Spacer(Modifier.width(8.dp))
        Text(
            text = crossing.label,
            modifier = Modifier.weight(1f),
            color = GT.colors.ink2,
            style = GT.type.sansLabel,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Text(
            text = crossing.detail ?: offsetLabel(crossing.offsetMinutes),
            color = if (crossing.offsetMinutes < 0) color else GT.colors.muted,
            style = GT.type.monoLabel.copy(fontSize = 10.sp),
            maxLines = 1,
        )
    }
}

@Composable
private fun InsulinMarker(color: Color) {
    Canvas(modifier = Modifier.size(18.dp)) {
        val stroke = 1.4.dp.toPx()
        drawLine(
            color = color,
            start = Offset(5.dp.toPx(), 13.dp.toPx()),
            end = Offset(12.dp.toPx(), 6.dp.toPx()),
            strokeWidth = stroke,
            cap = StrokeCap.Round,
        )
        drawLine(
            color = color,
            start = Offset(4.dp.toPx(), 11.dp.toPx()),
            end = Offset(7.dp.toPx(), 14.dp.toPx()),
            strokeWidth = stroke,
            cap = StrokeCap.Round,
        )
        drawLine(
            color = color,
            start = Offset(10.dp.toPx(), 5.dp.toPx()),
            end = Offset(13.dp.toPx(), 8.dp.toPx()),
            strokeWidth = stroke,
            cap = StrokeCap.Round,
        )
        drawLine(
            color = color,
            start = Offset(12.dp.toPx(), 6.dp.toPx()),
            end = Offset(15.dp.toPx(), 3.dp.toPx()),
            strokeWidth = 1.dp.toPx(),
            cap = StrokeCap.Round,
        )
    }
}

@Composable
private fun NumberedMarker(label: String, color: Color) {
    val surfaceColor = GT.colors.surface
    Canvas(modifier = Modifier.size(18.dp)) {
        drawNumberedMarker(
            label = label,
            centerX = size.width / 2f,
            centerY = size.height / 2f,
            color = color,
            surfaceColor = surfaceColor,
            radiusPx = 8.dp.toPx(),
            textSizePx = 8.sp.toPx(),
        )
    }
}

private fun DrawScope.drawNumberedMarker(
    label: String,
    centerX: Float,
    centerY: Float,
    color: Color,
    surfaceColor: Color,
    radiusPx: Float,
    textSizePx: Float,
) {
    val center = Offset(centerX, centerY)
    drawCircle(color = surfaceColor, radius = radiusPx, center = center)
    drawCircle(
        color = color,
        radius = radiusPx,
        center = center,
        style = Stroke(width = 1.4.dp.toPx()),
    )
    val paint = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
        this.color = color.toArgb()
        textAlign = android.graphics.Paint.Align.CENTER
        textSize = textSizePx
        typeface = android.graphics.Typeface.create(
            android.graphics.Typeface.MONOSPACE,
            android.graphics.Typeface.BOLD,
        )
    }
    val baseline = centerY - (paint.ascent() + paint.descent()) / 2f
    drawContext.canvas.nativeCanvas.drawText(label, centerX, baseline, paint)
}

private fun crossingMarker(index: Int): String =
    if (index in 0..25) ('A'.code + index).toChar().toString() else (index + 1).toString()

@Composable
private fun offsetLabel(minutes: Int): String {
    val total = kotlin.math.abs(minutes)
    return when {
        minutes < 0 && total >= 60 ->
            stringResource(R.string.episode_breakdown_before_hours, total / 60, total % 60)
        minutes < 0 -> stringResource(R.string.episode_breakdown_before, total)
        total >= 60 ->
            stringResource(R.string.episode_breakdown_after_hours, total / 60, total % 60)
        else -> stringResource(R.string.episode_breakdown_after, total)
    }
}

@Composable
private fun breakdownKindLabel(classification: String): String = stringResource(
    when (classification) {
        "carb_correction" -> R.string.history_tone_carb_correction
        "insulin_correction" -> R.string.episode_breakdown_kind_insulin_correction
        "snack" -> R.string.episode_breakdown_kind_snack
        "mixed" -> R.string.episode_breakdown_kind_mixed
        "meal" -> R.string.episode_breakdown_kind_meal
        else -> R.string.episode_breakdown_kind_unresolved
    },
)

@Composable
private fun episodeInterpretationTitle(classification: String): String = stringResource(
    when (classification) {
        "carb_correction" -> R.string.episode_breakdown_cause_hypo
        "insulin_correction" -> R.string.episode_breakdown_result_correction
        "meal", "snack" -> R.string.episode_breakdown_result_meal
        else -> R.string.episode_breakdown_result_mixed
    },
)

@Composable
private fun breakdownKindColor(classification: String): Color = when (classification) {
    "carb_correction" -> GT.colors.kindCarbRescue
    "insulin_correction" -> GT.colors.kindInsulinCorrection
    "snack" -> GT.colors.kindSnack
    else -> GT.colors.kindMeal
}

@Composable
private fun crossingColor(crossing: BreakdownCrossingUi): Color = when {
    crossing.kind == "sleep" -> GT.colors.stateSleep
    crossing.kind == "activity" -> GT.colors.stateActivity
    crossing.kind == "insulin" -> GT.colors.kindInsulinCorrection
    crossing.therapyClass == "carb_correction" -> GT.colors.kindCarbRescue
    crossing.therapyClass == "snack" -> GT.colors.kindSnack
    crossing.therapyClass == "insulin_correction" -> GT.colors.kindInsulinCorrection
    else -> GT.colors.kindMeal
}

/**
 * An anchor's ring carries its role, the same way the diary's bars do.
 *
 * The low it answered, the peak it reached and where it settled are three
 * different facts, and three identical grey rings say they are one.
 */
@Composable
private fun anchorColor(role: String): Color = when (role) {
    "trough" -> GT.colors.kindCarbRescue
    "settle" -> GT.colors.kindSnack
    else -> GT.colors.ink
}

private fun clock(at: Instant, zone: TimeZone): String {
    val time = at.toLocalDateTime(zone).time
    return "%02d:%02d".format(time.hour, time.minute)
}

private fun formatMmol(value: Double): String = "%.1f".format(value).replace('.', ',')

private fun signedMmol(value: Double): String {
    val body = formatMmol(kotlin.math.abs(value))
    return if (value < 0) "−$body" else "+$body"
}

private fun formatPer(value: Double): String = "%.2f".format(value).replace('.', ',')
