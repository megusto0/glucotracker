package com.local.glucotracker.ui.glucose

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.GlucoseReading
import com.local.glucotracker.domain.model.GlucoseRange
import com.local.glucotracker.domain.model.EpisodeTherapyClass
import com.local.glucotracker.domain.model.InsulinDayContext
import com.local.glucotracker.domain.model.InsulinEvent
import com.local.glucotracker.domain.model.InsulinEventType
import com.local.glucotracker.domain.model.NightscoutConnectionState
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTHintBox
import com.local.glucotracker.ui.design.primitives.GTKicker
import com.local.glucotracker.ui.design.primitives.GTKpiCard
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.design.tokens.GTColors
import com.local.glucotracker.ui.feature.history.HistoryEntryTone
import com.local.glucotracker.ui.feature.history.HistoryMealRowUi
import com.local.glucotracker.ui.feature.insulin.HistoricalInsulinButton
import com.local.glucotracker.ui.feature.insulin.InsulinManagementSheet
import com.local.glucotracker.ui.feature.today.TodayMealRowKind
import com.local.glucotracker.ui.feature.today.TodayMealRowUi
import com.local.glucotracker.ui.format.formatGrams
import com.local.glucotracker.ui.format.formatKcal
import com.local.glucotracker.ui.format.formatMmol
import com.local.glucotracker.ui.format.formatPercent
import java.text.DecimalFormat
import java.text.DecimalFormatSymbols
import java.util.Locale
import javax.inject.Inject
import kotlinx.datetime.Clock
import kotlinx.datetime.DatePeriod
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.atStartOfDayIn
import kotlinx.datetime.plus
import kotlinx.datetime.toLocalDateTime
import kotlinx.coroutines.delay
import kotlin.math.abs
import kotlin.math.sqrt
import kotlin.time.Duration.Companion.minutes

class GlucoseSurfacesReal @Inject constructor() : GlucoseSurfaces {
    @Composable
    override fun MiniGlucoseCard(modifier: Modifier) {
        MiniGlucoseSurface(modifier)
    }

    @Composable
    override fun TodayGlucoseKpiCard(modifier: Modifier): Boolean {
        TodayGlucoseKpiSurface(modifier)
        return true
    }

    @Composable
    override fun StatsTirSection(periodApiValue: String) {
        val viewModel: StatsTirViewModel = hiltViewModel()
        LaunchedEffect(periodApiValue) { viewModel.load(periodApiValue) }
        val days by viewModel.state.collectAsStateWithLifecycle()
        if (days.none { it.hasData }) {
            GlucoseNoteCard(
                title = stringResource(R.string.stats_chart_tir),
                text = stringResource(R.string.stats_tir_empty),
            )
            return
        }
        StatsTirDailyCard(days = days)
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
    override fun StackMealGlucoseMetaRow(eatenAt: Instant) {
        StackGlucoseMetaRow(eatenAt)
    }

    @Composable
    override fun StackMealContextMetaRows(
        mealId: String?,
        eatenAt: Instant,
        meals: List<MealContextAnchor>,
        recommendationEligible: Boolean,
    ) {
        val viewModel: InsulinContextViewModel = hiltViewModel()
        val date = eatenAt.toLocalDateTime(TimeZone.currentSystemDefault()).date
        val signature = remember(meals) {
            mealGroupingSignature(meals.map { MealGroupingKey(it.id, it.eatenAt) })
        }
        LaunchedEffect(date, signature) { viewModel.onMealsChanged(date, "stack", signature) }
        val context by viewModel.context(date)
            .collectAsStateWithLifecycle(initialValue = InsulinDayContext.Empty)
        val paired = mealId?.let { context.byMealId[it] }.orEmpty()
        if (paired.isNotEmpty()) {
            InsulinMetaRow(events = paired)
        }
        // The episode may span more than one sitting, because a bolus inside the
        // linking window of two meals joins them however far apart they are.
        // Ask only about the sitting the tapped dish belongs to.
        val targetIds = mealId?.let { id ->
            val episode = context.mealEpisodeGroups.firstOrNull { id in it }
                ?: return@let listOf(id)
            eatingOccasion(
                episodeMealIds = episode,
                eatenAt = meals.associate { it.id to it.eatenAt },
                anchorId = id,
            )
        }.orEmpty()
        // Units anchored anywhere in that sitting, not just to this dish.
        val episodeUnits = targetIds.sumOf { id ->
            context.byMealId[id].orEmpty().sumOf { it.doseUnits }
        }
        val isCurrentDay =
            date == Clock.System.now().toLocalDateTime(TimeZone.currentSystemDefault()).date
        // Not gated on today or on being undosed any more. After a dose the
        // sheet becomes a comparison against what was actually given, which is
        // the more useful reading and what the desktop has always done; the
        // food half is stored server-side, so looking is cheap.
        if (
            recommendationEligible &&
            targetIds.isNotEmpty() &&
            targetIds.all { runCatching { java.util.UUID.fromString(it) }.isSuccess }
        ) {
            HistoricalInsulinButton(
                mealIds = targetIds,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 6.dp),
                alreadyGivenUnits = episodeUnits,
            )
        }
    }

    @Composable
    override fun TodayRows(
        date: LocalDate,
        rows: List<TodayMealRowUi>,
        rowContent: @Composable (
            row: TodayMealRowUi,
            framed: Boolean,
            showTime: Boolean,
            extraMetaContent: @Composable ColumnScope.() -> Unit,
        ) -> Unit,
    ) {
        val viewModel: InsulinContextViewModel = hiltViewModel()
        val signature = remember(rows) {
            mealGroupingSignature(
                rows.mapNotNull { row ->
                    row.recordId?.let { MealGroupingKey(it, row.eatenAt, row.totalCarbsG) }
                },
            )
        }
        LaunchedEffect(date, signature) { viewModel.onMealsChanged(date, "today", signature) }
        val context by viewModel.context(date)
            .collectAsStateWithLifecycle(initialValue = InsulinDayContext.Empty)
        TodayEpisodeRows(
            date = date,
            context = context,
            rows = rows,
            rowContent = rowContent,
        )
    }

    @Composable
    override fun HistoryRows(
        date: LocalDate,
        rows: List<HistoryMealRowUi>,
        rowContent: @Composable (
            row: HistoryMealRowUi,
            tone: HistoryEntryTone?,
            showTime: Boolean,
            extraMetaContent: @Composable ColumnScope.() -> Unit,
        ) -> Unit,
        divider: @Composable () -> Unit,
    ) {
        val viewModel: InsulinContextViewModel = hiltViewModel()
        val signature = remember(rows) {
            mealGroupingSignature(
                rows.mapNotNull { row ->
                    row.recordId?.let { MealGroupingKey(it, row.eatenAt, row.totalCarbsG) }
                },
            )
        }
        LaunchedEffect(date, signature) { viewModel.onMealsChanged(date, "history", signature) }
        val context by viewModel.context(date)
            .collectAsStateWithLifecycle(initialValue = InsulinDayContext.Empty)
        InsulinAwareRows(
            context = context,
            rows = rows,
            rowId = { row -> row.id },
            rowTime = { row -> row.eatenAt },
            rowTone = { row -> context.classificationByMealId[row.id].toTone() },
            rowRecordId = { row -> row.recordId },
            rowContent = rowContent,
            separator = divider,
        )
    }

    @Composable
    override fun HistoryDayTimeline(
        date: LocalDate,
        meals: List<HistoryTimelineMeal>,
        onMealTap: (String) -> Unit,
        modifier: Modifier,
    ) {
        val viewModel: GlucoseSparklineViewModel = hiltViewModel()
        val readings by viewModel.readings(date).collectAsStateWithLifecycle(initialValue = emptyList())
        val contextViewModel: InsulinContextViewModel = hiltViewModel()
        val context by contextViewModel.context(date)
            .collectAsStateWithLifecycle(initialValue = InsulinDayContext.Empty)
        DayTimelineGluco(
            meals = meals,
            readings = readings,
            classification = context.classificationByMealId,
            insulin = context.allEvents,
            onMealTap = onMealTap,
            modifier = modifier,
        )
    }

    @Composable
    override fun HistoryDayGlucoseSummary(date: LocalDate, modifier: Modifier) {
        val viewModel: HistoryDayGlucoseViewModel = hiltViewModel()
        LaunchedEffect(Unit) { viewModel.ensureLoaded() }
        val days by viewModel.state.collectAsStateWithLifecycle()
        val day = days[date] ?: return
        Text(
            text = if (day.highPct == 0 && day.lowPct == 0) {
                stringResource(
                    R.string.history_day_glucose_clean,
                    formatPercent(day.inRangePct.toDouble()),
                )
            } else {
                stringResource(
                    R.string.history_day_glucose,
                    formatPercent(day.inRangePct.toDouble()),
                    formatPercent(day.highPct.toDouble()),
                    formatPercent(day.lowPct.toDouble()),
                )
            },
            modifier = modifier,
            color = GT.colors.muted,
            style = GT.type.monoLabel,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }

    @Composable
    override fun MoreNightscoutSection() {
        MoreGlucoseSettingsSurface()
    }
}

@Composable
private fun StackGlucoseMetaRow(eatenAt: Instant) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 3.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = stringResource(R.string.record_glucose_kicker),
            color = GT.colors.muted,
            style = GT.type.kicker.copy(fontSize = 8.sp),
            maxLines = 1,
        )
        Text(
            text = stringResource(R.string.stack_glucose_meta_value, eatenAt.timeText()),
            modifier = Modifier.padding(start = 10.dp),
            color = GT.colors.ink2,
            style = GT.type.monoLabel.copy(fontSize = 10.sp),
            maxLines = 1,
        )
    }
}

@Composable
private fun TodayEpisodeRows(
    date: LocalDate,
    context: InsulinDayContext,
    rows: List<TodayMealRowUi>,
    rowContent: @Composable (
        row: TodayMealRowUi,
        framed: Boolean,
        showTime: Boolean,
        extraMetaContent: @Composable ColumnScope.() -> Unit,
    ) -> Unit,
) {
    var responseCardEvent by remember { mutableStateOf<InsulinEvent?>(null) }
    val items = remember(context, rows) { buildTodayTimeline(context, rows) }
    val isCurrentDay =
        date == Clock.System.now().toLocalDateTime(TimeZone.currentSystemDefault()).date

    items.forEachIndexed { index, item ->
        when (item) {
            is TodayTimelineItem.Single -> TodaySingleCard(
                entry = item.entry,
                rowContent = rowContent,
            )
            is TodayTimelineItem.Episode -> TodayEpisodeCard(
                entries = item.entries,
                recommendationEligible = isCurrentDay,
                rowContent = rowContent,
            )
            is TodayTimelineItem.Orphan -> OrphanInsulinRow(
                event = item.event,
                onOpenResponse = { responseCardEvent = item.event }
                    .takeIf { !item.event.isPending },
            )
        }
        if (index < items.lastIndex) Spacer(Modifier.height(14.dp))
    }

    responseCardEvent?.let { event ->
        CorrectionResponseSheet(
            event = event,
            onDismiss = { responseCardEvent = null },
        )
    }
}

private data class TodayMealEntry(
    val row: TodayMealRowUi,
    val paired: List<InsulinEvent>,
)


private sealed interface TodayTimelineItem {
    val timestamp: Instant

    data class Single(val entry: TodayMealEntry, override val timestamp: Instant) : TodayTimelineItem
    data class Episode(
        val entries: List<TodayMealEntry>,
        override val timestamp: Instant,
    ) : TodayTimelineItem
    data class Orphan(val event: InsulinEvent, override val timestamp: Instant) : TodayTimelineItem
}

/**
 * Groups accepted meals that the backend episode engine considers one eating
 * event into a single card; everything else stays a standalone card/row.
 */
private fun buildTodayTimeline(
    context: InsulinDayContext,
    rows: List<TodayMealRowUi>,
): List<TodayTimelineItem> {
    val rowById = rows.associateBy { it.id }
    val entryOf = { row: TodayMealRowUi ->
        TodayMealEntry(row = row, paired = context.byMealId[row.id].orEmpty())
    }
    val groupedIds = mutableSetOf<String>()
    val episodes = context.mealEpisodeGroups.mapNotNull { group ->
        val present = group.mapNotNull { rowById[it] }
        if (present.size < 2) return@mapNotNull null
        present.forEach { groupedIds += it.id }
        val entries = present
            .sortedByDescending { it.eatenAt }
            .map(entryOf)
        TodayTimelineItem.Episode(
            entries = entries,
            timestamp = present.maxOf { it.eatenAt },
        )
    }

    val singles = rows
        .filter { it.id !in groupedIds }
        .map { row -> TodayTimelineItem.Single(entryOf(row), row.eatenAt) }

    val anchoredIds = rows.map { it.id }.toSet()
    val orphanEvents = context.orphans +
        context.byMealId.filterKeys { it !in anchoredIds }.values.flatten()
    val orphans = orphanEvents.map { TodayTimelineItem.Orphan(it, it.timestamp) }

    return (episodes + singles + orphans).sortedByDescending { it.timestamp }
}

/**
 * One dish, in the same shape a sitting of several gets.
 *
 * Its actions used to hang off the row's meta column, which has the time
 * gutter and the photo taken out of its width — so the pair wrapped and sat
 * indented under a short divider while the sitting beside it had them side by
 * side across the card. Same structure for both now: card, rows, hairline,
 * footer. The row itself is drawn unframed, exactly as it is inside a sitting,
 * so this card supplies the surface.
 */
@Composable
private fun TodaySingleCard(
    entry: TodayMealEntry,
    rowContent: @Composable (
        row: TodayMealRowUi,
        framed: Boolean,
        showTime: Boolean,
        extraMetaContent: @Composable ColumnScope.() -> Unit,
    ) -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 18.dp)
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card),
    ) {
        rowContent(entry.row, false, true) {
            entry.paired.forEach { event -> InlineInsulinLine(event = event) }
        }
        entry.row.recordId
            ?.takeIf { entry.row.kind == TodayMealRowKind.Accepted }
            ?.let { mealId ->
                GlucoCardActionRow {
                    // Kept after a dose: it stops being a suggestion and
                    // becomes a comparison against what was given.
                    HistoricalInsulinButton(
                        mealIds = listOf(mealId),
                        alreadyGivenUnits = entry.paired
                            .sumOf { event -> event.doseUnits },
                    )
                    SittingTimeButton(
                        meals = listOf(SittingMeal(mealId, entry.row.eatenAt)),
                    )
                }
            }
    }
}

@Composable
private fun TodayEpisodeCard(
    entries: List<TodayMealEntry>,
    recommendationEligible: Boolean,
    rowContent: @Composable (
        row: TodayMealRowUi,
        framed: Boolean,
        showTime: Boolean,
        extraMetaContent: @Composable ColumnScope.() -> Unit,
    ) -> Unit,
) {
    val totalCarbs = entries.sumOf { it.row.totalCarbsG ?: 0.0 }
    val totalKcal = entries.sumOf { it.row.totalKcal ?: 0.0 }
    val totalInsulin = entries.sumOf { entry -> entry.paired.sumOf { it.doseUnits } }
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 18.dp)
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(start = 14.dp, end = 14.dp, top = 10.dp, bottom = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            GTKicker(text = stringResource(R.string.today_episode_kicker, entries.size))
            Spacer(Modifier.weight(1f))
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    text = todayEpisodeSummary(totalCarbs, totalKcal, totalInsulin),
                    color = GT.colors.muted,
                    style = GT.type.monoLabel.copy(fontSize = 11.sp),
                    maxLines = 1,
                )
                // The totals alone say nothing about whether the dose worked
                // out: the same units can be right for the food and still land
                // after it, which is what leaves insulin acting once the carbs
                // are gone. Show the achieved ratio and the timing split.
                todayEpisodeCoverage(entries, totalCarbs, totalInsulin)?.let { coverage ->
                    Text(
                        text = coverage,
                        color = GT.colors.muted,
                        style = GT.type.monoLabel.copy(fontSize = 10.sp),
                        maxLines = 1,
                    )
                }
            }
        }
        GTHairlineDivider(modifier = Modifier.padding(horizontal = 14.dp))
        // The time stays in the gutter, where the rest of the page keeps it.
        // Only the repeats go: a plate that starts a new minute states it, the
        // ones photographed alongside it leave the column blank.
        var statedMinute: String? = null
        entries.forEachIndexed { index, entry ->
            val minute = entry.row.eatenAt.timeText()
            val showTime = minute != statedMinute
            statedMinute = minute
            rowContent(entry.row, false, showTime) {
                entry.paired.forEach { event -> InlineInsulinLine(event = event) }
            }
            if (index < entries.lastIndex) {
                GTHairlineDivider(modifier = Modifier.padding(horizontal = 14.dp))
            }
        }
        // An episode card can hold two sittings, and the last one is what any
        // question is being asked about. Anchor on the newest plate.
        val anchorEntry = entries.maxByOrNull { it.row.eatenAt }
        val sitting = anchorEntry?.row?.recordId?.let { anchorId ->
            eatingOccasion(
                episodeMealIds = entries.mapNotNull { it.row.recordId },
                eatenAt = entries.mapNotNull { entry ->
                    entry.row.recordId?.let { it to entry.row.eatenAt }
                }.toMap(),
                anchorId = anchorId,
            )
        }.orEmpty()
        val sittingMeals = entries.mapNotNull { entry ->
            entry.row.recordId
                ?.takeIf { it in sitting }
                ?.let { SittingMeal(it, entry.row.eatenAt) }
        }
        // No divider over an empty row.
        if (recommendationEligible || sittingMeals.size >= 2) GlucoCardActionRow {
            if (recommendationEligible) {
                // Kept visible after a dose exists: that is exactly when the
                // question changes from "how much" to "was it enough", and
                // hiding it removed the only place the two numbers meet.
                HistoricalInsulinButton(
                    mealIds = sitting,
                    alreadyGivenUnits = entries
                        .filter { it.row.recordId in sitting }
                        .sumOf { entry -> entry.paired.sumOf { it.doseUnits } },
                )
            }
            // Not gated on the day: a sitting logged at the wrong hour is
            // exactly the thing you come back to History to fix.
            SittingTimeButton(meals = sittingMeals)
        }
    }
}

@Composable
private fun todayEpisodeCoverage(
    entries: List<TodayMealEntry>,
    totalCarbs: Double,
    totalInsulin: Double,
): String? {
    val coverage = episodeCoverage(
        doses = entries.flatMap { entry ->
            entry.paired.map { event ->
                EpisodeDose(
                    units = event.doseUnits,
                    lateBy = event.timestamp - entry.row.eatenAt,
                )
            }
        },
        totalCarbs = totalCarbs,
        totalInsulin = totalInsulin,
    ) ?: return null
    val ratio = stringResource(
        R.string.today_episode_ratio,
        formatGrams(coverage.gramsPerUnit),
    )
    val split = if (coverage.lateUnits <= 0.0) {
        stringResource(R.string.today_episode_all_on_time)
    } else {
        val onTimeText = stringResource(
            R.string.today_episode_split_on_time,
            formatInsulinDose(coverage.onTimeUnits),
        )
        val lateText = stringResource(
            R.string.today_episode_split_late,
            formatInsulinDose(coverage.lateUnits),
        )
        "$onTimeText · $lateText"
    }
    return "$ratio · $split"
}

@Composable
private fun todayEpisodeSummary(
    totalCarbs: Double,
    totalKcal: Double,
    totalInsulin: Double,
): String {
    val carbs = stringResource(R.string.today_episode_carbs, formatGrams(totalCarbs))
    val kcal = stringResource(R.string.today_episode_kcal, formatKcal(totalKcal))
    val base = "$carbs · $kcal"
    return if (totalInsulin > 0.0) {
        "$base · ${formatInsulinDose(totalInsulin)} ${stringResource(R.string.insulin_units_short)}"
    } else {
        base
    }
}

@Composable
private fun <T> InsulinAwareRows(
    context: InsulinDayContext,
    rows: List<T>,
    rowId: (T) -> String,
    rowTime: (T) -> Instant,
    rowTone: @Composable (T) -> HistoryEntryTone?,
    rowRecordId: (T) -> String?,
    rowContent: @Composable (
        row: T,
        tone: HistoryEntryTone?,
        showTime: Boolean,
        extraMetaContent: @Composable ColumnScope.() -> Unit,
    ) -> Unit,
    separator: @Composable () -> Unit = { Spacer(Modifier.height(14.dp)) },
) {
    var responseCardEvent by remember { mutableStateOf<InsulinEvent?>(null) }
    val timeline = remember(context, rows) {
        val rowIds = rows.map(rowId).toSet()
        val rowById = rows.associateBy(rowId)
        // Events anchored to meals not present in the row list (e.g. other
        // statuses) still surface as standalone rows instead of vanishing.
        val unanchored = context.byMealId
            .filterKeys { mealId -> mealId !in rowIds }
            .values
            .flatten()
        // One sitting used to appear as several unrelated rows with the
        // insulin hanging off whichever item happened to be anchored, which
        // read as though the rest of the plate went uncovered.
        val grouped = mutableSetOf<String>()
        val episodes = context.mealEpisodeGroups.mapNotNull { group ->
            val present = group.mapNotNull { rowById[it] }
            if (present.size < 2) return@mapNotNull null
            present.forEach { grouped += rowId(it) }
            InsulinTimelineItem.Episode(
                rows = present.sortedByDescending(rowTime),
                paired = present.flatMap { context.byMealId[rowId(it)].orEmpty() }
                    .distinctBy { event -> event.id },
                timestamp = present.maxOf(rowTime),
            )
        }
        (
            episodes +
                rows.filterNot { rowId(it) in grouped }.map { row ->
                    InsulinTimelineItem.Meal(
                        row = row,
                        paired = context.byMealId[rowId(row)].orEmpty(),
                        timestamp = rowTime(row),
                    )
                } +
                (context.orphans + unanchored).map { event ->
                    InsulinTimelineItem.Orphan(event = event, timestamp = event.timestamp)
                }
            ).sortedByDescending { item -> item.timestamp }
    }

    timeline.forEachIndexed { index, item ->
        when (item) {
            is InsulinTimelineItem.Meal -> {
                rowContent(item.row, rowTone(item.row), true) {
                    item.paired.forEach { event ->
                        InlineInsulinLine(event = event)
                    }
                    HistoryRecommendationButton(
                        mealIds = listOfNotNull(rowRecordId(item.row)),
                        givenUnits = item.paired.sumOf { it.doseUnits },
                    )
                }
            }
            is InsulinTimelineItem.Episode -> {
                // The insulin belongs to the sitting, so it is stated once
                // under the last item rather than beside an arbitrary one.
                // Same for the time: a plate that starts a new minute states
                // it, the ones photographed alongside it leave it blank.
                var statedMinute: String? = null
                item.rows.forEachIndexed { rowIndex, row ->
                    val minute = rowTime(row).timeText()
                    val showTime = minute != statedMinute
                    statedMinute = minute
                    rowContent(row, rowTone(row), showTime) {
                        if (rowIndex == item.rows.lastIndex) {
                            item.paired.forEach { event ->
                                InlineInsulinLine(event = event)
                            }
                            // Only the calculation here. History's column is
                            // narrower than Today's and the second action was
                            // clipped to a single letter; the sitting's time is
                            // editable on Today, where it fits.
                            HistoryRecommendationButton(
                                mealIds = item.rows.mapNotNull(rowRecordId),
                                givenUnits = item.paired.sumOf { it.doseUnits },
                            )
                        }
                    }
                }
            }
            is InsulinTimelineItem.Orphan -> OrphanInsulinRow(
                event = item.event,
                onOpenResponse = { responseCardEvent = item.event }
                    .takeIf { !item.event.isPending },
            )
        }
        if (index < timeline.lastIndex) separator()
    }

    responseCardEvent?.let { event ->
        CorrectionResponseSheet(
            event = event,
            onDismiss = { responseCardEvent = null },
        )
    }
}

/** Mixed and unresolved stay untinted: a guess is not worth a colour. */
@Composable
private fun EpisodeTherapyClass?.toTone(): HistoryEntryTone? = when (this) {
    EpisodeTherapyClass.Meal -> HistoryEntryTone(HistoryEntryTone.Kind.Meal, null)
    EpisodeTherapyClass.Snack -> HistoryEntryTone(
        HistoryEntryTone.Kind.Snack,
        stringResource(R.string.history_tone_snack),
    )
    EpisodeTherapyClass.CarbCorrection -> HistoryEntryTone(
        HistoryEntryTone.Kind.CarbCorrection,
        stringResource(R.string.history_tone_carb_correction),
    )
    EpisodeTherapyClass.InsulinCorrection -> HistoryEntryTone(
        HistoryEntryTone.Kind.InsulinCorrection,
        stringResource(R.string.history_tone_insulin_correction),
    )
    EpisodeTherapyClass.Mixed,
    EpisodeTherapyClass.Unresolved,
    null,
    -> null
}

/**
 * The calculation for a past sitting, which History never offered at all.
 *
 * Only for sittings that carry real meal records. Once insulin exists the sheet
 * reads as a comparison rather than a suggestion.
 */
@Composable
private fun HistoryRecommendationButton(mealIds: List<String>, givenUnits: Double) {
    val valid = mealIds.filter { id ->
        runCatching { java.util.UUID.fromString(id) }.isSuccess
    }
    if (valid.isEmpty()) return
    HistoricalInsulinButton(mealIds = valid, alreadyGivenUnits = givenUnits)
}

private sealed interface InsulinTimelineItem<out T> {
    val timestamp: Instant

    data class Meal<T>(
        val row: T,
        val paired: List<InsulinEvent>,
        override val timestamp: Instant,
    ) : InsulinTimelineItem<T>

    /** Several rows the backend reads as one sitting, sharing their insulin. */
    data class Episode<T>(
        val rows: List<T>,
        val paired: List<InsulinEvent>,
        override val timestamp: Instant,
    ) : InsulinTimelineItem<T>

    data class Orphan(
        val event: InsulinEvent,
        override val timestamp: Instant,
    ) : InsulinTimelineItem<Nothing>
}

@Composable
private fun InlineInsulinLine(event: InsulinEvent) {
    var showTooltip by remember(event.id) { mutableStateOf(false) }
    var showManagement by remember(event.id) { mutableStateOf(false) }
    LaunchedEffect(showTooltip) {
        if (showTooltip) {
            delay(1_500)
            showTooltip = false
        }
    }
    Column(modifier = Modifier.padding(top = 3.dp)) {
        Row(
            modifier = Modifier
                .heightIn(min = 44.dp)
                .pointerInput(event.id, event.isReadOnly, event.isPending) {
                    detectTapGestures(
                        onTap = {
                            if (!event.isReadOnly && !event.isPending) {
                                showManagement = true
                            } else {
                                showTooltip = true
                            }
                        },
                        onLongPress = { showTooltip = true },
                    )
                },
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "+ ${formatInsulinDose(event.doseUnits)} ${stringResource(R.string.insulin_units_short)} · ${event.timestamp.timeText()}",
                color = GT.colors.ink2.copy(alpha = 0.72f),
                style = GT.type.monoLabel.copy(fontSize = 10.sp),
                maxLines = 1,
            )
            val suffix = event.sourceSuffix()
            if (suffix.isNotEmpty()) {
                Spacer(Modifier.width(6.dp))
                Text(
                    text = suffix,
                    color = GT.colors.ink2.copy(alpha = 0.46f),
                    style = GT.type.monoLabel.copy(fontSize = 10.sp),
                    maxLines = 1,
                )
            }
        }
        if (showTooltip) {
            InsulinTooltip(event = event)
        }
    }
    if (showManagement) {
        InsulinManagementSheet(
            event = event,
            onDismiss = { showManagement = false },
        )
    }
}

@Composable
private fun OrphanInsulinRow(
    event: InsulinEvent,
    onOpenResponse: (() -> Unit)? = null,
) {
    var showTooltip by remember(event.id) { mutableStateOf(false) }
    var showManagement by remember(event.id) { mutableStateOf(false) }
    LaunchedEffect(showTooltip) {
        if (showTooltip) {
            delay(1_500)
            showTooltip = false
        }
    }
    // On its own surface like everything else on the page. A correction with
    // no meal is still a record, and rendering it as a bare line between two
    // cards read as something that had failed to draw. Quieter inside than a
    // meal card, because it carries one number rather than a plate.
    Column(
        modifier = Modifier
            .padding(horizontal = 18.dp)
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .padding(horizontal = 14.dp, vertical = 2.dp),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = 44.dp)
                .pointerInput(event.id, onOpenResponse, event.isReadOnly, event.isPending) {
                    detectTapGestures(
                        onTap = {
                            if (!event.isReadOnly && !event.isPending) {
                                showManagement = true
                            } else {
                                onOpenResponse?.invoke()
                            }
                        },
                        onLongPress = { showTooltip = true },
                    )
                }
                .padding(vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = event.timestamp.timeText(),
                modifier = Modifier.width(36.dp),
                color = GT.colors.muted,
                style = GT.type.monoLabel.copy(fontSize = 10.sp),
                maxLines = 1,
            )
            Text(
                text = "+",
                modifier = Modifier.width(32.dp),
                color = GT.colors.ink2.copy(alpha = 0.7f),
                style = GT.type.monoLabel.copy(fontSize = 12.sp),
                maxLines = 1,
            )
            Text(
                text = listOfNotNull(
                    "${formatInsulinDose(event.doseUnits)} ${stringResource(R.string.insulin_units_short)}",
                    stringResource(R.string.insulin_correction).takeIf {
                        event.eventType == InsulinEventType.Correction
                    },
                ).joinToString("  "),
                modifier = Modifier.weight(1f),
                color = GT.colors.ink2.copy(alpha = 0.72f),
                style = GT.type.monoLabel.copy(fontSize = 10.sp),
                maxLines = 1,
            )
            Text(
                text = event.displaySource(),
                color = GT.colors.ink2.copy(alpha = 0.46f),
                style = GT.type.monoLabel.copy(fontSize = 10.sp),
                maxLines = 1,
            )
        }
        if (showTooltip) {
            InsulinTooltip(event = event)
        }
    }
    if (showManagement) {
        InsulinManagementSheet(
            event = event,
            onDismiss = { showManagement = false },
        )
    }
}

@Composable
private fun InsulinMetaRow(events: List<InsulinEvent>) {
    val unit = stringResource(R.string.insulin_units_short)
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 3.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = stringResource(R.string.stack_meta_insulin),
            color = GT.colors.muted,
            style = GT.type.kicker.copy(fontSize = 8.sp),
            maxLines = 1,
        )
        Text(
            text = events.joinToString("; ") { event ->
                "${formatInsulinDose(event.doseUnits)} $unit · ${event.timestamp.timeText()}"
            },
            modifier = Modifier.padding(start = 10.dp),
            color = GT.colors.ink2,
            style = GT.type.monoLabel.copy(fontSize = 10.sp),
            maxLines = 1,
        )
    }
}

@Composable
private fun InsulinTooltip(event: InsulinEvent) {
    Box(
        modifier = Modifier
            .padding(top = 4.dp)
            .background(GT.colors.surface2, GT.shapes.tag)
            .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.tag)
            .padding(horizontal = 8.dp, vertical = 5.dp),
    ) {
        Text(
            text = stringResource(
                R.string.insulin_attribution_tooltip,
                event.displaySource(),
                event.sourceEventId ?: event.id,
            ),
            color = GT.colors.ink2,
            style = GT.type.monoLabel.copy(fontSize = 10.sp),
            maxLines = 1,
        )
    }
}

/**
 * Trailing label for one insulin line, or empty when there is nothing to say.
 *
 * Practically every event arrives from Nightscout, so repeating the word on
 * each line cost the width that then truncated it — three identical "Nightscou"
 * fragments under one meal. It is kept only where it distinguishes something:
 * an event still in the outbox, or a source that is not the usual one.
 */
@Composable
private fun InsulinEvent.sourceSuffix(): String {
    val source = when {
        isPending -> stringResource(R.string.insulin_source_pending)
        source.equals("nightscout", ignoreCase = true) -> ""
        else -> source
    }
    val kind = when (eventType) {
        InsulinEventType.Correction -> stringResource(R.string.insulin_correction)
        InsulinEventType.CatchUp -> stringResource(R.string.insulin_catch_up)
        else -> ""
    }
    return listOf(kind, source).filter { it.isNotBlank() }.joinToString(" · ")
}

/**
 * Descriptive glucose response around one standalone correction — same idea
 * as the meal cards' postprandial view, computed from cached CGM readings.
 * No advice, only what happened.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CorrectionResponseSheet(
    event: InsulinEvent,
    onDismiss: () -> Unit,
    viewModel: GlucoseSparklineViewModel = hiltViewModel(),
) {
    val zone = TimeZone.currentSystemDefault()
    val date = event.timestamp.toLocalDateTime(zone).date
    val readings by viewModel.readings(date)
        .collectAsStateWithLifecycle(initialValue = emptyList())
    val windowStartMs = event.timestamp.toEpochMilliseconds() - 30L * 60_000L
    val windowEndMs = event.timestamp.toEpochMilliseconds() + 180L * 60_000L
    val windowReadings = remember(readings, event.id) {
        readings.filter { reading ->
            reading.readingAt.toEpochMilliseconds() in windowStartMs..windowEndMs
        }
    }
    val atInjection = windowReadings.valueNear(event.timestamp.toEpochMilliseconds())
    val plus1h = windowReadings.valueNear(
        event.timestamp.toEpochMilliseconds() + 60L * 60_000L,
    )
    val plus2h = windowReadings.valueNear(
        event.timestamp.toEpochMilliseconds() + 120L * 60_000L,
    )
    val delta2h = if (atInjection != null && plus2h != null) plus2h - atInjection else null

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(),
        containerColor = GT.colors.surface,
        contentColor = GT.colors.ink,
        tonalElevation = 0.dp,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp)
                .padding(bottom = 24.dp),
        ) {
            Text(
                text = stringResource(R.string.correction_sheet_title),
                color = GT.colors.ink,
                style = GT.type.serifSection,
            )
            Text(
                text = stringResource(
                    R.string.correction_sheet_dose,
                    formatInsulinDose(event.doseUnits),
                    event.timestamp.timeText(),
                ),
                modifier = Modifier.padding(top = 4.dp),
                color = GT.colors.muted,
                style = GT.type.monoLabel,
            )
            GTKicker(
                text = stringResource(R.string.correction_sheet_kicker),
                modifier = Modifier.padding(top = 16.dp),
            )
            if (windowReadings.size < 2) {
                GTHintBox(
                    text = stringResource(R.string.correction_sheet_no_data),
                    modifier = Modifier.padding(top = 8.dp),
                )
            } else {
                Sparkline(
                    points = windowReadings.map { it.displayValueMmolL },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(64.dp)
                        .padding(top = 10.dp),
                    color = GT.colors.info,
                )
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 12.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    CorrectionStat(
                        label = stringResource(R.string.correction_sheet_at_injection),
                        value = atInjection,
                        modifier = Modifier.weight(1f),
                    )
                    CorrectionStat(
                        label = stringResource(R.string.correction_sheet_plus_1h),
                        value = plus1h,
                        modifier = Modifier.weight(1f),
                    )
                    CorrectionStat(
                        label = stringResource(R.string.correction_sheet_plus_2h),
                        value = plus2h,
                        modifier = Modifier.weight(1f),
                    )
                    CorrectionStat(
                        label = stringResource(R.string.correction_sheet_delta),
                        value = delta2h,
                        signed = true,
                        modifier = Modifier.weight(1f),
                    )
                }
            }
        }
    }
}

@Composable
private fun CorrectionStat(
    label: String,
    value: Double?,
    modifier: Modifier = Modifier,
    signed: Boolean = false,
) {
    Column(modifier = modifier) {
        Text(
            text = label,
            color = GT.colors.muted,
            style = GT.type.kicker,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Text(
            text = when {
                value == null -> stringResource(R.string.glucose_value_empty)
                signed -> formatGlucoseDelta(value)
                else -> formatMmol(value)
            },
            modifier = Modifier.padding(top = 4.dp),
            color = GT.colors.ink,
            style = GT.type.monoLabel,
            maxLines = 1,
        )
    }
}

private fun List<GlucoseReading>.valueNear(
    targetEpochMs: Long,
    toleranceMs: Long = 15L * 60_000L,
): Double? =
    minByOrNull { reading ->
        kotlin.math.abs(reading.readingAt.toEpochMilliseconds() - targetEpochMs)
    }
        ?.takeIf { reading ->
            kotlin.math.abs(
                reading.readingAt.toEpochMilliseconds() - targetEpochMs,
            ) <= toleranceMs
        }
        ?.displayValueMmolL

@Composable
private fun InsulinEvent.displaySource(): String =
    when {
        isPending -> stringResource(R.string.insulin_source_pending)
        source.equals("nightscout", ignoreCase = true) ->
            stringResource(R.string.insulin_source_nightscout)
        else -> source
    }

private fun formatInsulinDose(value: Double): String =
    InsulinDoseFormat.format(value)

private val InsulinDoseFormat = DecimalFormat(
    "0.0",
    DecimalFormatSymbols(Locale("ru")),
)

@Composable
private fun DayTimelineGluco(
    meals: List<HistoryTimelineMeal>,
    readings: List<GlucoseReading>,
    classification: Map<String, EpisodeTherapyClass>,
    insulin: List<InsulinEvent>,
    onMealTap: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = GT.colors
    val sortedMeals = androidx.compose.runtime.remember(meals) { meals.sortedBy { it.minutesOfDay } }
    val sortedReadings = androidx.compose.runtime.remember(readings) { readings.sortedBy { it.readingAt } }
    val hasReadings = sortedReadings.isNotEmpty()
    val scale = androidx.compose.runtime.remember(sortedReadings) { glucoseScale(sortedReadings) }
    Canvas(
        modifier = modifier
            .height(if (hasReadings) 48.dp else 28.dp)
            .pointerInput(sortedMeals, sortedReadings, scale) {
                detectTapGestures { offset ->
                    val baselineY = size.height / 2f
                    val laidOut = layoutHistoryTimelineCircles(
                        meals = sortedMeals.map { meal ->
                            val x = size.width * (meal.minutesOfDay / TimelineMinutesPerDay)
                            val y = glucoseYAtMeal(
                                meal = meal,
                                readings = sortedReadings,
                                baselineY = baselineY,
                                height = size.height.toFloat(),
                                scale = scale,
                            )
                            HistoryTimelineCircleInput(
                                id = meal.id,
                                x = x.coerceIn(0f, size.width.toFloat()),
                                naturalY = y,
                                radius = computeCarbRadiusPx(meal.carbsG),
                            )
                        },
                        padding = 2.dp.toPx(),
                    )
                    val tapped = laidOut
                        .asReversed()
                        .firstOrNull { layout ->
                            val hitRadius = maxOf(layout.radius, 12.dp.toPx())
                            (offset - Offset(layout.x, layout.y)).getDistance() <= hitRadius
                        }
                    tapped?.let { layout -> onMealTap(layout.id) }
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

        // The band is the whole reference. With a fixed scale behind it, a
        // wiggle at 5.5 reads as small and a climb to 13 reads as a climb,
        // without an axis, labels or gridlines.
        if (scale != null) {
            val top = glucoseY(InRangeHigh, size.height, scale)
            val bottom = glucoseY(InRangeLow, size.height, scale)
            drawRect(
                color = colors.accent.copy(alpha = 0.07f),
                topLeft = Offset(0f, top),
                size = Size(size.width, (bottom - top).coerceAtLeast(1f)),
            )
        }

        // Doses lived only in the rows, so the chart could not show the one
        // thing a day chart is for here: what a dose did to the curve above it.
        // Ticks hang off the baseline, height by units, so they read as a
        // second series without becoming a second chart.
        insulin.forEach { event ->
            val units = event.doseUnits
            if (units <= 0.0) return@forEach
            val minutes = event.timestamp
                .toLocalDateTime(TimeZone.currentSystemDefault())
                .let { it.hour * 60 + it.minute }
            val x = size.width * (minutes / TimelineMinutesPerDay)
            val tick = (units / TimelineInsulinNormalization)
                .coerceIn(0.0, 1.0)
                .toFloat() * TimelineInsulinTickMax.toPx()
            drawLine(
                color = colors.info.copy(alpha = 0.55f),
                start = Offset(x, size.height),
                end = Offset(x, size.height - tick.coerceAtLeast(2.dp.toPx())),
                strokeWidth = 1.5.dp.toPx(),
                cap = StrokeCap.Round,
            )
        }

        if (sortedReadings.size >= 2 && scale != null) {
            val stroke = Stroke(width = 1.5.dp.toPx(), cap = StrokeCap.Round)
            splitContinuousReadings(sortedReadings).forEach { segment ->
                if (segment.size >= 2) {
                    drawPath(
                        path = buildGlucosePath(segment, size.width, size.height, scale),
                        color = colors.ink2.copy(alpha = 0.7f),
                        style = stroke,
                    )
                }
            }
            sortedReadings.zipWithNext()
                .filter { (a, b) -> minutesBetween(a.readingAt, b.readingAt) >= CgmGapMinutes }
                .forEach { (a, b) ->
                    drawPath(
                        path = buildGlucosePath(listOf(a, b), size.width, size.height, scale),
                        color = colors.muted.copy(alpha = 0.4f),
                        style = Stroke(
                            width = 1.dp.toPx(),
                            cap = StrokeCap.Round,
                            pathEffect = PathEffect.dashPathEffect(
                                floatArrayOf(4.dp.toPx(), 4.dp.toPx()),
                            ),
                        ),
                    )
                }
        }

        val mealsById = sortedMeals.associateBy { it.id }
        val laidOut = layoutHistoryTimelineCircles(
            meals = sortedMeals.map { meal ->
                val x = size.width * (meal.minutesOfDay / TimelineMinutesPerDay)
                val y = glucoseYAtMeal(
                    meal = meal,
                    readings = sortedReadings,
                    baselineY = baselineY,
                    height = size.height,
                    scale = scale,
                )
                HistoryTimelineCircleInput(
                    id = meal.id,
                    x = x.coerceIn(0f, size.width),
                    naturalY = y,
                    radius = computeCarbRadiusPx(meal.carbsG),
                )
            },
            padding = 2.dp.toPx(),
        )
        laidOut.forEach { layout ->
            val meal = mealsById.getValue(layout.id)
            val center = Offset(layout.x, layout.y)
            // Same axis as the row rails below. These used to be coloured by
            // glycemic response, so a bubble could be warn for spiking while
            // its own row was tinted for being an insulin correction - two
            // palettes answering different questions on one screen.
            val kind = entryKindColor(classification[meal.id], colors)
            drawCircle(
                color = kind.copy(alpha = 0.5f),
                radius = layout.radius,
                center = center,
            )
            drawCircle(
                color = if (meal.stuck) {
                    colors.warn.copy(alpha = 0.8f)
                } else {
                    kind.copy(alpha = 0.8f)
                },
                radius = layout.radius,
                center = center,
                style = Stroke(width = 1.dp.toPx()),
            )
        }
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
private fun StatsTirDailyCard(
    days: List<TirDayUi>,
    modifier: Modifier = Modifier,
) {
    val veryLowColor = GT.colors.bad
    val lowColor = GT.colors.info
    val inRangeColor = GT.colors.good
    val highColor = GT.colors.warn
    val emptyColor = GT.colors.hairline
    val description = stringResource(R.string.stats_tir_daily_description, days.count { it.hasData })
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .padding(14.dp),
    ) {
        GTKicker(text = stringResource(R.string.stats_tir_daily_title))
        Canvas(
            modifier = Modifier
                .fillMaxWidth()
                .height(120.dp)
                .padding(top = 10.dp)
                .semantics { contentDescription = description },
        ) {
            if (days.isEmpty()) return@Canvas
            val gap = 2.dp.toPx()
            val barWidth = (size.width - gap * (days.size - 1)) / days.size
            days.forEachIndexed { index, day ->
                val x = index * (barWidth + gap)
                if (!day.hasData) {
                    drawRect(
                        color = emptyColor,
                        topLeft = Offset(x, size.height - 2.dp.toPx()),
                        size = Size(barWidth, 2.dp.toPx()),
                    )
                    return@forEachIndexed
                }
                // Stack from the bottom: very low, low, in range, high, very high.
                val segments = listOf(
                    day.veryLowPct to veryLowColor,
                    day.lowPct to lowColor,
                    day.inRangePct to inRangeColor,
                    day.highPct to highColor,
                    day.veryHighPct to veryLowColor,
                )
                var bottom = size.height
                segments.forEach { (pct, color) ->
                    val segmentHeight = (pct / 100.0 * size.height).toFloat()
                    if (segmentHeight > 0f) {
                        drawRect(
                            color = color,
                            topLeft = Offset(x, bottom - segmentHeight),
                            size = Size(barWidth, segmentHeight),
                        )
                        bottom -= segmentHeight
                    }
                }
            }
        }
        Row(
            modifier = Modifier.padding(top = 10.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            GlucoTirLegendItem(
                label = stringResource(R.string.glucose_tir_very_low),
                color = veryLowColor,
            )
            GlucoTirLegendItem(
                label = stringResource(R.string.glucose_tir_low),
                color = lowColor,
            )
            GlucoTirLegendItem(
                label = stringResource(R.string.glucose_tir_range),
                color = inRangeColor,
            )
            GlucoTirLegendItem(
                label = stringResource(R.string.glucose_tir_high),
                color = highColor,
            )
        }
    }
}

@Composable
private fun TodayGlucoseKpiSurface(
    modifier: Modifier = Modifier,
    viewModel: TodayGlucoseKpiViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val percent = state.belowRangePercent
    GTKpiCard(
        label = stringResource(R.string.today_kpi_below_range),
        value = percent?.let { formatPercent(it.toDouble()) }
            ?: stringResource(R.string.glucose_value_empty),
        sub = if (percent != null) {
            stringResource(R.string.today_kpi_below_range_sub)
        } else {
            stringResource(R.string.today_glucose_no_fresh)
        },
        progress = percent?.let { (it / 100f).coerceIn(0f, 1f) } ?: 0f,
        progressColor = GT.colors.info.copy(alpha = 0.65f),
        modifier = modifier,
    )
}

@Composable
private fun MoreGlucoseSettingsSurface(
    viewModel: MoreNightscoutViewModel = hiltViewModel(),
    settingsViewModel: MoreGlucoseSettingsViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val alarms by settingsViewModel.alarmToggles.collectAsStateWithLifecycle()
    val normalizedDisplay by settingsViewModel.normalizedGlucoseDisplay.collectAsStateWithLifecycle()
    val connected = state.status.connectionState == NightscoutConnectionState.Connected
    val statusLabel = when {
        state.isRefreshing -> stringResource(R.string.more_ns_checking)
        connected -> stringResource(R.string.more_ns_connected)
        else -> stringResource(R.string.more_ns_disconnected)
    }
    val nightscoutDescription = state.status.lastSyncAt?.let { lastSync ->
        stringResource(R.string.more_gluco_nightscout_desc, statusLabel, lastSync.timeText())
    } ?: stringResource(R.string.more_gluco_nightscout_no_sync, statusLabel)

    Column(verticalArrangement = Arrangement.spacedBy(18.dp)) {
        GlucoSettingsSection(
            title = stringResource(R.string.more_gluco_sensor_section),
            note = stringResource(R.string.more_gluco_sensor_note),
        ) {
            GlucoSettingsGroup {
                GlucoSettingsRow(
                    title = stringResource(R.string.more_section_nightscout),
                    description = nightscoutDescription,
                    action = {
                        GTOutlineButton(
                            text = if (state.isRefreshing) {
                                stringResource(R.string.more_ns_checking)
                            } else {
                                stringResource(R.string.more_ns_sync_now)
                            },
                            onClick = viewModel::syncNow,
                            enabled = !state.isRefreshing,
                        )
                    },
                )
                if (state.status.queueDepth > 0) {
                    GTHairlineDivider()
                    GlucoSettingsRow(
                        title = stringResource(
                            R.string.more_ns_unsynced,
                            state.status.queueDepth,
                        ),
                        description = stringResource(R.string.more_ns_hint),
                        locked = true,
                    )
                }
                GTHairlineDivider()
                GlucoSettingsRow(
                    title = stringResource(R.string.more_gluco_calibration_title),
                    description = stringResource(R.string.more_gluco_calibration_desc),
                    locked = true,
                    action = { GlucoDesktopPill() },
                )
            }
        }

        GlucoSettingsSection(
            title = stringResource(R.string.more_gluco_display_section),
            note = stringResource(R.string.more_gluco_display_note),
        ) {
            GlucoSettingsGroup {
                GlucoSettingsRow(
                    title = stringResource(R.string.more_gluco_normalized_title),
                    description = stringResource(R.string.more_gluco_normalized_desc),
                    action = {
                        GlucoSettingsSwitch(
                            checked = normalizedDisplay,
                            accent = GT.colors.info,
                            onToggle = settingsViewModel::toggleNormalizedGlucoseDisplay,
                        )
                    },
                    onClick = settingsViewModel::toggleNormalizedGlucoseDisplay,
                )
            }
        }

        GlucoTirSection()

        GlucoSettingsSection(
            title = stringResource(R.string.more_gluco_alarms_section),
            note = stringResource(R.string.more_gluco_alarms_note),
        ) {
            GlucoSettingsGroup {
                GlucoAlarmRow(
                    title = stringResource(R.string.more_gluco_alarm_low_title),
                    description = stringResource(R.string.more_gluco_alarm_low_desc),
                    checked = alarms.low,
                    tone = GT.colors.warn,
                    onToggle = { settingsViewModel.toggleAlarm("low") },
                )
                GTHairlineDivider()
                GlucoAlarmRow(
                    title = stringResource(R.string.more_gluco_alarm_high_title),
                    description = stringResource(R.string.more_gluco_alarm_high_desc),
                    checked = alarms.high,
                    tone = GT.colors.info,
                    onToggle = { settingsViewModel.toggleAlarm("high") },
                )
                GTHairlineDivider()
                GlucoAlarmRow(
                    title = stringResource(R.string.more_gluco_alarm_signal_title),
                    description = stringResource(R.string.more_gluco_alarm_signal_desc),
                    checked = alarms.sensorSignalLoss,
                    tone = GT.colors.info,
                    onToggle = { settingsViewModel.toggleAlarm("sensor_signal_loss") },
                )
            }
        }
    }
}

@Composable
private fun GlucoTirSection() {
    GlucoSettingsSection(
        title = stringResource(R.string.more_gluco_tir_section),
        note = stringResource(R.string.more_gluco_tir_note),
    ) {
        GlucoSettingsGroup {
            Column(
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 14.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Text(
                    text = stringResource(R.string.more_gluco_tir_desc),
                    color = GT.colors.muted,
                    style = GT.type.sansLabel.copy(fontSize = 11.sp),
                )
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(14.dp)
                        .clip(RoundedCornerShape(7.dp)),
                ) {
                    Box(
                        modifier = Modifier
                            .weight(8f)
                            .height(14.dp)
                            .background(GT.colors.bad),
                    )
                    Box(
                        modifier = Modifier
                            .weight(12f)
                            .height(14.dp)
                            .background(GT.colors.info),
                    )
                    Box(
                        modifier = Modifier
                            .weight(56f)
                            .height(14.dp)
                            .background(GT.colors.good),
                    )
                    Box(
                        modifier = Modifier
                            .weight(16f)
                            .height(14.dp)
                            .background(GT.colors.warn),
                    )
                    Box(
                        modifier = Modifier
                            .weight(8f)
                            .height(14.dp)
                            .background(GT.colors.bad),
                    )
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = stringResource(R.string.more_gluco_tir_scale),
                        color = GT.colors.muted,
                        style = GT.type.monoLabel,
                        modifier = Modifier.weight(1f),
                    )
                }
                Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                    GlucoTirLegendItem(
                        label = stringResource(R.string.glucose_tir_very_low),
                        color = GT.colors.bad,
                    )
                    GlucoTirLegendItem(
                        label = stringResource(R.string.glucose_tir_low),
                        color = GT.colors.info,
                    )
                    GlucoTirLegendItem(
                        label = stringResource(R.string.glucose_tir_range),
                        color = GT.colors.good,
                    )
                    GlucoTirLegendItem(
                        label = stringResource(R.string.glucose_tir_high),
                        color = GT.colors.warn,
                    )
                    GlucoTirLegendItem(
                        label = stringResource(R.string.glucose_tir_very_high),
                        color = GT.colors.bad,
                    )
                }
            }
        }
    }
}

@Composable
private fun GlucoTirLegendItem(
    label: String,
    color: Color,
) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier
                .size(8.dp)
                .background(color, GT.shapes.iconButton),
        )
        Text(
            text = label,
            modifier = Modifier.padding(start = 5.dp),
            color = GT.colors.ink2,
            style = GT.type.sansLabel.copy(fontSize = 11.sp),
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun GlucoAlarmRow(
    title: String,
    description: String,
    checked: Boolean,
    tone: Color,
    onToggle: () -> Unit,
) {
    GlucoSettingsRow(
        title = title,
        description = description,
        leading = {
            Box(
                modifier = Modifier
                    .size(18.dp)
                    .border(GT.space.hairline, tone, GT.shapes.iconButton),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    text = "!",
                    color = tone,
                    style = GT.type.monoLabel.copy(fontSize = 11.sp),
                )
            }
        },
        action = {
            GlucoSettingsSwitch(
                checked = checked,
                accent = GT.colors.info,
                onToggle = onToggle,
            )
        },
        onClick = onToggle,
    )
}

@Composable
private fun GlucoSettingsSection(
    title: String,
    note: String? = null,
    content: @Composable () -> Unit,
) {
    Column(
        modifier = Modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            GTKicker(text = title)
            if (note != null) {
                Spacer(Modifier.weight(1f))
                Text(
                    text = note,
                    color = GT.colors.muted,
                    style = GT.type.monoLabel.copy(fontSize = 10.sp),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        content()
    }
}

@Composable
private fun GlucoSettingsGroup(content: @Composable () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(GT.colors.surface2, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .clip(GT.shapes.card),
    ) {
        content()
    }
}

@Composable
private fun GlucoSettingsRow(
    title: String,
    description: String? = null,
    locked: Boolean = false,
    leading: (@Composable () -> Unit)? = null,
    action: (@Composable () -> Unit)? = null,
    onClick: (() -> Unit)? = null,
) {
    val rowModifier = if (onClick == null) Modifier else Modifier.clickable(
        role = Role.Button,
        onClick = onClick,
    )
    Row(
        modifier = rowModifier
            .fillMaxWidth()
            .heightIn(min = 58.dp)
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (leading != null) {
            Box(
                modifier = Modifier.width(30.dp),
                contentAlignment = Alignment.Center,
            ) {
                leading()
            }
            Spacer(Modifier.width(12.dp))
        }
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = title,
                color = if (locked) GT.colors.muted else GT.colors.ink,
                style = GT.type.sansBody.copy(fontSize = 14.sp),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (description != null) {
                Text(
                    text = description,
                    modifier = Modifier.padding(top = 3.dp),
                    color = GT.colors.muted,
                    style = GT.type.sansLabel.copy(fontSize = 11.sp),
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        if (action != null) {
            Spacer(Modifier.width(10.dp))
            action()
        }
    }
}

@Composable
private fun GlucoSettingsSwitch(
    checked: Boolean,
    accent: Color,
    onToggle: () -> Unit,
) {
    Box(
        modifier = Modifier
            .heightIn(min = GT.space.touch)
            .width(50.dp)
            .clickable(role = Role.Switch, onClick = onToggle),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .width(46.dp)
                .height(28.dp)
                .background(
                    color = if (checked) accent else GT.colors.hairline2,
                    shape = RoundedCornerShape(14.dp),
                )
                .padding(3.dp),
            contentAlignment = if (checked) Alignment.CenterEnd else Alignment.CenterStart,
        ) {
            Box(
                modifier = Modifier
                    .size(22.dp)
                    .background(GT.colors.surface2, CircleShape),
            )
        }
    }
}

@Composable
private fun GlucoDesktopPill() {
    Box(
        modifier = Modifier
            .height(22.dp)
            .background(GT.colors.surface, GT.shapes.tag)
            .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.tag)
            .padding(horizontal = 8.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = stringResource(R.string.more_desktop_pill),
            color = GT.colors.muted,
            style = GT.type.sansLabel.copy(fontSize = 9.sp),
            maxLines = 1,
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

/**
 * One scale for every day, so two days can be compared by looking at them.
 *
 * This used to fit each day to its own min and max, which normalised the units
 * away: a day that ran 5.0-7.0 and a day that ran 3.5-12.0 drew the same shape
 * filling the same height. A calm day looked dramatic and a bad day looked
 * ordinary, and scrolling the history compared nothing.
 */
private fun glucoseScale(readings: List<GlucoseReading>): Pair<Double, Double>? {
    if (readings.isEmpty()) return null
    // Widen only for a day that genuinely leaves the fixed frame, so those
    // readings stay on the chart instead of being clipped flat against an edge.
    val values = readings.map { it.displayValueMmolL }
    val yMin = minOf(DisplayGlucoseMin, values.min())
    val yMax = maxOf(DisplayGlucoseMax, values.max())
    return yMin to yMax
}

private fun splitContinuousReadings(readings: List<GlucoseReading>): List<List<GlucoseReading>> {
    if (readings.isEmpty()) return emptyList()
    val segments = mutableListOf<MutableList<GlucoseReading>>()
    readings.forEach { reading ->
        val current = segments.lastOrNull()
        if (current == null || minutesBetween(current.last().readingAt, reading.readingAt) >= CgmGapMinutes) {
            segments += mutableListOf(reading)
        } else {
            current += reading
        }
    }
    return segments
}

private fun buildGlucosePath(
    readings: List<GlucoseReading>,
    width: Float,
    height: Float,
    scale: Pair<Double, Double>,
): Path {
    val path = Path()
    val points = readings.map { reading ->
        Offset(
            x = width * (reading.minutesOfDay() / TimelineMinutesPerDay),
            y = glucoseY(reading.displayValueMmolL, height, scale),
        )
    }
    points.firstOrNull()?.let { first -> path.moveTo(first.x.coerceIn(0f, width), first.y) }
    points.zipWithNext().forEach { (a, b) ->
        val ax = a.x.coerceIn(0f, width)
        val bx = b.x.coerceIn(0f, width)
        val midX = (ax + bx) / 2f
        path.cubicTo(midX, a.y, midX, b.y, bx, b.y)
    }
    return path
}

private fun glucoseYAtMeal(
    meal: HistoryTimelineMeal,
    readings: List<GlucoseReading>,
    baselineY: Float,
    height: Float,
    scale: Pair<Double, Double>?,
): Float {
    if (readings.isEmpty() || scale == null) return baselineY
    val nearest = readings.minByOrNull { reading ->
        abs(reading.minutesOfDay() - meal.minutesOfDay)
    } ?: return baselineY
    return if (abs(nearest.minutesOfDay() - meal.minutesOfDay) <= CgmGapMinutes) {
        glucoseY(nearest.displayValueMmolL, height, scale)
    } else {
        baselineY
    }
}

private fun glucoseY(value: Double, height: Float, scale: Pair<Double, Double>): Float {
    val (yMin, yMax) = scale
    val range = (yMax - yMin).takeIf { it > 0.01 } ?: (DisplayGlucoseMax - DisplayGlucoseMin)
    val normalized = ((value.coerceIn(yMin, yMax) - yMin) / range).coerceIn(0.0, 1.0)
    return height - (normalized.toFloat() * height)
}

private fun GlucoseReading.minutesOfDay(): Int {
    val time = readingAt.toLocalDateTime(TimeZone.currentSystemDefault()).time
    return (time.hour * 60 + time.minute).coerceIn(0, TimelineMinutesPerDayInt - 1)
}

private fun minutesBetween(a: Instant, b: Instant): Long =
    abs(b.toEpochMilliseconds() - a.toEpochMilliseconds()) / 60_000L

/** Sized by carbohydrate, which is what actually moves the curve under it. */
private fun Density.computeCarbRadiusPx(carbsG: Double?): Float {
    val normalized = sqrt(
        ((carbsG ?: 0.0).toFloat() / TimelineCarbNormalization).coerceIn(0f, 1f),
    )
    return TimelineMinRadius.toPx() + normalized * (TimelineMaxRadius.toPx() - TimelineMinRadius.toPx())
}

private fun Density.computeTimelineRadiusPx(kcal: Int?): Float {
    val normalized = sqrt(((kcal ?: 0) / TimelineKcalNormalization).coerceIn(0f, 1f))
    return TimelineMinRadius.toPx() + normalized * (TimelineMaxRadius.toPx() - TimelineMinRadius.toPx())
}

/**
 * Bubble fill by entry kind, matching the History row rails exactly.
 *
 * An ordinary meal stays neutral so the uncommon kinds stand out, which is the
 * same rule the rails follow.
 */
private fun entryKindColor(
    classification: EpisodeTherapyClass?,
    colors: GTColors,
): Color = when (classification) {
    EpisodeTherapyClass.Snack -> colors.accent.copy(alpha = 0.45f)
    EpisodeTherapyClass.CarbCorrection -> colors.warn
    EpisodeTherapyClass.InsulinCorrection -> colors.info
    EpisodeTherapyClass.Meal,
    EpisodeTherapyClass.Mixed,
    EpisodeTherapyClass.Unresolved,
    null,
    -> colors.muted
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

private val TimelineMinRadius = 4.dp
private val TimelineMaxRadius = 14.dp
private const val TimelineKcalNormalization = 700f
private const val TimelineMinutesPerDay = 1_440f
private const val TimelineMinutesPerDayInt = 1_440
private const val CgmGapMinutes = 10L
// Fixed frame every day is drawn in. Wide enough that ordinary days sit calmly
// inside it and a real excursion visibly leaves the band.
private const val DisplayGlucoseMin = 3.0
private const val DisplayGlucoseMax = 14.0
// The band drawn behind the curve. No labels: the reference is the band.
private const val InRangeLow = 3.9
private const val InRangeHigh = 10.0
// A 60 g plate reaches full size; carbohydrate is what moves the curve.
private const val TimelineCarbNormalization = 60f
// A 12 U bolus reaches a full-height tick.
private const val TimelineInsulinNormalization = 12.0
private val TimelineInsulinTickMax = 10.dp
