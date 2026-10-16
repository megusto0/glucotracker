package com.local.glucotracker.ui.feature.glucose

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextMeasurer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.BodySpan
import com.local.glucotracker.domain.model.GlucoseReading
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.format.formatClockDuration
import com.local.glucotracker.ui.format.formatGrams
import com.local.glucotracker.ui.format.formatInsulinUnits
import com.local.glucotracker.ui.format.formatMmol
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlinx.datetime.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

private const val LowMmol = 3.9
private const val HighMmol = 10.0

/** An event is pinned to the curve only if a reading is this close in time. */
private const val AnchorSnapMillis = 15L * 60L * 1_000L

/** A tap on the focus chart snaps to a reading within this distance. */
private const val ScrubSnapMillis = 10L * 60L * 1_000L

/**
 * Nightscout's main chart for a phone: hollow CGM rings against the 3.9–10
 * band, insulin as an «И» ring above the curve with its dose, carbs as a
 * filled «У» disc below it with grams, each tied to the curve by a short
 * leader. Sleep and effort run as slim capsules along the bottom.
 * Display only — every value drawn is the server's or the cache's.
 */
@Composable
fun GlucoseFocusChart(
    state: GlucoseScreenState,
    modifier: Modifier = Modifier,
) {
    val colors = GT.colors
    val measurer = rememberTextMeasurer()
    val axisStyle = GT.type.monoLabel.copy(color = colors.muted)
    val labelStyle = GT.type.monoLabel.copy(fontSize = 11.sp, fontWeight = FontWeight.Medium)
    val letterStyle = GT.type.sansLabel.copy(fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
    val spanStyle = GT.type.monoLabel.copy(fontSize = 9.sp, color = colors.ink2)
    val insulinLetter = stringResource(R.string.glucose_marker_insulin)
    val carbsLetter = stringResource(R.string.glucose_marker_carbs)
    val unitsSuffix = stringResource(R.string.glucose_unit_insulin_suffix)
    val gramsSuffix = stringResource(R.string.glucose_unit_grams_suffix)
    val sleepName = stringResource(R.string.body_state_sleep)
    val activityName = stringResource(R.string.body_state_activity)
    val description = focusDescription(state)
    var scrubX by remember(state.focusWindow, state.focusEnd) { mutableStateOf<Float?>(null) }

    val from = state.focusFrom
    val to = state.focusEnd
    val readings = remember(state.readings, from, to) { state.readings.filter { it.readingAt >= from && it.readingAt <= to } }
    // One carbs and one insulin mark per sitting, with the server's totals.
    val meals = state.carbMarks.filter { it.at >= from && it.at <= to }
    val insulin = state.insulinMarks.filter { it.at >= from && it.at <= to }
    val spans = state.bodySpans.filter { it.endAt > from && it.startAt < to }

    Canvas(
        modifier = modifier
            .background(colors.surface, GT.shapes.card)
            .border(GT.space.hairline, colors.hairline, GT.shapes.card)
            .semantics { contentDescription = description }
            .pointerInput(state.focusWindow, state.focusEnd) {
                detectTapGestures { offset -> scrubX = if (scrubX == null) offset.x else null }
            }
            .pointerInput(state.focusWindow, state.focusEnd) {
                detectHorizontalDragGestures(onDragStart = { scrubX = it.x }) { change, _ -> scrubX = change.position.x }
            },
    ) {
        // Equal side margins: the band edges are named inside the plot.
        val pad = 12.dp.toPx()
        val left = pad
        val right = size.width - pad
        val axisHeight = 18.dp.toPx()
        val spanRow = if (spans.isEmpty()) 0f else 16.dp.toPx()
        val plotTop = pad
        val plotBottom = size.height - axisHeight - spanRow - pad / 2f
        val fromMs = from.toEpochMilliseconds()
        val spanMs = (to.toEpochMilliseconds() - fromMs).coerceAtLeast(1L).toFloat()
        fun x(at: Instant): Float = left + (at.toEpochMilliseconds() - fromMs) / spanMs * (right - left)

        // Headroom so a marker above the highest or below the lowest reading still fits.
        val values = readings.map { it.displayValueMmolL }
        val lo = min(2.2, (values.minOrNull() ?: LowMmol) - 1.2)
        val hi = max(13.0, (values.maxOrNull() ?: HighMmol) + 2.0)
        fun y(mmol: Double): Float = plotBottom - ((mmol - lo) / (hi - lo)).toFloat() * (plotBottom - plotTop)

        // Target band and its edges.
        val bandTop = y(HighMmol)
        val bandBottom = y(LowMmol)
        drawRect(colors.good.copy(alpha = 0.09f), Offset(left, bandTop), Size(right - left, bandBottom - bandTop))
        val dots = PathEffect.dashPathEffect(floatArrayOf(2.dp.toPx(), 4.dp.toPx()))
        listOf(bandTop to HighMmol, bandBottom to LowMmol).forEach { (ly, value) ->
            drawLine(colors.good.copy(alpha = 0.6f), Offset(left, ly), Offset(right, ly), strokeWidth = 1.dp.toPx(), pathEffect = dots)
            val text = measurer.measure(formatMmol(value), axisStyle.copy(color = colors.good))
            val ty = if (value == HighMmol) ly - text.size.height - 2.dp.toPx() else ly + 2.dp.toPx()
            drawText(text, topLeft = Offset(right - text.size.width - 2.dp.toPx(), ty))
        }

        // Hour labels.
        hourTicks(from, to, stepHours = 1).forEach { (at, hour) ->
            val tx = x(at)
            drawLine(colors.hairline, Offset(tx, plotTop), Offset(tx, plotBottom), strokeWidth = 0.5.dp.toPx())
            val text = measurer.measure("%02d:00".format(hour), axisStyle)
            drawText(text, topLeft = Offset((tx - text.size.width / 2f).coerceIn(left, right - text.size.width), size.height - axisHeight - pad / 4f))
        }

        // Sleep and effort as slim named capsules above the time axis.
        val capsuleY = plotBottom + 4.dp.toPx()
        spans.forEach { span ->
            val x0 = x(span.startAt).coerceIn(left, right)
            val x1 = x(span.endAt).coerceIn(left, right)
            if (x1 - x0 < 2f) return@forEach
            val tint = if (span.kind == BodySpan.Kind.Sleep) colors.stateSleep else colors.stateActivity
            drawRoundRect(tint.copy(alpha = 0.28f), Offset(x0, capsuleY), Size(x1 - x0, 11.dp.toPx()), CornerRadius(5.5.dp.toPx()))
            val name = if (span.kind == BodySpan.Kind.Sleep) sleepName else span.label ?: activityName
            drawEllipsized(measurer, "$name ${formatClockDuration(span.totalMinutes)}", spanStyle, Offset(x0 + 5.dp.toPx(), capsuleY), x1 - x0 - 8.dp.toPx())
        }

        // CGM readings as hollow rings, coloured by range (position says the same).
        val ring = Stroke(width = 1.5.dp.toPx())
        val ringRadius = if (state.focusWindow == FocusWindow.ThreeHours) 3.4.dp.toPx() else 2.8.dp.toPx()
        readings.forEach { reading ->
            drawCircle(reading.rangeColor(colors.bad, colors.warn, colors.ink2), ringRadius, Offset(x(reading.readingAt), y(reading.displayValueMmolL)), style = ring)
        }
        state.latest?.takeIf { it.readingAt >= from && it.readingAt <= to }?.let { latest ->
            drawCircle(colors.ink, ringRadius + 1.5.dp.toPx(), Offset(x(latest.readingAt), y(latest.displayValueMmolL)))
        }

        // Event markers pinned to the curve.
        val markerRadius = 10.dp.toPx()
        val leader = 30.dp.toPx()
        val labelGap = 3.dp.toPx()
        fun curveY(atMs: Long): Float {
            val nearest = readings.minByOrNull { abs(it.readingAt.toEpochMilliseconds() - atMs) }
            return if (nearest != null && abs(nearest.readingAt.toEpochMilliseconds() - atMs) <= AnchorSnapMillis) {
                y(nearest.displayValueMmolL)
            } else {
                y((LowMmol + HighMmol) / 2)
            }
        }

        val placedLabels = mutableListOf<androidx.compose.ui.geometry.Rect>()
        fun placeLabel(width: Float, height: Float, centerX: Float, startY: Float, awayUp: Boolean): Offset {
            val lx = (centerX - width / 2f).coerceIn(left, size.width - pad - width)
            var ly = startY
            var rect = androidx.compose.ui.geometry.Rect(lx, ly, lx + width, ly + height)
            while (placedLabels.any { it.overlaps(rect) }) {
                ly += if (awayUp) -(height + 1.dp.toPx()) else height + 1.dp.toPx()
                rect = androidx.compose.ui.geometry.Rect(lx, ly, lx + width, ly + height)
            }
            placedLabels += rect
            return Offset(lx, ly)
        }

        // Place every marker first, then let labels steer around markers and each other.
        val insulinXs = spreadMarkers(insulin.map { x(it.at) }, markerRadius * 2.2f, left, right)
        val insulinPlaces = insulin.mapIndexed { index, event ->
            val anchorY = curveY(event.at.toEpochMilliseconds())
            val above = anchorY - leader - markerRadius * 2 - 14.dp.toPx() > plotTop
            Triple(insulinXs[index], if (above) anchorY - leader else anchorY + leader, above)
        }
        val mealXs = spreadMarkers(meals.map { x(it.at) }, markerRadius * 2.2f, left, right)
        val mealPlaces = meals.mapIndexed { index, meal ->
            val anchorY = curveY(meal.at.toEpochMilliseconds())
            val below = anchorY + leader + markerRadius * 2 + 14.dp.toPx() < plotBottom
            Triple(mealXs[index], if (below) anchorY + leader else anchorY - leader, below)
        }
        (insulinPlaces + mealPlaces).forEach { (mx, my, _) ->
            placedLabels += androidx.compose.ui.geometry.Rect(mx - markerRadius, my - markerRadius, mx + markerRadius, my + markerRadius)
        }

        insulin.forEachIndexed { index, event ->
            val anchorX = x(event.at)
            val anchorY = curveY(event.at.toEpochMilliseconds())
            val (mx, my, above) = insulinPlaces[index]
            val tint = when (event.tint) {
                InsulinTint.Correction -> colors.kindInsulinCorrection
                InsulinTint.Basal -> colors.muted
                InsulinTint.Food -> colors.ink
            }
            drawLine(tint.copy(alpha = 0.55f), Offset(anchorX, anchorY), Offset(mx, my), strokeWidth = 1.dp.toPx())
            drawCircle(colors.surface, markerRadius, Offset(mx, my))
            drawCircle(tint, markerRadius, Offset(mx, my), style = Stroke(width = if (event.pending) 1.dp.toPx() else 1.8.dp.toPx(), pathEffect = if (event.pending) dots else null))
            drawCentered(measurer, insulinLetter, letterStyle.copy(color = tint), Offset(mx, my))
            val label = measurer.measure(formatInsulinUnits(event.units) + unitsSuffix, labelStyle.copy(color = tint))
            val ly = if (above) my - markerRadius - labelGap - label.size.height else my + markerRadius + labelGap
            drawText(label, topLeft = placeLabel(label.size.width.toFloat(), label.size.height.toFloat(), mx, ly, awayUp = above))
        }

        meals.forEachIndexed { index, meal ->
            val anchorX = x(meal.at)
            val anchorY = curveY(meal.at.toEpochMilliseconds())
            val (mx, my, below) = mealPlaces[index]
            drawLine(colors.kindMeal.copy(alpha = 0.55f), Offset(anchorX, anchorY), Offset(mx, my), strokeWidth = 1.dp.toPx())
            drawCircle(colors.kindMeal, markerRadius, Offset(mx, my))
            drawCentered(measurer, carbsLetter, letterStyle.copy(color = colors.surface2), Offset(mx, my))
            val label = measurer.measure(formatGrams(meal.grams) + gramsSuffix, labelStyle.copy(color = colors.ink2))
            val ly = if (below) my + markerRadius + labelGap else my - markerRadius - labelGap - label.size.height
            drawText(label, topLeft = placeLabel(label.size.width.toFloat(), label.size.height.toFloat(), mx, ly, awayUp = !below))
        }

        // Scrubber: time and value under the finger.
        scrubX?.let { sx ->
            val cx = sx.coerceIn(left, right)
            val atMs = fromMs + ((cx - left) / (right - left) * spanMs).toLong()
            val nearest = readings.minByOrNull { abs(it.readingAt.toEpochMilliseconds() - atMs) }
                ?.takeIf { abs(it.readingAt.toEpochMilliseconds() - atMs) <= ScrubSnapMillis }
            val lineX = nearest?.let { x(it.readingAt) } ?: cx
            drawLine(colors.ink.copy(alpha = 0.4f), Offset(lineX, plotTop), Offset(lineX, plotBottom), strokeWidth = 1.dp.toPx())
            val text = buildString {
                append(Instant.fromEpochMilliseconds(nearest?.readingAt?.toEpochMilliseconds() ?: atMs).hourMinute())
                if (nearest != null) append(" · ").append(formatMmol(nearest.displayValueMmolL))
            }
            val measured = measurer.measure(text, labelStyle.copy(color = colors.ink))
            val boxPad = 6.dp.toPx()
            val boxW = measured.size.width + boxPad * 2
            val boxH = measured.size.height + boxPad * 2
            val boxX = (lineX - boxW / 2f).coerceIn(left, size.width - pad - boxW)
            drawRoundRect(colors.surface2, Offset(boxX, plotTop), Size(boxW, boxH), CornerRadius(6.dp.toPx()))
            drawRoundRect(colors.hairline2, Offset(boxX, plotTop), Size(boxW, boxH), CornerRadius(6.dp.toPx()), style = Stroke(width = 0.5.dp.toPx()))
            drawText(measured, topLeft = Offset(boxX + boxPad, plotTop + boxPad))
        }
    }
}

/**
 * The day as Nightscout's lower context chart: a thin line, small event
 * ticks, sleep and effort shading, and a frame over the focus window. Tap or
 * drag to move the focus window through the day.
 */
@Composable
fun GlucoseOverviewChart(
    state: GlucoseScreenState,
    onMoveFocus: (Instant) -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = GT.colors
    val measurer = rememberTextMeasurer()
    val axisStyle = GT.type.monoLabel.copy(color = colors.muted)
    val description = stringResource(
        R.string.glucose_overview_description,
        state.focusFrom.hourMinute(),
        state.focusEnd.hourMinute(),
    )
    val latestState by rememberUpdatedState(state)
    val move by rememberUpdatedState(onMoveFocus)

    fun endForX(xPx: Float, width: Float, pad: Float): Instant {
        val s = latestState
        val fromMs = s.dayFrom.toEpochMilliseconds()
        val spanMs = s.now.toEpochMilliseconds() - fromMs
        val center = fromMs + ((xPx - pad) / (width - pad * 2)).coerceIn(0f, 1f) * spanMs
        return Instant.fromEpochMilliseconds(center.toLong() + s.focusWindow.hours * 30L * 60L * 1_000L)
    }

    Canvas(
        modifier = modifier
            .background(colors.surface, GT.shapes.card)
            .border(GT.space.hairline, colors.hairline, GT.shapes.card)
            .semantics { contentDescription = description }
            .pointerInput(Unit) {
                val pad = 10.dp.toPx()
                detectTapGestures { offset -> move(endForX(offset.x, size.width.toFloat(), pad)) }
            }
            .pointerInput(Unit) {
                val pad = 10.dp.toPx()
                detectHorizontalDragGestures { change, _ -> move(endForX(change.position.x, size.width.toFloat(), pad)) }
            },
    ) {
        val pad = 10.dp.toPx()
        val left = pad
        val right = size.width - pad
        val axisHeight = 14.dp.toPx()
        val top = 8.dp.toPx()
        val bottom = size.height - axisHeight
        val fromMs = state.dayFrom.toEpochMilliseconds()
        val spanMs = (state.now.toEpochMilliseconds() - fromMs).coerceAtLeast(1L).toFloat()
        fun x(at: Instant): Float = left + (at.toEpochMilliseconds() - fromMs) / spanMs * (right - left)
        val lo = 2.2
        val hi = max(14.0, (state.readings.maxOfOrNull { it.displayValueMmolL } ?: 0.0) + 1.0)
        fun y(mmol: Double): Float = bottom - ((mmol - lo) / (hi - lo)).toFloat() * (bottom - top)

        state.bodySpans.forEach { span ->
            val x0 = x(span.startAt).coerceIn(left, right)
            val x1 = x(span.endAt).coerceIn(left, right)
            val tint = if (span.kind == BodySpan.Kind.Sleep) colors.stateSleep else colors.stateActivity
            drawRect(tint.copy(alpha = 0.13f), Offset(x0, top), Size(x1 - x0, bottom - top))
        }
        drawRect(colors.good.copy(alpha = 0.08f), Offset(left, y(HighMmol)), Size(right - left, y(LowMmol) - y(HighMmol)))

        val path = Path()
        var previousMs: Long? = null
        state.readings.forEach { reading ->
            val ms = reading.readingAt.toEpochMilliseconds()
            val px = x(reading.readingAt)
            val py = y(reading.displayValueMmolL)
            if (previousMs == null || ms - previousMs!! > 20L * 60L * 1_000L) path.moveTo(px, py) else path.lineTo(px, py)
            previousMs = ms
        }
        drawPath(path, colors.ink2, style = Stroke(width = 1.2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))

        state.carbMarks.forEach { drawCircle(colors.kindMeal, 2.6.dp.toPx(), Offset(x(it.at), top + 2.dp.toPx())) }
        state.insulinMarks.forEach { event ->
            val ix = x(event.at)
            val h = 3.dp.toPx()
            val tri = Path().apply {
                moveTo(ix - h, bottom - h * 2)
                lineTo(ix + h, bottom - h * 2)
                lineTo(ix, bottom)
                close()
            }
            val correction = event.tint == InsulinTint.Correction
            drawPath(tri, if (correction) colors.kindInsulinCorrection else colors.ink)
        }

        // Dim everything outside the focus window; frame the window itself.
        val fx0 = x(state.focusFrom).coerceIn(left, right)
        val fx1 = x(state.focusEnd).coerceIn(left, right)
        val frameTop = top - 4.dp.toPx()
        val frameHeight = bottom - frameTop
        drawRect(colors.bg.copy(alpha = 0.6f), Offset(left, frameTop), Size(fx0 - left, frameHeight))
        drawRect(colors.bg.copy(alpha = 0.6f), Offset(fx1, frameTop), Size(right - fx1, frameHeight))
        drawRoundRect(colors.ink, Offset(fx0, frameTop), Size(fx1 - fx0, frameHeight), CornerRadius(4.dp.toPx()), style = Stroke(width = 1.5.dp.toPx()))

        hourTicks(state.dayFrom, state.now, stepHours = 6).forEach { (at, hour) ->
            val text = measurer.measure("%02d".format(hour), axisStyle)
            drawText(text, topLeft = Offset((x(at) - text.size.width / 2f).coerceIn(left, right - text.size.width), bottom + 1.dp.toPx()))
        }
    }
}

/**
 * Pushes marker centres apart so neighbours never overlap: left to right at
 * least [minGap] apart, then pulled back if the last one ran past [right].
 */
internal fun spreadMarkers(xs: List<Float>, minGap: Float, left: Float, right: Float): List<Float> {
    if (xs.isEmpty()) return emptyList()
    val order = xs.indices.sortedBy { xs[it] }
    val placed = FloatArray(xs.size)
    var previous = Float.NEGATIVE_INFINITY
    order.forEach { index ->
        val wanted = max(xs[index], left + minGap / 2f)
        val placedX = max(wanted, previous + minGap)
        placed[index] = placedX
        previous = placedX
    }
    var limit = right - minGap / 2f
    order.reversed().forEach { index ->
        if (placed[index] > limit) placed[index] = limit
        limit = placed[index] - minGap
    }
    return placed.toList()
}

private fun GlucoseReading.rangeColor(low: Color, high: Color, inRange: Color): Color = when {
    displayValueMmolL < LowMmol -> low
    displayValueMmolL > HighMmol -> high
    else -> inRange
}

private fun DrawScope.drawCentered(measurer: TextMeasurer, text: String, style: TextStyle, center: Offset) {
    val measured = measurer.measure(text, style)
    drawText(measured, topLeft = Offset(center.x - measured.size.width / 2f, center.y - measured.size.height / 2f))
}

private fun DrawScope.drawEllipsized(measurer: TextMeasurer, text: String, style: TextStyle, topLeft: Offset, maxWidth: Float) {
    if (maxWidth < 14.dp.toPx()) return
    val measured = measurer.measure(
        text = text,
        style = style,
        overflow = TextOverflow.Ellipsis,
        maxLines = 1,
        constraints = Constraints(maxWidth = maxWidth.toInt()),
    )
    drawText(measured, topLeft = topLeft)
}

/** Whole local hours inside the range, every [stepHours]. */
internal fun hourTicks(from: Instant, to: Instant, stepHours: Int): List<Pair<Instant, Int>> {
    val zone = TimeZone.currentSystemDefault()
    val hourMs = 60L * 60L * 1_000L
    var t = (from.toEpochMilliseconds() / hourMs + 1) * hourMs
    val ticks = mutableListOf<Pair<Instant, Int>>()
    while (t <= to.toEpochMilliseconds()) {
        val at = Instant.fromEpochMilliseconds(t)
        val local = at.toLocalDateTime(zone)
        if (local.minute == 0 && local.hour % stepHours == 0) ticks += at to local.hour
        t += hourMs
    }
    return ticks
}

@Composable
private fun focusDescription(state: GlucoseScreenState): String {
    val readings = state.readings.filter { it.readingAt >= state.focusFrom && it.readingAt <= state.focusEnd }
    if (readings.isEmpty()) return stringResource(R.string.glucose_chart_empty_description)
    val values = readings.map { it.displayValueMmolL }
    val trend = state.delta15Mmol?.let { formatDelta(it) } ?: stringResource(R.string.glucose_value_empty)
    return stringResource(R.string.glucose_chart_description, formatMmol(values.min()), formatMmol(values.max()), trend)
}

internal fun Instant.hourMinute(): String {
    val time = toLocalDateTime(TimeZone.currentSystemDefault()).time
    return "%02d:%02d".format(time.hour, time.minute)
}
