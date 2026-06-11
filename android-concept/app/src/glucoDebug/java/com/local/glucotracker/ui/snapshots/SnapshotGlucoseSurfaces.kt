package com.local.glucotracker.ui.snapshots

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.Spacer
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import com.local.glucotracker.R
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTHintBox
import com.local.glucotracker.ui.design.tokens.GTColors
import com.local.glucotracker.ui.feature.history.HistoryMealRowUi
import com.local.glucotracker.ui.feature.today.TodayMealRowUi
import com.local.glucotracker.ui.glucose.GlucoseSurfaces
import com.local.glucotracker.ui.glucose.HistoryTimelineCircleInput
import com.local.glucotracker.ui.glucose.HistoryTimelineMeal
import com.local.glucotracker.ui.glucose.MealContextAnchor
import com.local.glucotracker.ui.glucose.layoutHistoryTimelineCircles
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlin.math.sqrt

object SnapshotGlucoseSurfaces : GlucoseSurfaces {
    @Composable
    override fun MiniGlucoseCard(modifier: Modifier) {
        GTHintBox(
            text = stringResource(R.string.today_glucose_no_fresh),
            modifier = modifier,
        )
    }

    @Composable
    override fun TodayGlucoseKpiCard(modifier: Modifier): Boolean {
        GTHintBox(
            text = stringResource(R.string.today_kpi_below_range),
            modifier = modifier,
        )
        return true
    }

    @Composable
    override fun StatsTirSection(periodApiValue: String) {
        GTHintBox(text = stringResource(R.string.stats_tir_empty))
    }

    @Composable
    override fun StatsDaypartSection() {
        GTHintBox(text = stringResource(R.string.stats_daypart_caption))
    }

    @Composable
    override fun RecordGlucoseAtMealPanel(eatenAt: Instant) {
        GTHintBox(text = stringResource(R.string.record_glucose_at, "09:15"))
    }

    @Composable
    override fun StackMealGlucoseMetaRow(eatenAt: Instant) {
        GTHintBox(text = stringResource(R.string.record_glucose_at, "09:15"))
    }

    @Composable
    override fun StackMealContextMetaRows(
        mealId: String?,
        eatenAt: Instant,
        meals: List<MealContextAnchor>,
    ) = Unit

    @Composable
    override fun TodayRows(
        date: LocalDate,
        rows: List<TodayMealRowUi>,
        rowContent: @Composable (
            row: TodayMealRowUi,
            extraMetaContent: @Composable ColumnScope.() -> Unit,
        ) -> Unit,
    ) {
        rows.forEachIndexed { index, row ->
            rowContent(row, {})
            if (index < rows.lastIndex) Spacer(Modifier.height(14.dp))
        }
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
        rows.forEachIndexed { index, row ->
            rowContent(row, {})
            if (index < rows.lastIndex) divider()
        }
    }

    @Composable
    override fun HistoryDayTimeline(
        date: LocalDate,
        meals: List<HistoryTimelineMeal>,
        onMealTap: (String) -> Unit,
        modifier: Modifier,
    ) {
        val colors = GT.colors
        val sortedMeals = meals.sortedBy { it.minutesOfDay }
        Canvas(
            modifier = modifier
                .fillMaxWidth()
                .height(48.dp)
                .pointerInput(sortedMeals) {
                    detectTapGestures { offset ->
                        val baselineY = size.height / 2f
                        val laidOut = layoutHistoryTimelineCircles(
                            meals = sortedMeals.map { meal ->
                                HistoryTimelineCircleInput(
                                    id = meal.id,
                                    x = size.width * (meal.minutesOfDay / 1_440f),
                                    naturalY = baselineY - snapshotWaveY(
                                        meal.minutesOfDay,
                                        size.height.toFloat(),
                                    ),
                                    radius = computeTimelineRadiusPx(meal.kcal),
                                )
                            },
                            padding = 2.dp.toPx(),
                        )
                        val tapped = laidOut.asReversed().firstOrNull { layout ->
                            (offset - Offset(layout.x, layout.y)).getDistance() <= maxOf(
                                layout.radius,
                                12.dp.toPx(),
                            )
                        }
                        tapped?.let { onMealTap(it.id) }
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
            var previous: Offset? = null
            (0..24).forEach { hour ->
                val x = size.width * (hour / 24f)
                val y = baselineY - snapshotWaveY(hour * 60, size.height)
                previous?.let { from ->
                    drawLine(
                        color = colors.ink2.copy(alpha = 0.7f),
                        start = from,
                        end = Offset(x, y),
                        strokeWidth = 1.5.dp.toPx(),
                        cap = StrokeCap.Round,
                    )
                }
                previous = Offset(x, y)
            }
            val mealsById = sortedMeals.associateBy { it.id }
            val laidOut = layoutHistoryTimelineCircles(
                meals = sortedMeals.map { meal ->
                    HistoryTimelineCircleInput(
                        id = meal.id,
                        x = size.width * (meal.minutesOfDay / 1_440f),
                        naturalY = baselineY - snapshotWaveY(meal.minutesOfDay, size.height),
                        radius = computeTimelineRadiusPx(meal.kcal),
                    )
                },
                padding = 2.dp.toPx(),
            )
            laidOut.forEach { layout ->
                val meal = mealsById.getValue(layout.id)
                val center = Offset(layout.x, layout.y)
                drawCircle(
                    color = snapshotResponseColor(meal.responseKey, colors, 0.5f),
                    radius = layout.radius,
                    center = center,
                )
                drawCircle(
                    color = if (meal.stuck) {
                        colors.warn.copy(alpha = 0.8f)
                    } else {
                        snapshotResponseColor(meal.responseKey, colors, 0.8f)
                    },
                    radius = layout.radius,
                    center = center,
                    style = Stroke(width = 1.dp.toPx()),
                )
            }
        }
    }

    @Composable
    override fun MoreNightscoutSection() {
        Column {
            GTHintBox(text = stringResource(R.string.more_ns_connected))
            GTHairlineDivider()
        }
    }
}

private fun snapshotWaveY(minutesOfDay: Int, height: Float): Float {
    val phase = minutesOfDay / 1_440f
    return ((phase - 0.5f) * (phase - 0.5f) * -1f + 0.2f) * height * 0.42f
}

private fun Density.computeTimelineRadiusPx(kcal: Int?): Float {
    val normalized = sqrt(((kcal ?: 0) / 700f).coerceIn(0f, 1f))
    return 4.dp.toPx() + normalized * (14.dp.toPx() - 4.dp.toPx())
}

private fun snapshotResponseColor(
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
