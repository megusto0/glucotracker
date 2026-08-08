package com.local.glucotracker.ui.design.primitives

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
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
) {
    enum class Kind { Meal, Snack }
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
) {
    val colors = GT.colors
    val sortedMeals = meals
        .filter { it.kcal > 0.0 }
        .sortedBy { it.minutesOfDay }
    Canvas(
        modifier = modifier.semantics {
            this.contentDescription = contentDescription
        },
    ) {
        val goal = goalKcal?.toDouble()?.takeIf { it > 0.0 }
        val top = max(max(goal ?: 0.0, totalKcal), 1.0) * 1.1
        val x: (Double) -> Float = { minutes ->
            (size.width * (minutes / MinutesPerDay)).toFloat().coerceIn(0f, size.width)
        }
        val y: (Double) -> Float = { kcal ->
            (size.height * (1.0 - kcal.coerceIn(0.0, top) / top)).toFloat()
        }
        val rawSum = sortedMeals.sumOf { it.kcal }
        val scale = if (rawSum > 0.0 && totalKcal > 0.0) totalKcal / rawSum else 1.0
        val points = mutableListOf(0.0 to 0.0)
        var accumulated = 0.0
        sortedMeals.forEach { meal ->
            val start = meal.minutesOfDay.toDouble()
            val contribution = meal.kcal * scale
            points += start to accumulated
            repeat(RampSamples) { sampleIndex ->
                val progress = (sampleIndex + 1).toDouble() / RampSamples
                val eased = progress * progress * (3.0 - 2.0 * progress)
                points += (start + MealRampMinutes * progress) to
                    (accumulated + contribution * eased)
            }
            accumulated += contribution
        }
        points += MinutesPerDay to totalKcal.coerceAtLeast(0.0)

        val line = Path().apply {
            points.forEachIndexed { index, (minutes, kcal) ->
                if (index == 0) moveTo(x(minutes), y(kcal)) else lineTo(x(minutes), y(kcal))
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

        accumulated = 0.0
        sortedMeals.forEach { meal ->
            accumulated += meal.kcal * scale
            val markerColor = when (meal.kind) {
                FoodCurveMeal.Kind.Meal -> colors.kindMeal
                FoodCurveMeal.Kind.Snack -> colors.kindSnack
            }
            val radius = (2.6.dp.toPx() + sqrt(meal.kcal).toFloat() * 0.18.dp.toPx())
                .coerceIn(3.5.dp.toPx(), 7.dp.toPx())
            val center = Offset(
                x(meal.minutesOfDay + MealRampMinutes),
                y(accumulated),
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

private const val MinutesPerDay = 1_440.0
private const val MealRampMinutes = 45.0
private const val RampSamples = 6
