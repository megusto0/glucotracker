package com.local.glucotracker.ui.design.primitives

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.local.glucotracker.ui.design.GT
import kotlin.math.max
import kotlin.math.sqrt

data class FoodCurveMeal(
    val minutesOfDay: Int,
    val kcal: Double,
    val kind: Kind,
    val id: String? = null,
) {
    enum class Kind { Meal, Snack }
}

internal data class FoodCurvePoint(
    val minutesOfDay: Double,
    val kcal: Double,
)

internal data class FoodCurveMarker(
    val minutesOfDay: Double,
    val accumulatedKcal: Double,
    val mealKcal: Double,
    val kind: FoodCurveMeal.Kind,
    val id: String?,
)

internal data class FoodCurveLayout(
    val points: List<FoodCurvePoint>,
    val markers: List<FoodCurveMarker>,
)

/**
 * Produces a time-monotonic curve even when sittings overlap or share a time.
 *
 * Appending one 45-minute ramp after another made the path jump back to the
 * next meal's start. On screen those backward segments looked like hooks. The
 * layout below samples the sum of all active ramps at increasing timestamps,
 * so both axes can only move forward.
 */
internal fun foodCurveLayout(
    meals: List<FoodCurveMeal>,
    totalKcal: Double,
): FoodCurveLayout {
    val sortedMeals = meals
        .filter { it.kcal > 0.0 }
        .sortedBy { it.minutesOfDay }
    val rawSum = sortedMeals.sumOf { it.kcal }
    val scale = if (rawSum > 0.0 && totalKcal > 0.0) totalKcal / rawSum else 1.0
    val contributions = sortedMeals.map { meal ->
        val start = meal.minutesOfDay.toDouble().coerceIn(0.0, MinutesPerDay)
        val duration = MealRampMinutes.coerceAtMost(MinutesPerDay - start).coerceAtLeast(1.0)
        CurveContribution(
            meal = meal,
            start = start,
            end = start + duration,
            kcal = meal.kcal * scale,
        )
    }
    fun accumulatedAt(minutes: Double): Double = contributions.sumOf { contribution ->
        val progress = ((minutes - contribution.start) / (contribution.end - contribution.start))
            .coerceIn(0.0, 1.0)
        val eased = progress * progress * (3.0 - 2.0 * progress)
        contribution.kcal * eased
    }

    val sampleTimes = buildSet {
        var minute = 0.0
        while (minute <= MinutesPerDay) {
            add(minute)
            minute += CurveSampleMinutes
        }
        contributions.forEach { contribution ->
            add(contribution.start)
            add(contribution.end)
        }
        add(MinutesPerDay)
    }.sorted()
    val points = sampleTimes.map { minute ->
        FoodCurvePoint(minutesOfDay = minute, kcal = accumulatedAt(minute))
    }
    val markers = contributions.map { contribution ->
        FoodCurveMarker(
            minutesOfDay = contribution.end,
            accumulatedKcal = accumulatedAt(contribution.end),
            mealKcal = contribution.meal.kcal,
            kind = contribution.meal.kind,
            id = contribution.meal.id,
        )
    }
    return FoodCurveLayout(points = points, markers = markers)
}

/**
 * The food flavor's day-at-a-glance curve from Tour 6 of the concept mockup.
 *
 * The backend total remains authoritative. Individual accepted meal calories
 * determine the relative steps, then the curve is normalized to end exactly
 * at [totalKcal], so a stale or partial row cache cannot invent another daily
 * headline. Marker area still reflects each meal's own server value.
 */
@Composable
fun FoodDayCurve(
    meals: List<FoodCurveMeal>,
    totalKcal: Double,
    goalKcal: Int?,
    contentDescription: String,
    modifier: Modifier = Modifier,
    onMealTap: (String) -> Unit = {},
) {
    val colors = GT.colors
    val layout = foodCurveLayout(meals = meals, totalKcal = totalKcal)
    val goal = goalKcal?.toDouble()?.takeIf { it > 0.0 }
    val top = max(max(goal ?: 0.0, totalKcal), 1.0) * 1.1
    Canvas(
        modifier = modifier
            .pointerInput(layout, top, onMealTap) {
                detectTapGestures { tap ->
                    val marker = layout.markers
                        .asReversed()
                        .firstOrNull { candidate ->
                            val center = Offset(
                                x = (size.width * (candidate.minutesOfDay / MinutesPerDay)).toFloat(),
                                y = (size.height *
                                    (1.0 - candidate.accumulatedKcal.coerceIn(0.0, top) / top)).toFloat(),
                            )
                            (tap - center).getDistance() <= 14.dp.toPx()
                        }
                    marker?.id?.let(onMealTap)
                }
            }
            .semantics {
                this.contentDescription = contentDescription
            },
    ) {
        val x: (Double) -> Float = { minutes ->
            (size.width * (minutes / MinutesPerDay)).toFloat().coerceIn(0f, size.width)
        }
        val y: (Double) -> Float = { kcal ->
            (size.height * (1.0 - kcal.coerceIn(0.0, top) / top)).toFloat()
        }
        val line = Path().apply {
            layout.points.forEachIndexed { index, point ->
                if (index == 0) {
                    moveTo(x(point.minutesOfDay), y(point.kcal))
                } else {
                    lineTo(x(point.minutesOfDay), y(point.kcal))
                }
            }
        }
        val area = Path().apply {
            addPath(line)
            lineTo(size.width, size.height)
            lineTo(0f, size.height)
            close()
        }
        drawPath(area, color = colors.hairline.copy(alpha = 0.52f))
        goal?.let { goalValue ->
            drawLine(
                color = colors.hairline2,
                start = Offset(0f, y(goalValue)),
                end = Offset(size.width, y(goalValue)),
                strokeWidth = 1.dp.toPx(),
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(4.dp.toPx(), 4.dp.toPx())),
            )
        }
        drawPath(
            path = line,
            color = colors.ink2.copy(alpha = 0.78f),
            style = Stroke(width = 1.4.dp.toPx()),
        )

        layout.markers.forEach { marker ->
            val markerColor = when (marker.kind) {
                FoodCurveMeal.Kind.Meal -> colors.kindMeal
                FoodCurveMeal.Kind.Snack -> colors.kindSnack
            }
            val radius = (2.6.dp.toPx() + sqrt(marker.mealKcal).toFloat() * 0.18.dp.toPx())
                .coerceIn(3.5.dp.toPx(), 7.dp.toPx())
            val center = Offset(
                x(marker.minutesOfDay),
                y(marker.accumulatedKcal),
            )
            drawCircle(markerColor.copy(alpha = 0.08f), radius = radius, center = center)
            drawCircle(
                markerColor.copy(alpha = 0.85f),
                radius = radius,
                center = center,
                style = Stroke(width = 1.2.dp.toPx()),
            )
        }
    }
}

private data class CurveContribution(
    val meal: FoodCurveMeal,
    val start: Double,
    val end: Double,
    val kcal: Double,
)

private const val MinutesPerDay = 1_440.0
private const val MealRampMinutes = 45.0
private const val CurveSampleMinutes = 5.0
