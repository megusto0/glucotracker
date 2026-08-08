package com.local.glucotracker.ui.glucose

import androidx.compose.runtime.Composable
import androidx.compose.runtime.ProvidableCompositionLocal
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import com.local.glucotracker.ui.feature.history.HistoryEntryTone
import com.local.glucotracker.ui.feature.history.HistoryMealRowUi
import com.local.glucotracker.ui.feature.today.TodayMealRowUi
import com.local.glucotracker.domain.model.HistoryFilter
import androidx.compose.ui.unit.dp
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlin.math.abs

data class HistoryTimelineMeal(
    val id: String,
    val minutesOfDay: Int,
    val kcal: Int?,
    //: Carbohydrates are what move the curve, so the gluco timeline sizes by
    //: these. The food timeline keeps sizing by [kcal], which is its subject.
    val carbsG: Double?,
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
    /** Flavor-owned history filters. Their copy stays out of the food APK. */
    @Composable
    fun HistoryQuickFilters(
        filters: Set<HistoryFilter>,
        onToggleFilter: (HistoryFilter) -> Unit,
    ) = Unit

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
        recommendationEligible: Boolean = false,
    )

    /**
     * The day's glucose as one column of the summary band, not a card.
     *
     * Returns false when the flavor has nothing to put there, so the caller can
     * fall back to a food statistic rather than leaving a hole in the row.
     */
    @Composable
    fun TodayGlucoseStat(modifier: Modifier = Modifier): Boolean

    /**
     * Sleep and hard effort as two numbers under the day's totals.
     *
     * Background, not records: the intervals themselves belong in the list at
     * the hour they happened. Renders nothing for a flavor with no watch.
     */
    @Composable
    fun TodayBodyStates(date: LocalDate, modifier: Modifier = Modifier)

    @Composable
    fun TodayRows(
        date: LocalDate,
        rows: List<TodayMealRowUi>,
        // framed = false means the row is drawn inside a shared episode card
        // and must not draw its own card border.
        // showTime = false means the sitting has already stated this minute —
        // three plates photographed together printed it three times over.
        rowContent: @Composable (
            row: TodayMealRowUi,
            framed: Boolean,
            showTime: Boolean,
            // The kind of record, drawn as a bar down its photo. Null where the
            // flavor has no kinds, which leaves the photo unmarked.
            kindColor: Color?,
            extraMetaContent: @Composable ColumnScope.() -> Unit,
        ) -> Unit,
    )

    @Composable
    fun HistoryRows(
        date: LocalDate,
        rows: List<HistoryMealRowUi>,
        filters: Set<HistoryFilter>,
        // tone is the backend episode classification, or null when unknown or
        // for the food flavor, in which case the row renders plain.
        // framed = false means the row sits inside a shared episode card, which
        // supplies both the surface and the time in its header — so the row
        // draws neither. Same contract as TodayRows.
        rowContent: @Composable (
            row: HistoryMealRowUi,
            tone: HistoryEntryTone?,
            framed: Boolean,
            showTime: Boolean,
            extraMetaContent: @Composable ColumnScope.() -> Unit,
        ) -> Unit,
        divider: @Composable () -> Unit,
    )

    @Composable
    fun HistoryDayTimeline(
        date: LocalDate,
        meals: List<HistoryTimelineMeal>,
        filters: Set<HistoryFilter>,
        onMealTap: (String) -> Unit,
        modifier: Modifier = Modifier,
    )

    /**
     * Second line of a history day heading: how the day went.
     *
     * The first line counts what went in. On a diabetes journal the share of
     * the day spent in range is the number worth reading next to it, and it
     * comes from the backend rather than being recomputed here. The food noop
     * renders nothing.
     */
    @Composable
    fun HistoryDayGlucoseSummary(date: LocalDate, modifier: Modifier = Modifier)

    @Composable
    fun MoreNightscoutSection()

    /**
     * Health Connect settings. Lives in the flavor that has Health Connect, so
     * the shared screen needs neither its classes nor a reflective bridge to
     * them; the food binary carries none of it.
     */
    @Composable
    fun MoreHealthConnectSection()
}

val LocalGlucoseSurfaces: ProvidableCompositionLocal<GlucoseSurfaces> =
    staticCompositionLocalOf { GlucoseSurfacesNoop }

object GlucoseSurfacesNoop : GlucoseSurfaces {
    @Composable
    override fun HistoryQuickFilters(
        filters: Set<HistoryFilter>,
        onToggleFilter: (HistoryFilter) -> Unit,
    ) = Unit

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
        recommendationEligible: Boolean,
    ) = Unit

    @Composable
    override fun TodayGlucoseStat(modifier: Modifier): Boolean = false

    @Composable
    override fun TodayBodyStates(date: LocalDate, modifier: Modifier) = Unit

    @Composable
    override fun TodayRows(
        date: LocalDate,
        rows: List<TodayMealRowUi>,
        rowContent: @Composable (
            row: TodayMealRowUi,
            framed: Boolean,
            showTime: Boolean,
            // The kind of record, drawn as a bar down its photo. Null where the
            // flavor has no kinds, which leaves the photo unmarked.
            kindColor: Color?,
            extraMetaContent: @Composable ColumnScope.() -> Unit,
        ) -> Unit,
    ) {
        rows.forEachIndexed { index, row ->
            rowContent(row, true, true, null, {})
            if (index < rows.lastIndex) Spacer(Modifier.height(14.dp))
        }
    }

    @Composable
    override fun HistoryRows(
        date: LocalDate,
        rows: List<HistoryMealRowUi>,
        filters: Set<HistoryFilter>,
        rowContent: @Composable (
            row: HistoryMealRowUi,
            tone: HistoryEntryTone?,
            framed: Boolean,
            showTime: Boolean,
            extraMetaContent: @Composable ColumnScope.() -> Unit,
        ) -> Unit,
        divider: @Composable () -> Unit,
    ) {
        // No episodes without glucose, so each row carries its own card and its
        // own time — the same shape this flavor's Today already has.
        rows.forEachIndexed { index, row ->
            rowContent(row, null, true, true, {})
            if (index < rows.lastIndex) divider()
        }
    }

    @Composable
    override fun HistoryDayTimeline(
        date: LocalDate,
        meals: List<HistoryTimelineMeal>,
        filters: Set<HistoryFilter>,
        onMealTap: (String) -> Unit,
        modifier: Modifier,
    ) = Unit

    @Composable
    override fun HistoryDayGlucoseSummary(date: LocalDate, modifier: Modifier) = Unit

    @Composable
    override fun MoreNightscoutSection() = Unit

    @Composable
    override fun MoreHealthConnectSection() = Unit
}
