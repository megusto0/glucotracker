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
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil3.compose.AsyncImage
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.DayTotals
import com.local.glucotracker.domain.model.StatsInsight
import com.local.glucotracker.domain.model.StatsOverview
import com.local.glucotracker.domain.model.StatsOverviewAnomaly
import com.local.glucotracker.domain.model.StatsOverviewDay
import com.local.glucotracker.domain.model.StatsOverviewHourlyBucket
import com.local.glucotracker.domain.model.StatsOverviewMacro
import com.local.glucotracker.domain.model.StatsOverviewTopProduct
import com.local.glucotracker.domain.model.StatsPeriod
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTKicker
import com.local.glucotracker.ui.glucose.LocalGlucoseSurfaces
import com.local.glucotracker.ui.format.formatGrams
import com.local.glucotracker.ui.format.formatKcal
import com.local.glucotracker.ui.format.formatPercent
import com.local.glucotracker.ui.format.truncateToLines
import java.time.DayOfWeek
import java.time.ZoneId
import java.time.format.DateTimeFormatter
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
    val state by viewModel.foodState.collectAsStateWithLifecycle()
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
    val accent = brandAccentColor ?: GT.colors.accent
    when (state) {
        StatsState.Loading -> Box(
            modifier = modifier
                .fillMaxSize()
                .background(GT.colors.bg),
        )

        is StatsState.Sparse -> SparseStats(
            state = state,
            accent = accent,
            onPeriodSelected = onPeriodSelected,
            modifier = modifier,
        )

        is StatsState.Charts -> NutritionStatsCharts(
            state = state,
            accent = accent,
            onPeriodSelected = onPeriodSelected,
            modifier = modifier,
        )
    }
}

@Composable
private fun SparseStats(
    state: StatsState.Sparse,
    accent: Color,
    onPeriodSelected: (StatsPeriod) -> Unit,
    modifier: Modifier = Modifier,
) {
    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg)
            .padding(horizontal = 18.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            GTKicker(
                text = stringResource(state.period.kickerRes()),
                modifier = Modifier.padding(top = 8.dp),
            )
            Text(
                text = stringResource(R.string.stats_empty_title),
                modifier = Modifier.padding(top = 6.dp),
                color = GT.colors.ink,
                style = GT.type.serifTitle,
            )
            Text(
                text = stringResource(R.string.stats_sparse),
                modifier = Modifier.padding(top = 8.dp),
                color = GT.colors.ink2,
                style = GT.type.sansBody,
            )
        }
        item {
            StatsPeriodSegmentedControl(
                selected = state.period,
                accent = accent,
                onSelected = onPeriodSelected,
            )
        }
    }
}

@Composable
private fun NutritionStatsCharts(
    state: StatsState.Charts,
    accent: Color,
    onPeriodSelected: (StatsPeriod) -> Unit,
    modifier: Modifier = Modifier,
) {
    val overview = state.overview
    val fallbackDays = state.days.toOverviewDays()
    val chartDays = overview?.daily?.takeIf { it.isNotEmpty() } ?: fallbackDays
    val averageKcal = overview?.averageKcal ?: fallbackDays.averageKcal()
    val spreadKcal = overview?.spreadKcal
    val insights = state.insights.displayNutritionInsights()
    val hourly = overview?.hourly ?: state.localHourly
    val topProducts = overview?.topProducts ?: state.localTopProducts
    val anomalies = overview?.anomalies ?: state.localAnomalies

    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg)
            .padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            StatsLeadStatement(
                overview = overview,
                averageKcal = averageKcal,
                modifier = Modifier.padding(top = 8.dp),
            )
            state.staleCacheAt?.let {
                Text(
                    text = stringResource(R.string.stats_stale_cache, it.toStatsCacheStamp()),
                    modifier = Modifier.padding(top = 4.dp),
                    color = GT.colors.muted,
                    style = GT.type.monoLabel,
                )
            }
        }
        item {
            StatsPeriodSegmentedControl(
                selected = state.period,
                accent = accent,
                onSelected = onPeriodSelected,
            )
        }
        if (insights.isNotEmpty()) {
            item {
                InsightStrip(insights = insights, accent = accent)
            }
        }
        item {
            StatCard(
                title = stringResource(R.string.stats_kcal_by_day_title),
                meta = kcalMeta(averageKcal, spreadKcal),
                contentDescription = stringResource(
                    R.string.stats_kcal_by_day_description,
                    averageKcal?.let(::formatKcal) ?: stringResource(R.string.value_empty),
                ),
            ) {
                KcalByDayOverviewChart(
                    days = chartDays,
                    today = state.date,
                    normalLow = overview?.normalKcalLow,
                    normalHigh = overview?.normalKcalHigh,
                    accent = accent,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(158.dp),
                )
            }
        }
        item {
            LocalGlucoseSurfaces.current.StatsTirSection(periodApiValue = state.period.apiValue)
        }
        item {
            StatCard(
                title = stringResource(R.string.stats_macro_stack_title),
                meta = null,
                contentDescription = stringResource(R.string.stats_macro_stack_description),
            ) {
                MacroAverageRows(macros = overview?.macros ?: state.days.toMacroRows())
            }
        }
        item {
            StatCard(
                title = stringResource(R.string.stats_time_histogram_title),
                meta = stringResource(R.string.stats_time_histogram_meta, state.period.days),
                contentDescription = stringResource(R.string.stats_time_histogram_description),
            ) {
                HourlyDensity(
                    buckets = hourly,
                    accent = accent,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(132.dp),
                )
            }
        }
        item {
            StatCard(
                title = stringResource(R.string.stats_top_products_title),
                meta = stringResource(R.string.stats_top_products_meta, state.period.days),
                contentDescription = stringResource(R.string.stats_top_products_title),
            ) {
                TopProductsList(products = topProducts)
            }
        }
        item {
            StatCard(
                title = stringResource(R.string.stats_anomalies_title),
                meta = stringResource(R.string.stats_anomalies_meta),
                contentDescription = stringResource(R.string.stats_anomalies_title),
            ) {
                AnomalyList(anomalies = anomalies)
            }
        }
        item {
            Spacer(Modifier.height(10.dp))
        }
    }
}

@Composable
private fun StatsLeadStatement(
    overview: StatsOverview?,
    averageKcal: Double?,
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier.fillMaxWidth()) {
        GTKicker(text = overview?.lead?.kicker ?: stringResource(R.string.stats_period_kicker_month))
        Text(
            text = if (averageKcal != null) {
                stringResource(
                    R.string.stats_lead_sentence,
                    formatKcal(averageKcal),
                    overview?.lead?.descriptor ?: stringResource(R.string.value_empty_label),
                )
            } else {
                stringResource(R.string.stats_empty_title)
            },
            modifier = Modifier.padding(top = 6.dp),
            color = GT.colors.ink,
            style = GT.type.serifTitle,
        )
        overview?.lead?.detail?.let { detail ->
            Text(
                text = detail,
                modifier = Modifier.padding(top = 8.dp),
                color = GT.colors.ink2,
                style = GT.type.sansBody,
                maxLines = 3,
                overflow = TextOverflow.Ellipsis,
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
            .background(GT.colors.hairline, RoundedCornerShape(10.dp))
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
                        shape = RoundedCornerShape(8.dp),
                    )
                    .clickable { onSelected(period) },
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    text = stringResource(period.labelRes()),
                    color = if (active) GT.colors.ink else GT.colors.muted,
                    style = GT.type.sansLabel,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
private fun InsightStrip(
    insights: List<StatsInsight>,
    accent: Color,
    modifier: Modifier = Modifier,
) {
    LazyRow(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        items(insights.take(3), key = { it.id }) { insight ->
            Column(
                modifier = Modifier
                    .width(244.dp)
                    .background(GT.colors.surface, RoundedCornerShape(10.dp))
                    .border(GT.space.hairline, GT.colors.hairline2, RoundedCornerShape(10.dp))
                    .padding(12.dp),
            ) {
                Text(
                    text = stringResource(R.string.stats_insight_kicker),
                    color = accent,
                    style = GT.type.kicker,
                )
                Text(
                    text = truncateToLines(insight.text, maxLines = 3, charsPerLine = 34),
                    modifier = Modifier.padding(top = 5.dp),
                    color = GT.colors.ink2,
                    style = GT.type.sansBody,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
private fun StatCard(
    title: String,
    meta: String?,
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
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.Top,
        ) {
            GTKicker(text = title, modifier = Modifier.weight(1f))
            if (meta != null) {
                Text(
                    text = meta,
                    color = GT.colors.ink2,
                    style = GT.type.monoLabel,
                    textAlign = TextAlign.End,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        Spacer(Modifier.height(12.dp))
        content()
    }
}

@Composable
private fun KcalByDayOverviewChart(
    days: List<StatsOverviewDay>,
    today: LocalDate,
    normalLow: Double?,
    normalHigh: Double?,
    accent: Color,
    modifier: Modifier = Modifier,
) {
    val values = days.mapNotNull { it.kcal }
    if (days.isEmpty() || values.isEmpty()) {
        Text(
            text = stringResource(R.string.value_empty_label),
            color = GT.colors.muted,
            style = GT.type.sansBody,
        )
        return
    }
    val graphite = GT.colors.ink.copy(alpha = 0.72f)
    val weekend = GT.colors.ink.copy(alpha = 0.32f)
    val hairline = GT.colors.hairline
    val hairlineWidth = GT.space.hairline
    val rangeColor = GT.colors.warn
    val maxValue = listOfNotNull(values.maxOrNull(), normalHigh)
        .maxOrNull()
        ?.coerceAtLeast(1.0)
        ?: 1.0
    Column(modifier = modifier) {
        Canvas(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
        ) {
            val chartHeight = size.height
            val gap = 2.dp.toPx()
            val barWidth = ((size.width - gap * (days.size - 1)) / days.size)
                .coerceAtLeast(2.dp.toPx())
            if (normalLow != null && normalHigh != null && normalHigh > normalLow) {
                val top = chartHeight - (normalHigh / maxValue * chartHeight).toFloat()
                val bottom = chartHeight - (normalLow / maxValue * chartHeight).toFloat()
                drawRect(
                    color = rangeColor.copy(alpha = 0.08f),
                    topLeft = Offset(0f, top.coerceIn(0f, chartHeight)),
                    size = Size(size.width, (bottom - top).coerceAtLeast(1.dp.toPx())),
                )
                val dash = PathEffect.dashPathEffect(
                    floatArrayOf(4.dp.toPx(), 4.dp.toPx()),
                )
                listOf(top, bottom).forEach { y ->
                    drawLine(
                        color = rangeColor.copy(alpha = 0.42f),
                        start = Offset(0f, y.coerceIn(0f, chartHeight)),
                        end = Offset(size.width, y.coerceIn(0f, chartHeight)),
                        strokeWidth = hairlineWidth.toPx(),
                        pathEffect = dash,
                    )
                }
            }
            days.forEachIndexed { index, day ->
                if (day.date.isMonday()) {
                    val x = index * (barWidth + gap)
                    drawLine(
                        color = hairline,
                        start = Offset(x, 0f),
                        end = Offset(x, chartHeight),
                        strokeWidth = hairlineWidth.toPx(),
                    )
                }
                val kcal = day.kcal ?: return@forEachIndexed
                val barHeight = (kcal / maxValue * chartHeight)
                    .toFloat()
                    .coerceAtLeast(2.dp.toPx())
                val color = when {
                    day.date == today -> accent
                    day.date.isWeekend() -> weekend
                    else -> graphite
                }
                drawRoundRect(
                    color = color,
                    topLeft = Offset(index * (barWidth + gap), chartHeight - barHeight),
                    size = Size(barWidth, barHeight),
                    cornerRadius = CornerRadius(1.5.dp.toPx(), 1.5.dp.toPx()),
                )
            }
        }
        Text(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 2.dp),
            text = stringResource(
                R.string.stats_kcal_period_label,
                days.first().date.toStatsShortDate(),
                days.last().date.toStatsShortDate(),
            ),
            color = GT.colors.muted,
            style = GT.type.monoLabel,
            maxLines = 1,
        )
        Row(
            modifier = Modifier.padding(top = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            KcalLegendItem(color = graphite, label = stringResource(R.string.stats_kcal_legend_weekday))
            KcalLegendItem(color = weekend, label = stringResource(R.string.stats_kcal_legend_weekend))
            KcalLegendItem(color = accent, label = stringResource(R.string.stats_kcal_legend_today))
            KcalLegendItem(color = rangeColor, label = stringResource(R.string.stats_kcal_range_label))
        }
    }
}

@Composable
private fun KcalLegendItem(
    color: Color,
    label: String,
) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Box(
            modifier = Modifier
                .size(width = 10.dp, height = 6.dp)
                .background(color, GT.shapes.tag),
        )
        Text(
            text = label,
            color = GT.colors.muted,
            style = GT.type.monoLabel,
            maxLines = 1,
        )
    }
}

@Composable
private fun MacroAverageRows(
    macros: List<StatsOverviewMacro>,
    modifier: Modifier = Modifier,
) {
    val ordered = listOf("protein", "fat", "carbs").mapNotNull { key ->
        macros.firstOrNull { it.key == key }
    }
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        ordered.forEach { macro ->
            MacroRow(macro = macro)
        }
    }
}

@Composable
private fun MacroRow(macro: StatsOverviewMacro) {
    val color = macroColor(macro.key)
    val barTrackColor = GT.colors.hairline
    val targetColor = GT.colors.ink2
    val percent = macro.percent?.coerceIn(0.0, 1.0) ?: 0.0
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Column(modifier = Modifier.width(92.dp)) {
            Text(
                text = macro.label,
                color = GT.colors.ink,
                style = GT.type.sansLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                text = macro.grams?.let { formatGrams(it) } ?: stringResource(R.string.value_empty),
                color = GT.colors.muted,
                style = GT.type.monoLabel,
                maxLines = 1,
            )
        }
        Canvas(
            modifier = Modifier
                .weight(1f)
                .height(22.dp),
        ) {
            val barTop = size.height / 2 - 3.dp.toPx()
            drawRoundRect(
                color = barTrackColor,
                topLeft = Offset(0f, barTop),
                size = Size(size.width, 6.dp.toPx()),
                cornerRadius = CornerRadius(3.dp.toPx(), 3.dp.toPx()),
            )
            drawRoundRect(
                color = color,
                topLeft = Offset(0f, barTop),
                size = Size(size.width * percent.toFloat(), 6.dp.toPx()),
                cornerRadius = CornerRadius(3.dp.toPx(), 3.dp.toPx()),
            )
            macro.targetPercent?.coerceIn(0.0, 1.0)?.let { target ->
                val x = size.width * target.toFloat()
                drawLine(
                    color = targetColor,
                    start = Offset(x, barTop - 3.dp.toPx()),
                    end = Offset(x, barTop + 9.dp.toPx()),
                    strokeWidth = 1.5.dp.toPx(),
                )
            }
        }
        Text(
            text = macro.percent?.let { formatPercent(it * 100) } ?: stringResource(R.string.value_empty),
            color = GT.colors.ink,
            style = GT.type.monoLabel,
            textAlign = TextAlign.End,
            modifier = Modifier.width(40.dp),
            maxLines = 1,
        )
    }
}

@Composable
private fun HourlyDensity(
    buckets: List<StatsOverviewHourlyBucket>,
    accent: Color,
    modifier: Modifier = Modifier,
) {
    val normalized = (0..23).map { hour ->
        buckets.firstOrNull { it.hour == hour } ?: StatsOverviewHourlyBucket(hour, 0, 0.0)
    }
    val hasData = normalized.any { it.mealCount > 0 }
    val hairline = GT.colors.hairline
    val hairlineWidth = GT.space.hairline
    val areaColor = GT.colors.ink.copy(alpha = 0.08f)
    val lineColor = GT.colors.ink
    if (!hasData) {
        Text(
            text = stringResource(R.string.value_empty_label),
            color = GT.colors.muted,
            style = GT.type.sansBody,
        )
        return
    }
    Column(modifier = modifier) {
        Canvas(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
        ) {
            val baseline = size.height - 12.dp.toPx()
            val topPad = 4.dp.toPx()
            val step = size.width / 23f
            val points = normalized.map { bucket ->
                val x = bucket.hour * step
                val y = baseline - (baseline - topPad) * bucket.share.toFloat().coerceIn(0f, 1f)
                Offset(x, y)
            }
            drawLine(
                color = hairline,
                start = Offset(0f, baseline),
                end = Offset(size.width, baseline),
                strokeWidth = hairlineWidth.toPx(),
            )
            listOf(6, 12, 18).forEach { hour ->
                val x = hour * step
                drawLine(
                    color = hairline,
                    start = Offset(x, topPad),
                    end = Offset(x, baseline),
                    strokeWidth = hairlineWidth.toPx(),
                    pathEffect = PathEffect.dashPathEffect(
                        floatArrayOf(3.dp.toPx(), 4.dp.toPx()),
                    ),
                )
            }
            val area = Path().apply {
                moveTo(0f, baseline)
                points.forEachIndexed { index, point ->
                    if (index == 0) lineTo(point.x, point.y) else lineTo(point.x, point.y)
                }
                lineTo(size.width, baseline)
                close()
            }
            drawPath(area, color = areaColor)
            val line = Path().apply {
                points.forEachIndexed { index, point ->
                    if (index == 0) moveTo(point.x, point.y) else lineTo(point.x, point.y)
                }
            }
            drawPath(
                path = line,
                color = lineColor,
                style = Stroke(width = 1.4.dp.toPx()),
            )
            normalized.peaks().forEach { bucket ->
                val x = bucket.hour * step
                val y = baseline - (baseline - topPad) * bucket.share.toFloat()
                drawCircle(
                    color = accent,
                    radius = 3.dp.toPx(),
                    center = Offset(x, y),
                )
            }
        }
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            listOf("00", "06", "12", "18", "24").forEach { label ->
                Text(text = label, color = GT.colors.muted, style = GT.type.monoLabel)
            }
        }
        val peaks = normalized.peaks()
        Column(
            modifier = Modifier.padding(top = 8.dp),
            verticalArrangement = Arrangement.spacedBy(3.dp),
        ) {
            Text(
                text = stringResource(R.string.stats_hour_peaks_label),
                color = GT.colors.muted,
                style = GT.type.sansLabel,
                maxLines = 1,
            )
            peaks.forEach { peak ->
                Text(
                    text = stringResource(
                        R.string.stats_hour_peak,
                        "${peak.hour.toString().padStart(2, '0')}:00",
                        stringResource(peak.hour.roleLabelRes()),
                        peak.mealCount,
                    ),
                    color = GT.colors.ink2,
                    style = GT.type.monoLabel,
                    maxLines = 1,
                )
            }
        }
    }
}

@Composable
private fun TopProductsList(products: List<StatsOverviewTopProduct>) {
    if (products.isEmpty()) {
        Text(
            text = stringResource(R.string.value_empty_label),
            color = GT.colors.muted,
            style = GT.type.sansBody,
        )
        return
    }
    Column(modifier = Modifier.fillMaxWidth()) {
        products.forEachIndexed { index, product ->
            if (index > 0) HairlineSpacer()
            TopProductRow(product = product)
        }
    }
}

@Composable
private fun TopProductRow(product: StatsOverviewTopProduct) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text(
            text = product.rank.toString().padStart(2, '0'),
            color = GT.colors.muted,
            style = GT.type.monoLabel,
            modifier = Modifier.width(24.dp),
        )
        ProductThumb(product.imageUrl)
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = product.name,
                color = GT.colors.ink,
                style = GT.type.sansLabel,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                text = stringResource(
                    R.string.stats_top_product_meta,
                    product.kcalPer100g.formatNullableKcal(),
                    product.proteinPer100g.formatNullableGrams(),
                    product.fatPer100g.formatNullableGrams(),
                    product.carbsPer100g.formatNullableGrams(),
                ),
                modifier = Modifier.padding(top = 2.dp),
                color = GT.colors.muted,
                style = GT.type.monoLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        Text(
            text = stringResource(R.string.stats_top_product_count, product.count),
            color = GT.colors.ink2,
            style = GT.type.monoLabel,
            textAlign = TextAlign.End,
            maxLines = 1,
        )
    }
}

@Composable
private fun ProductThumb(imageUrl: String?) {
    if (imageUrl == null) {
        Box(
            modifier = Modifier
                .size(28.dp)
                .background(GT.colors.hairline, RoundedCornerShape(6.dp))
                .border(GT.space.hairline, GT.colors.hairline2, RoundedCornerShape(6.dp)),
        )
        return
    }
    AsyncImage(
        model = imageUrl,
        contentDescription = null,
        contentScale = ContentScale.Crop,
        modifier = Modifier
            .size(28.dp)
            .clip(RoundedCornerShape(6.dp)),
    )
}

@Composable
private fun AnomalyList(anomalies: List<StatsOverviewAnomaly>) {
    if (anomalies.isEmpty()) {
        Text(
            text = stringResource(R.string.stats_anomalies_empty),
            color = GT.colors.muted,
            style = GT.type.sansBody,
        )
        return
    }
    Column(modifier = Modifier.fillMaxWidth()) {
        anomalies.forEachIndexed { index, anomaly ->
            if (index > 0) HairlineSpacer()
            AnomalyRow(anomaly = anomaly)
        }
    }
}

@Composable
private fun AnomalyRow(anomaly: StatsOverviewAnomaly) {
    val up = anomaly.direction == "up"
    val reason = anomaly.reasonText()
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Box(
            modifier = Modifier
                .size(24.dp)
                .background(if (up) GT.colors.warn else GT.colors.info, RoundedCornerShape(4.dp)),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = if (up) "↑" else "↓",
                color = GT.colors.surface2,
                style = GT.type.monoLabel,
            )
        }
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = anomaly.date.toAnomalyDate(),
                color = GT.colors.ink,
                style = GT.type.sansLabel,
                maxLines = 1,
            )
            Text(
                text = reason,
                modifier = Modifier.padding(top = 1.dp),
                color = GT.colors.muted,
                style = GT.type.monoLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(
                text = formatKcal(anomaly.kcal),
                color = GT.colors.ink,
                style = GT.type.monoLabel,
                maxLines = 1,
            )
            Text(
                text = anomaly.deltaKcal.formatDeltaKcal(),
                color = if (up) GT.colors.warn else GT.colors.info,
                style = GT.type.monoLabel,
                maxLines = 1,
            )
        }
    }
}

@Composable
private fun StatsOverviewAnomaly.reasonText(): String =
    when (reason) {
        LOCAL_REASON_MORE_MEALS -> stringResource(R.string.stats_anomaly_reason_more_meals)
        LOCAL_REASON_LESS_MEALS -> stringResource(R.string.stats_anomaly_reason_less_meals)
        LOCAL_REASON_NO_MORNING -> stringResource(R.string.stats_anomaly_reason_no_morning)
        LOCAL_REASON_RHYTHM -> stringResource(R.string.stats_anomaly_reason_rhythm)
        else -> reason
    }

@Composable
private fun HairlineSpacer() {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(GT.space.hairline)
            .background(GT.colors.hairline),
    )
}

@Composable
private fun macroColor(key: String): Color = when (key) {
    "protein" -> GT.colors.info
    "fat" -> GT.colors.warn
    "carbs" -> GT.colors.accent
    else -> GT.colors.ink2
}

@Composable
private fun kcalMeta(averageKcal: Double?, spreadKcal: Double?): String? {
    if (averageKcal == null || spreadKcal == null) return null
    return stringResource(
        R.string.stats_kcal_by_day_meta,
        formatKcal(averageKcal),
        formatKcal(spreadKcal),
    )
}

private fun List<StatsDay>.toOverviewDays(): List<StatsOverviewDay> =
    map { day ->
        StatsOverviewDay(
            date = day.date,
            kcal = day.totals?.kcal?.takeIf { day.totals.mealCount > 0 },
            mealCount = day.totals?.mealCount ?: 0,
        )
    }

private fun List<StatsOverviewDay>.averageKcal(): Double? {
    val values = mapNotNull { day -> day.kcal?.takeIf { day.mealCount > 0 } }
    return values.takeIf { it.isNotEmpty() }?.average()
}

@Composable
private fun List<StatsDay>.toMacroRows(): List<StatsOverviewMacro> {
    val totals = mapNotNull { it.totals }.filter { it.mealCount > 0 }
    if (totals.isEmpty()) {
        return listOf(
            StatsOverviewMacro("protein", stringResource(R.string.today_kpi_protein), null, null, null),
            StatsOverviewMacro("fat", stringResource(R.string.today_kpi_fat), null, null, null),
            StatsOverviewMacro("carbs", stringResource(R.string.today_kpi_carbs), null, null, null),
        )
    }
    val divisor = totals.size
    val protein = totals.sumOf(DayTotals::proteinG) / divisor
    val fat = totals.sumOf(DayTotals::fatG) / divisor
    val carbs = totals.sumOf(DayTotals::carbsG) / divisor
    val proteinKcal = protein * 4
    val fatKcal = fat * 9
    val carbsKcal = carbs * 4
    val total = max(1.0, proteinKcal + fatKcal + carbsKcal)
    return listOf(
        StatsOverviewMacro(
            "protein",
            stringResource(R.string.today_kpi_protein),
            protein,
            proteinKcal / total,
            null,
        ),
        StatsOverviewMacro("fat", stringResource(R.string.today_kpi_fat), fat, fatKcal / total, null),
        StatsOverviewMacro(
            "carbs",
            stringResource(R.string.today_kpi_carbs),
            carbs,
            carbsKcal / total,
            null,
        ),
    )
}

private fun List<StatsInsight>.displayNutritionInsights(): List<StatsInsight> {
    val blockedKinds = setOf(
        "consistent",
        "weekday_pattern_sweet",
        "meal_predictability",
        "evening_lows",
        "hypo_recovery_pattern",
        "late_meal_glucose_footprint",
    )
    return filterNot { it.kind in blockedKinds }
        .distinctBy { it.text.trim().lowercase(Locale.ROOT) }
        .take(3)
}

private fun List<StatsOverviewHourlyBucket>.peaks(): List<StatsOverviewHourlyBucket> =
    filter { it.mealCount > 0 }
        .sortedWith(compareByDescending<StatsOverviewHourlyBucket> { it.mealCount }.thenBy { it.hour })
        .take(4)
        .sortedBy { it.hour }

private fun Int.roleLabelRes(): Int = when (this) {
    in 5..10 -> R.string.stats_hour_breakfast
    in 11..16 -> R.string.stats_hour_lunch
    in 17..21 -> R.string.stats_hour_dinner
    else -> R.string.stats_hour_tail
}

private fun LocalDate.isWeekend(): Boolean {
    val day = toJavaLocalDate().dayOfWeek
    return day == DayOfWeek.SATURDAY || day == DayOfWeek.SUNDAY
}

private fun LocalDate.isMonday(): Boolean =
    toJavaLocalDate().dayOfWeek == DayOfWeek.MONDAY

private fun LocalDate.toAnomalyDate(): String =
    toJavaLocalDate().format(DateTimeFormatter.ofPattern("EEEE, d MMMM", Locale("ru")))

private fun LocalDate.toStatsShortDate(): String =
    toJavaLocalDate().format(DateTimeFormatter.ofPattern("d MMM", Locale("ru")))

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

@Composable
private fun Double?.formatNullableKcal(): String =
    this?.let { formatKcal(it) } ?: stringResource(R.string.value_empty)

@Composable
private fun Double?.formatNullableGrams(): String =
    this?.let { formatGrams(it) } ?: stringResource(R.string.value_empty)

private fun Double.formatDeltaKcal(): String {
    val rounded = roundToLong()
    val value = formatKcal(abs(rounded))
    return if (rounded >= 0) "+$value" else "−$value"
}
