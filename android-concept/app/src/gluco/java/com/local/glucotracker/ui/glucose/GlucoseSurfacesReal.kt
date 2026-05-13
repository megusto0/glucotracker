package com.local.glucotracker.ui.glucose

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.GlucoseRange
import com.local.glucotracker.domain.model.NightscoutConnectionState
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTHintBox
import com.local.glucotracker.ui.design.primitives.GTKicker
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.format.formatMmol
import javax.inject.Inject
import kotlinx.datetime.Clock
import kotlinx.datetime.DatePeriod
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.atStartOfDayIn
import kotlinx.datetime.plus
import kotlinx.datetime.toLocalDateTime
import kotlin.math.abs

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
    override fun HistoryDayCgmSparkline(date: LocalDate) {
        val viewModel: GlucoseSparklineViewModel = hiltViewModel()
        val points by viewModel.points(date).collectAsStateWithLifecycle(initialValue = emptyList())
        Sparkline(
            points = points,
            color = GT.colors.info,
            modifier = Modifier
                .padding(start = 10.dp, top = 4.dp)
                .size(width = 72.dp, height = 28.dp),
        )
    }

    @Composable
    override fun MoreNightscoutSection() {
        MoreNightscoutSurface()
        GTHairlineDivider()
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
