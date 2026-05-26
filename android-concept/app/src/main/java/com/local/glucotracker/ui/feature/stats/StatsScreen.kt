package com.local.glucotracker.ui.feature.stats

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.DayTotals
import com.local.glucotracker.domain.model.StatsInsight
import com.local.glucotracker.domain.model.StatsPeriod
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHintBox
import com.local.glucotracker.ui.design.primitives.GTKicker
import com.local.glucotracker.ui.design.primitives.GTKpiCard
import com.local.glucotracker.ui.format.formatGrams
import com.local.glucotracker.ui.format.formatKcal
import com.local.glucotracker.ui.format.formatSignedKcal
import com.local.glucotracker.ui.format.truncateToLines
import com.local.glucotracker.ui.glucose.LocalGlucoseSurfaces
import java.time.format.DateTimeFormatter
import java.time.ZoneId
import java.util.Locale
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.roundToLong
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.toJavaInstant
import kotlinx.datetime.toJavaLocalDate

@Composable
fun StatsRoute(
    brandAccentColor: Color? = null,
    viewModel: StatsViewModel = hiltViewModel(),
) {
    val state by if (brandAccentColor != null) {
        viewModel.foodState.collectAsStateWithLifecycle()
    } else {
        viewModel.state.collectAsStateWithLifecycle()
    }
    StatsScreen(
        state = state,
        brandAccentColor = brandAccentColor,
        onPeriodSelected = viewModel::selectPeriod,
    )
}

@Composable
fun StatsScreen(
    state: StatsState,
    modifier: Modifier = Modifier,
    brandAccentColor: Color? = null,
    onPeriodSelected: (StatsPeriod) -> Unit = {},
) {
    when (state) {
        StatsState.Loading -> Box(
            modifier = modifier
                .fillMaxSize()
                .background(GT.colors.bg),
        )
        is StatsState.Sparse -> SparseStats(
            state = state,
            modifier = modifier,
            food = brandAccentColor != null,
        )
        is StatsState.Charts -> if (brandAccentColor != null) {
            FoodStatsCharts(
                state = state,
                accent = brandAccentColor,
                onPeriodSelected = onPeriodSelected,
                modifier = modifier,
            )
        } else {
            StatsCharts(state = state, modifier = modifier)
        }
    }
}

@Composable
private fun SparseStats(
    state: StatsState.Sparse,
    modifier: Modifier = Modifier,
    food: Boolean = false,
) {
    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg)
            .padding(horizontal = 18.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            if (food) {
                Text(
                    text = stringResource(R.string.stats_empty_title),
                    modifier = Modifier.padding(top = 8.dp),
                    color = GT.colors.ink,
                    style = GT.type.serifTitle,
                )
            } else {
                StatsHero(
                    date = state.date,
                    surplusText = stringResource(R.string.stats_surplus_unknown),
                    staleText = null,
                    modifier = Modifier.padding(top = 6.dp),
                )
            }
        }
        item {
            Text(
                text = stringResource(R.string.stats_sparse),
                color = GT.colors.ink2,
                style = GT.type.sansBody,
            )
        }
    }
}

@Composable
private fun StatsCharts(
    state: StatsState.Charts,
    modifier: Modifier = Modifier,
) {
    val days = state.days
    val completedBalances = days
        .filter { it.date < state.date }
        .mapNotNull { it.totals?.netBalanceKcal }
    val balanceTotal = completedBalances.takeIf { it.isNotEmpty() }?.sum()
    val surplusText = when {
        balanceTotal == null -> stringResource(R.string.stats_surplus_unknown)
        balanceTotal >= 0.0 -> stringResource(R.string.stats_surplus, formatKcal(balanceTotal))
        else -> stringResource(R.string.stats_deficit, formatKcal(abs(balanceTotal)))
    }
    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg)
            .padding(horizontal = 18.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            StatsHero(
                date = state.date,
                surplusText = surplusText,
                staleText = state.staleCacheAt?.let {
                    stringResource(R.string.stats_stale_cache, it.toStatsCacheStamp())
                },
                modifier = Modifier.padding(top = 6.dp),
            )
        }
        item {
            StatsKpiGrid(days = days)
        }
        item {
            ChartCard(
                title = stringResource(R.string.stats_chart_carbs),
                caption = stringResource(R.string.stats_chart_carbs_caption),
                bars = days.map { it.toChartBar { totals -> totals.carbsG } },
                color = GT.colors.accent,
                valueText = ::formatGrams,
            )
        }
        item {
            ChartCard(
                title = stringResource(R.string.stats_chart_balance),
                caption = stringResource(R.string.stats_chart_balance_caption),
                bars = days.map { it.toChartBar { totals -> totals.netBalanceKcal } },
                color = GT.colors.warn,
                negativeColor = GT.colors.bad,
                signed = true,
                valueText = { formatSignedKcal(it.roundToLong()) },
            )
        }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                LocalGlucoseSurfaces.current.StatsTirSection()
                LocalGlucoseSurfaces.current.StatsDaypartSection()
                GTHintBox(text = stringResource(R.string.stats_heatmap_hint))
            }
        }
        item {
            Spacer(Modifier.height(10.dp))
        }
    }
}

@Composable
private fun FoodStatsCharts(
    state: StatsState.Charts,
    accent: Color,
    onPeriodSelected: (StatsPeriod) -> Unit,
    modifier: Modifier = Modifier,
) {
    val days = state.days
    val availableDays = days.mapNotNull { it.totals }
    val averageKcal = availableDays
        .takeIf { it.isNotEmpty() }
        ?.sumOf { it.kcal }
        ?.div(availableDays.size)
        ?: 0.0
    val totalDaysInPeriod = days.size
    val daysWithData = availableDays.size
    val leadInsight = state.insights.firstOrNull { it.weight == "primary" && it.kind == "consistent" }
    val cardInsights = state.insights.filter { it.kind != "consistent" }

    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg)
            .padding(horizontal = 18.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            GTKicker(
                text = state.period.toPeriodKicker(
                    days = days,
                    label = stringResource(state.period.kickerRes()),
                ),
                modifier = Modifier.padding(top = 8.dp),
            )
        }
        item {
            StatsLeadStatement(
                averageKcal = averageKcal,
                daysWithData = daysWithData,
                totalDays = totalDaysInPeriod,
                insight = leadInsight,
            )
        }
        item {
            StatsPeriodSegmentedControl(
                selected = state.period,
                accent = accent,
                onSelected = onPeriodSelected,
            )
        }
        if (cardInsights.isNotEmpty()) {
            item {
                InsightCard(insights = cardInsights, accent = accent)
            }
        }
        item {
            StatCard(
                title = stringResource(R.string.stats_kcal_by_day_title),
                contentDescription = stringResource(
                    R.string.stats_kcal_by_day_description,
                    formatKcal(averageKcal),
                ),
            ) {
                KcalByDayBars(
                    days = days,
                    accent = accent,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(148.dp),
                )
            }
        }
        item {
            StatCard(
                title = stringResource(R.string.stats_macro_stack_title),
                contentDescription = stringResource(R.string.stats_macro_stack_description),
            ) {
                MacroStackBar(days = days)
            }
        }
        item {
            StatCard(
                title = stringResource(R.string.stats_time_histogram_title),
                contentDescription = stringResource(R.string.stats_time_histogram_description),
            ) {
                TimeOfDayHistogram(
                    insight = state.insights.firstOrNull {
                        it.kind == "time_of_day_eating"
                    },
                    accent = accent,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(130.dp),
                )
            }
        }
        item {
            Spacer(Modifier.height(10.dp))
        }
    }
}

@Composable
fun StatsLeadStatement(
    averageKcal: Double,
    daysWithData: Int,
    totalDays: Int,
    insight: StatsInsight?,
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier.fillMaxWidth()) {
        Text(
            text = stringResource(R.string.stats_lead_average, formatKcal(averageKcal)),
            color = GT.colors.ink,
            style = GT.type.serifTitle,
        )
        if (daysWithData < totalDays && daysWithData > 0) {
            Text(
                text = stringResource(R.string.stats_lead_coverage, daysWithData, totalDays),
                modifier = Modifier.padding(top = 2.dp),
                color = GT.colors.muted,
                style = GT.type.monoLabel,
            )
        }
        if (insight != null) {
            Text(
                text = insight.text,
                modifier = Modifier.padding(top = 4.dp),
                color = GT.colors.muted,
                style = GT.type.serifSection,
                maxLines = 2,
            )
        }
    }
}

@Composable
private fun StatsPeriodSegmentedControl(
    selected: StatsPeriod,
    accent: Color,
    onSelected: (StatsPeriod) -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = 44.dp)
            .border(GT.space.hairline, GT.colors.hairline, RoundedCornerShape(8.dp))
            .padding(3.dp),
        horizontalArrangement = Arrangement.spacedBy(3.dp),
    ) {
        StatsPeriod.entries.forEach { period ->
            val active = period == selected
            Box(
                modifier = Modifier
                    .weight(1f)
                    .height(38.dp)
                    .background(
                        color = if (active) accent.copy(alpha = 0.18f) else Color.Transparent,
                        shape = RoundedCornerShape(6.dp),
                    )
                    .clickable { onSelected(period) },
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    text = stringResource(period.labelRes()),
                    color = if (active) GT.colors.ink else GT.colors.ink2,
                    style = GT.type.sansLabel,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
fun InsightCard(
    insights: List<StatsInsight>,
    accent: Color,
    modifier: Modifier = Modifier,
) {
    val primary = insights.firstOrNull { it.weight == "primary" }
        ?: insights.firstOrNull()
        ?: return
    val secondary = insights
        .filter { it.weight == "secondary" }
        .take(2)
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(GT.colors.surface2, RoundedCornerShape(12.dp))
            .border(GT.space.hairline, GT.colors.hairline, RoundedCornerShape(12.dp))
            .padding(14.dp),
    ) {
        Text(
            text = stringResource(R.string.stats_insight_kicker),
            color = accent,
            style = GT.type.monoLabel,
        )
        Text(
            text = truncateToLines(primary.text, maxLines = 3, charsPerLine = 40),
            modifier = Modifier.padding(top = 8.dp),
            color = GT.colors.ink2,
            style = GT.type.sansBody,
            maxLines = 3,
        )
        if (secondary.isNotEmpty()) {
            Box(
                modifier = Modifier
                    .padding(vertical = 12.dp)
                    .fillMaxWidth()
                    .height(GT.space.hairline)
                    .background(GT.colors.hairline),
            )
            secondary.forEach { insight ->
                Text(
                    text = insight.text,
                    color = GT.colors.ink2,
                    style = GT.type.sansLabel,
                    maxLines = 1,
                    modifier = Modifier.padding(top = 4.dp),
                )
            }
        }
    }
}

@Composable
private fun StatCard(
    title: String,
    contentDescription: String,
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .semantics { this.contentDescription = contentDescription }
            .padding(14.dp),
    ) {
        GTKicker(text = title)
        Spacer(Modifier.height(12.dp))
        content()
    }
}

@Composable
fun KcalByDayBars(
    days: List<StatsDay>,
    accent: Color,
    modifier: Modifier = Modifier,
) {
    val graphite = GT.colors.ink.copy(alpha = 0.72f)
    val hairline = GT.colors.hairline2
    val muted = GT.colors.muted
    val values = days.map { it.totals?.kcal ?: 0.0 }
    val maxValue = values.maxOrNull()?.coerceAtLeast(1.0) ?: 1.0
    val topDays = values
        .withIndex()
        .sortedByDescending { it.value }
        .take(2)
        .map { it.index }
        .toSet()
    Canvas(modifier = modifier) {
        val labelHeight = 18.dp.toPx()
        val chartHeight = size.height - labelHeight
        val gap = 5.dp.toPx()
        val barWidth = ((size.width - gap * (days.size - 1)) / days.size).coerceAtLeast(2.dp.toPx())
        drawLine(
            color = hairline,
            start = Offset(0f, chartHeight * 0.34f),
            end = Offset(size.width, chartHeight * 0.34f),
            strokeWidth = 0.5.dp.toPx(),
            pathEffect = PathEffect.dashPathEffect(floatArrayOf(4.dp.toPx(), 4.dp.toPx())),
        )
        values.forEachIndexed { index, value ->
            val barHeight = (value / maxValue * chartHeight).toFloat().coerceAtLeast(2.dp.toPx())
            drawRect(
                color = if (index in topDays) accent else graphite,
                topLeft = Offset(index * (barWidth + gap), chartHeight - barHeight),
                size = Size(barWidth, barHeight),
            )
        }
    }
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        days.forEach { day ->
            Text(
                text = day.date.toChartDayLabel(),
                color = muted,
                style = GT.type.monoLabel,
                maxLines = 1,
            )
        }
    }
}

@Composable
fun MacroStackBar(
    days: List<StatsDay>,
    modifier: Modifier = Modifier,
) {
    val totals = days.mapNotNull { it.totals }
    val proteinKcal = totals.sumOf { it.proteinG } * 4.0
    val fatKcal = totals.sumOf { it.fatG } * 9.0
    val carbsKcal = totals.sumOf { it.carbsG } * 4.0
    val total = (proteinKcal + fatKcal + carbsKcal).coerceAtLeast(1.0)
    val segments = listOf(
        Triple(stringResource(R.string.today_kpi_protein), proteinKcal / total, Color(0xFF6B7A92)),
        Triple(stringResource(R.string.today_kpi_fat), fatKcal / total, Color(0xFFC98A55)),
        Triple(stringResource(R.string.today_kpi_carbs), carbsKcal / total, Color(0xFF5E6F3A)),
    )
    Column(modifier = modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(18.dp)
                .background(GT.colors.hairline, RoundedCornerShape(9.dp)),
        ) {
            segments.forEach { (_, percent, color) ->
                Box(
                    modifier = Modifier
                        .weight(percent.toFloat().coerceAtLeast(0.01f))
                        .height(18.dp)
                        .background(color),
                )
            }
        }
        Row(
            modifier = Modifier.padding(top = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            segments.forEach { (label, percent, color) ->
                Text(
                    text = stringResource(R.string.stats_macro_legend, label, (percent * 100).roundToLong()),
                    color = color,
                    style = GT.type.monoLabel,
                )
            }
        }
    }
}

@Composable
fun TimeOfDayHistogram(
    insight: StatsInsight?,
    accent: Color,
    modifier: Modifier = Modifier,
) {
    val supporting = insight?.supportingNumbers.orEmpty()
    val bucketHours = listOf(0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22)
    val maxCount = bucketHours
        .mapNotNull { h -> supporting["h${h.toString().padStart(2, '0')}"]?.toIntOrNull() }
        .maxOrNull()?.coerceAtLeast(1) ?: 0
    val values = bucketHours.map { hour ->
        val count = supporting["h${hour.toString().padStart(2, '0')}"]?.toIntOrNull() ?: 0
        if (maxCount == 0) 0.08f else (count.toFloat() / maxCount).coerceIn(0.08f, 1f)
    }
    val hasData = values.any { it > 0.08f }
    if (!hasData) return
    Canvas(modifier = modifier) {
        val labelHeight = 18.dp.toPx()
        val chartHeight = size.height - labelHeight
        val gap = 6.dp.toPx()
        val barWidth = ((size.width - gap * (values.size - 1)) / values.size).coerceAtLeast(4.dp.toPx())
        values.forEachIndexed { index, value ->
            val height = chartHeight * value
            drawRect(
                color = accent.copy(alpha = 0.18f),
                topLeft = Offset(index * (barWidth + gap), chartHeight - height),
                size = Size(barWidth, height),
            )
        }
    }
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        bucketHours.forEach { hour ->
            Text(
                text = "${hour}",
                color = GT.colors.muted,
                style = GT.type.monoLabel,
            )
        }
    }
}

@Composable
private fun StatsHero(
    date: LocalDate,
    surplusText: String,
    staleText: String?,
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier.fillMaxWidth()) {
        Text(
            text = stringResource(R.string.stats_date_with_suffix, date.toHeroDate()),
            color = GT.colors.ink,
            style = GT.type.serifTitle,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Text(
            text = surplusText,
            modifier = Modifier.padding(top = 2.dp),
            color = GT.colors.ink2,
            style = GT.type.serifSection,
        )
        if (staleText != null) {
            Text(
                text = staleText,
                modifier = Modifier.padding(top = 4.dp),
                color = GT.colors.muted,
                style = GT.type.monoLabel,
            )
        }
    }
}

@Composable
private fun StatsKpiGrid(days: List<StatsDay>) {
    val availableDays = days.mapNotNull { it.totals }
    val divisor = max(availableDays.size, 1)
    val carbs = availableDays.sumOf { it.carbsG }
    val kcal = availableDays.sumOf { it.kcal }
    val protein = availableDays.sumOf { it.proteinG }
    val fat = availableDays.sumOf { it.fatG }
    val carbsAverage = carbs / divisor
    val kcalAverage = kcal / divisor
    val healthConnectKcalGoal = availableDays
        .mapNotNull { it.healthConnectTdeeKcal() }
        .takeIf { it.isNotEmpty() }
        ?.sum()
    Column {
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            GTKpiCard(
                label = stringResource(R.string.stats_kpi_carbs),
                value = formatGrams(carbs),
                sub = stringResource(R.string.stats_kpi_week_sub),
                progress = 0f,
                progressColor = GT.colors.accent.copy(alpha = 0.68f),
                extra = stringResource(R.string.stats_kpi_avg_sub, formatGrams(carbsAverage)),
                modifier = Modifier.weight(1f),
            )
            GTKpiCard(
                label = stringResource(R.string.stats_kpi_kcal),
                value = formatKcal(kcal),
                sub = healthConnectKcalGoal
                    ?.let { stringResource(R.string.today_kpi_goal_sub, formatKcal(it.toDouble())) }
                    ?: stringResource(R.string.stats_kpi_week_sub),
                progress = healthConnectKcalGoal?.let { progressOf(kcal, it) } ?: 0f,
                progressColor = GT.colors.good.copy(alpha = 0.65f),
                extra = stringResource(R.string.stats_kpi_avg_sub, formatKcal(kcalAverage)),
                modifier = Modifier.weight(1f),
            )
        }
        Row(
            modifier = Modifier.padding(top = 10.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            GTKpiCard(
                label = stringResource(R.string.stats_kpi_gi),
                value = "—",
                sub = stringResource(R.string.desktop_only_hint),
                progress = 0f,
                progressColor = GT.colors.info.copy(alpha = 0.65f),
                modifier = Modifier.weight(1f),
            )
            GTKpiCard(
                label = stringResource(R.string.stats_kpi_macro),
                value = stringResource(R.string.stats_kpi_macro_value, formatGrams(protein)),
                sub = stringResource(R.string.stats_kpi_week_sub),
                progress = 0f,
                progressColor = GT.colors.bad.copy(alpha = 0.55f),
                extra = stringResource(R.string.stats_kpi_macro_extra, formatGrams(fat), formatGrams(carbs)),
                modifier = Modifier.weight(1f),
            )
        }
    }
}

private fun DayTotals.healthConnectTdeeKcal(): Int? =
    tdeeKcal
        ?.takeIf { activitySource in HealthConnectTotalSources && it > 0.0 }
        ?.roundToLong()
        ?.toInt()

private fun progressOf(value: Double, goal: Int): Float =
    if (goal <= 0) 0f else (value / goal).toFloat().coerceIn(0f, 1f)

private val HealthConnectTotalSources = setOf(
    "health_connect_total",
    "health_connect_total_calories",
)

@Composable
private fun ChartCard(
    title: String,
    caption: String,
    bars: List<ChartBar>,
    color: Color,
    negativeColor: Color = color,
    signed: Boolean = false,
    valueText: (Double) -> String,
) {
    val hasValues = bars.any { it.value != null }
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .height(206.dp)
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .padding(14.dp),
    ) {
        GTKicker(text = title)
        Text(
            text = caption,
            modifier = Modifier.padding(top = 6.dp),
            color = GT.colors.muted,
            style = GT.type.sansLabel,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        if (!hasValues) {
            Text(
                text = stringResource(R.string.value_empty_label),
                modifier = Modifier.padding(top = 18.dp),
                color = GT.colors.muted,
                style = GT.type.sansBody,
            )
        } else {
            BarChart(
                bars = bars,
                color = color,
                negativeColor = negativeColor,
                signed = signed,
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .padding(top = 12.dp),
            )
            ChartLabels(
                bars = bars,
                signed = signed,
                valueText = valueText,
                modifier = Modifier.padding(top = 6.dp),
            )
        }
    }
}

@Composable
private fun BarChart(
    bars: List<ChartBar>,
    color: Color,
    negativeColor: Color,
    signed: Boolean,
    modifier: Modifier = Modifier,
) {
    val hairline = GT.colors.hairline2
    Canvas(modifier = modifier) {
        val values = bars.mapNotNull { it.value }
        if (values.isEmpty()) return@Canvas
        val rawMin = values.minOrNull() ?: return@Canvas
        val rawMax = values.maxOrNull() ?: return@Canvas
        var min = if (signed) minOf(0.0, rawMin) else 0.0
        var max = if (signed) maxOf(0.0, rawMax) else rawMax
        if (signed && min == 0.0 && max > 0.0) min = -max * 0.18
        if (signed && max == 0.0 && min < 0.0) max = abs(min) * 0.18
        if (max <= min) return@Canvas

        fun yFor(value: Double): Float =
            (size.height - ((value - min) / (max - min) * size.height)).toFloat()

        val gap = 6.dp.toPx()
        val barWidth = ((size.width - gap * (bars.size - 1)) / bars.size)
            .coerceAtLeast(1.dp.toPx())
        val baseline = if (signed) yFor(0.0).coerceIn(0f, size.height) else size.height
        drawLine(
            color = hairline,
            start = Offset(0f, baseline),
            end = Offset(size.width, baseline),
            strokeWidth = 1.dp.toPx(),
        )
        bars.forEachIndexed { index, bar ->
            val value = bar.value ?: return@forEachIndexed
            val valueY = yFor(value).coerceIn(0f, size.height)
            val top = if (value >= 0.0 || !signed) valueY else baseline
            val bottom = if (value >= 0.0 || !signed) baseline else valueY
            val barHeight = abs(bottom - top).coerceAtLeast(1.dp.toPx())
            drawRect(
                color = (if (signed && value < 0.0) negativeColor else color).copy(alpha = 0.68f),
                topLeft = Offset(index * (barWidth + gap), minOf(top, bottom)),
                size = Size(barWidth, barHeight),
            )
        }
    }
}

@Composable
private fun ChartLabels(
    bars: List<ChartBar>,
    signed: Boolean,
    valueText: (Double) -> String,
    modifier: Modifier = Modifier,
) {
    val empty = stringResource(R.string.value_empty)
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        bars.forEach { bar ->
            val value = bar.value
            Column(
                modifier = Modifier.weight(1f),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text(
                    text = bar.date.toChartDayLabel(),
                    color = GT.colors.muted,
                    style = GT.type.monoLabel,
                    maxLines = 1,
                    textAlign = TextAlign.Center,
                )
                Text(
                    text = value?.let(valueText) ?: empty,
                    color = when {
                        signed && value != null && value < 0.0 -> GT.colors.bad
                        signed && value != null && value > 0.0 -> GT.colors.warn
                        else -> GT.colors.ink2
                    },
                    style = GT.type.monoLabel,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    textAlign = TextAlign.Center,
                )
            }
        }
    }
}

private data class ChartBar(
    val date: LocalDate,
    val value: Double?,
)

private fun StatsDay.toChartBar(value: (DayTotals) -> Double?): ChartBar =
    ChartBar(date = date, value = totals?.let(value))

private fun LocalDate.toHeroDate(): String =
    toJavaLocalDate().format(DateTimeFormatter.ofPattern("d MMMM yyyy", Locale("ru")))

private fun LocalDate.toChartDayLabel(): String =
    toJavaLocalDate().format(DateTimeFormatter.ofPattern("EE", Locale("ru")))

private fun Instant.toStatsCacheStamp(): String =
    DateTimeFormatter.ofPattern("d MMM HH:mm", Locale("ru"))
        .withZone(ZoneId.systemDefault())
        .format(toJavaInstant())

private fun StatsPeriod.labelRes(): Int = when (this) {
    StatsPeriod.Week -> R.string.stats_period_week
    StatsPeriod.Fortnight -> R.string.stats_period_fortnight
    StatsPeriod.Month -> R.string.stats_period_month
}

private fun StatsPeriod.kickerRes(): Int = when (this) {
    StatsPeriod.Week -> R.string.stats_period_kicker_week
    StatsPeriod.Fortnight -> R.string.stats_period_kicker_fortnight
    StatsPeriod.Month -> R.string.stats_period_kicker_month
}

private fun StatsPeriod.toPeriodKicker(days: List<StatsDay>, label: String): String {
    val first = days.firstOrNull()?.date ?: return ""
    val last = days.lastOrNull()?.date ?: first
    val month = last.toJavaLocalDate().format(DateTimeFormatter.ofPattern("MMMM", Locale("ru")))
    return "$label · ${first.dayOfMonth}-${last.dayOfMonth} ${month.uppercase(Locale("ru"))}"
}
