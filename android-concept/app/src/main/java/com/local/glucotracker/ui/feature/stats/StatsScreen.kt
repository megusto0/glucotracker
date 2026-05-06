package com.local.glucotracker.ui.feature.stats

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.DayTotals
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHintBox
import com.local.glucotracker.ui.design.primitives.GTKicker
import com.local.glucotracker.ui.design.primitives.GTKpiCard
import com.local.glucotracker.ui.format.formatGrams
import com.local.glucotracker.ui.format.formatKcal
import java.time.format.DateTimeFormatter
import java.time.ZoneId
import java.util.Locale
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.toJavaInstant
import kotlinx.datetime.toJavaLocalDate

@Composable
fun StatsRoute(
    viewModel: StatsViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsState()
    StatsScreen(state = state)
}

@Composable
fun StatsScreen(
    state: StatsState,
    modifier: Modifier = Modifier,
) {
    when (state) {
        StatsState.Loading -> Box(
            modifier = modifier
                .fillMaxSize()
                .background(GT.colors.bg),
        )
        is StatsState.Sparse -> SparseStats(state = state, modifier = modifier)
        is StatsState.Charts -> StatsCharts(state = state, modifier = modifier)
    }
}

@Composable
private fun SparseStats(
    state: StatsState.Sparse,
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
            StatsHero(
                date = state.date,
                surplusText = stringResource(R.string.stats_surplus_unknown),
                staleText = null,
                modifier = Modifier.padding(top = 6.dp),
            )
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
                surplusText = stringResource(R.string.stats_surplus_unknown),
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
                values = days.map { it.carbsG },
                color = GT.colors.accent,
            )
        }
        item {
            ChartCard(
                title = stringResource(R.string.stats_chart_balance),
                values = days.map { it.kcal },
                color = GT.colors.bad,
            )
        }
        item {
            ChartCard(
                title = stringResource(R.string.stats_chart_tir),
                values = emptyList(),
                color = GT.colors.good,
            )
        }
        item {
            DaypartGrid()
        }
        item {
            GTHintBox(text = stringResource(R.string.stats_heatmap_hint))
        }
        item {
            Spacer(Modifier.height(10.dp))
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
private fun StatsKpiGrid(days: List<DayTotals>) {
    val carbs = days.sumOf { it.carbsG }
    val kcal = days.sumOf { it.kcal }
    Column {
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            GTKpiCard(
                label = stringResource(R.string.stats_kpi_carbs),
                value = formatGrams(carbs),
                sub = stringResource(R.string.today_kpi_day_sub),
                progress = 0f,
                progressColor = GT.colors.accent.copy(alpha = 0.68f),
                modifier = Modifier.weight(1f),
            )
            GTKpiCard(
                label = stringResource(R.string.stats_kpi_kcal),
                value = formatKcal(kcal),
                sub = stringResource(R.string.today_kpi_day_sub),
                progress = 0f,
                progressColor = GT.colors.good.copy(alpha = 0.65f),
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
                value = "—",
                sub = stringResource(R.string.today_kpi_day_sub),
                progress = 0f,
                progressColor = GT.colors.bad.copy(alpha = 0.55f),
                modifier = Modifier.weight(1f),
            )
        }
    }
}

@Composable
private fun ChartCard(
    title: String,
    values: List<Double>,
    color: Color,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .height(148.dp)
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .padding(14.dp),
    ) {
        GTKicker(text = title)
        if (values.isEmpty()) {
            Text(
                text = stringResource(R.string.desktop_only_hint),
                modifier = Modifier.padding(top = 18.dp),
                color = GT.colors.muted,
                style = GT.type.sansBody,
            )
        } else {
            BarChart(
                values = values,
                color = color,
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .padding(top = 14.dp),
            )
        }
    }
}

@Composable
private fun BarChart(
    values: List<Double>,
    color: Color,
    modifier: Modifier = Modifier,
) {
    Canvas(modifier = modifier) {
        val max = values.maxOrNull()?.takeIf { it > 0.0 } ?: return@Canvas
        val gap = 6.dp.toPx()
        val barWidth = (size.width - gap * (values.size - 1)) / values.size
        values.forEachIndexed { index, value ->
            val barHeight = (value / max * size.height).toFloat().coerceAtLeast(1.dp.toPx())
            drawRect(
                color = color.copy(alpha = 0.62f),
                topLeft = Offset(index * (barWidth + gap), size.height - barHeight),
                size = Size(barWidth, barHeight),
            )
        }
    }
}

@Composable
private fun DaypartGrid() {
    Column(
        modifier = Modifier
            .fillMaxWidth()
    ) {
        GTKicker(text = stringResource(R.string.stats_chart_dayparts))
        Row(
            modifier = Modifier.padding(top = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            repeat(2) {
                GTHintBox(
                    text = stringResource(R.string.desktop_only_hint),
                    modifier = Modifier.weight(1f),
                )
            }
        }
        Row(
            modifier = Modifier.padding(top = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            repeat(2) {
                GTHintBox(
                    text = stringResource(R.string.desktop_only_hint),
                    modifier = Modifier.weight(1f),
                )
            }
        }
        Row(
            modifier = Modifier.padding(top = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            repeat(2) {
                GTHintBox(
                    text = stringResource(R.string.desktop_only_hint),
                    modifier = Modifier.weight(1f),
                )
            }
        }
    }
}

private fun LocalDate.toHeroDate(): String =
    toJavaLocalDate().format(DateTimeFormatter.ofPattern("d MMMM yyyy", Locale("ru")))

private fun Instant.toStatsCacheStamp(): String =
    DateTimeFormatter.ofPattern("d MMM HH:mm", Locale("ru"))
        .withZone(ZoneId.systemDefault())
        .format(toJavaInstant())
