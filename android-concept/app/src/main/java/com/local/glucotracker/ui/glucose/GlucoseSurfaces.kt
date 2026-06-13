package com.local.glucotracker.ui.glucose

import androidx.compose.runtime.Composable
import androidx.compose.runtime.ProvidableCompositionLocal
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import com.local.glucotracker.ui.feature.history.HistoryMealRowUi
import com.local.glucotracker.ui.feature.today.TodayMealRowUi
import androidx.compose.ui.unit.dp
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlin.math.abs

data class HistoryTimelineMeal(
    val id: String,
    val minutesOfDay: Int,
    val kcal: Int?,
    val accepted: Boolean,
    val stuck: Boolean,
    val mainMeal: Boolean,
    val responseKey: String?,
)

data class MealContextAnchor(
    val id: String,
    val eatenAt: Instant,
)

data class HistoryTimelineCircleInput(
    val id: String,
    val x: Float,
    val naturalY: Float,
    val radius: Float,
)

data class HistoryTimelineCircleLayout(
    val id: String,
    val x: Float,
    val y: Float,
    val naturalY: Float,
    val radius: Float,
)

fun layoutHistoryTimelineCircles(
    meals: List<HistoryTimelineCircleInput>,
    padding: Float,
): List<HistoryTimelineCircleLayout> {
    val laidOut = mutableListOf<HistoryTimelineCircleLayout>()
    meals.forEach { meal ->
        val priorOverlap = laidOut.lastOrNull { prior ->
            abs(prior.x - meal.x) < (prior.radius + meal.radius - padding)
        }
        val y = if (priorOverlap == null) {
            meal.naturalY
        } else {
            val offset = (meal.radius + priorOverlap.radius) * 0.6f
            when {
                abs(priorOverlap.y - priorOverlap.naturalY) < 0.5f -> meal.naturalY - offset
                priorOverlap.y < priorOverlap.naturalY -> meal.naturalY + offset
                else -> meal.naturalY - offset
            }
        }
        laidOut += HistoryTimelineCircleLayout(
            id = meal.id,
            x = meal.x,
            y = y,
            naturalY = meal.naturalY,
            radius = meal.radius,
        )
    }
    return laidOut
}

interface GlucoseSurfaces {
    @Composable
    fun MiniGlucoseCard(modifier: Modifier = Modifier)

    /**
     * Fourth KPI card on the Today grid. The gluco flavor renders a
     * descriptive below-range glance for the current day and returns true;
     * the noop returns false so the caller keeps the kcal-remaining card.
     */
    @Composable
    fun TodayGlucoseKpiCard(modifier: Modifier = Modifier): Boolean

    /**
     * Daily TIR distribution card on the stats page. The gluco flavor
     * fetches the backend-computed per-day band shares for [periodApiValue]
     * (e.g. "30d") from the gluco-gated endpoint; the food noop renders
     * nothing.
     */
    @Composable
    fun StatsTirSection(periodApiValue: String)

    @Composable
    fun StatsDaypartSection()

    @Composable
    fun RecordGlucoseAtMealPanel(eatenAt: Instant)

    @Composable
    fun StackMealGlucoseMetaRow(eatenAt: Instant)

    @Composable
    fun StackMealContextMetaRows(
        mealId: String?,
        eatenAt: Instant,
        meals: List<MealContextAnchor> = emptyList(),
    )

    @Composable
    fun TodayRows(
        date: LocalDate,
        rows: List<TodayMealRowUi>,
        // framed = false means the row is drawn inside a shared episode card
        // and must not draw its own card border.
        rowContent: @Composable (
            row: TodayMealRowUi,
            framed: Boolean,
            extraMetaContent: @Composable ColumnScope.() -> Unit,
        ) -> Unit,
    )

    @Composable
    fun HistoryRows(
        date: LocalDate,
        rows: List<HistoryMealRowUi>,
        rowContent: @Composable (
            row: HistoryMealRowUi,
            extraMetaContent: @Composable ColumnScope.() -> Unit,
        ) -> Unit,
        divider: @Composable () -> Unit,
    )

    @Composable
    fun HistoryDayTimeline(
        date: LocalDate,
        meals: List<HistoryTimelineMeal>,
        onMealTap: (String) -> Unit,
        modifier: Modifier = Modifier,
    )

    @Composable
    fun MoreNightscoutSection()
}

val LocalGlucoseSurfaces: ProvidableCompositionLocal<GlucoseSurfaces> =
    staticCompositionLocalOf { GlucoseSurfacesNoop }

object GlucoseSurfacesNoop : GlucoseSurfaces {
    @Composable
    override fun MiniGlucoseCard(modifier: Modifier) = Unit

    @Composable
    override fun TodayGlucoseKpiCard(modifier: Modifier): Boolean = false

    @Composable
    override fun StatsTirSection(periodApiValue: String) = Unit

    @Composable
    override fun StatsDaypartSection() = Unit

    @Composable
    override fun RecordGlucoseAtMealPanel(eatenAt: Instant) = Unit

    @Composable
    override fun StackMealGlucoseMetaRow(eatenAt: Instant) = Unit

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
            framed: Boolean,
            extraMetaContent: @Composable ColumnScope.() -> Unit,
        ) -> Unit,
    ) {
        rows.forEachIndexed { index, row ->
            rowContent(row, true, {})
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
    ) = Unit

    @Composable
    override fun MoreNightscoutSection() = Unit
}
