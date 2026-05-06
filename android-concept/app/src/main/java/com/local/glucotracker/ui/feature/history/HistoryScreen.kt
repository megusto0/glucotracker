package com.local.glucotracker.ui.feature.history

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.HistoryFilter
import com.local.glucotracker.domain.model.HistoryStatusFilter
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTHintBox
import com.local.glucotracker.ui.design.primitives.GTIconButton
import com.local.glucotracker.ui.design.primitives.GTMealRow
import com.local.glucotracker.ui.design.primitives.GTMealRowStatus
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.design.primitives.GTStatusTone
import com.local.glucotracker.ui.design.primitives.GTTag
import com.local.glucotracker.ui.format.formatGrams
import com.local.glucotracker.ui.format.formatKcal
import com.local.glucotracker.ui.format.formatSignedKcal
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.roundToLong
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toJavaLocalDate
import kotlinx.datetime.toLocalDateTime

@Composable
fun HistoryRoute(
    onOpenRecord: (String) -> Unit,
    viewModel: HistoryViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsState()
    HistoryScreen(
        state = state,
        onOpenRecord = onOpenRecord,
        onToggleFilter = viewModel::toggleFilter,
        onStatusChange = viewModel::setStatus,
        onSearchChange = viewModel::setSearch,
        onLoadMore = viewModel::loadMore,
    )
}

@Composable
fun HistoryScreen(
    state: HistoryScreenState,
    onOpenRecord: (String) -> Unit,
    onToggleFilter: (HistoryFilter) -> Unit,
    onStatusChange: (HistoryStatusFilter) -> Unit,
    onSearchChange: (String) -> Unit,
    onLoadMore: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var statusSheetVisible by remember { mutableStateOf(false) }
    val listState = rememberLazyListState()
    val shouldLoadMore by remember(state.showNeedsNetworkHint) {
        derivedStateOf {
            val lastVisible = listState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0
            val total = listState.layoutInfo.totalItemsCount
            total > 0 && lastVisible >= total - 4 && !state.showNeedsNetworkHint
        }
    }

    LaunchedEffect(shouldLoadMore) {
        if (shouldLoadMore) onLoadMore()
    }

    LazyColumn(
        state = listState,
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            HistoryHeader(
                state = state,
                onToggleFilter = onToggleFilter,
                onSearchChange = onSearchChange,
                onStatusClick = { statusSheetVisible = true },
                modifier = Modifier.padding(horizontal = 18.dp, vertical = 10.dp),
            )
        }
        if (state.days.isEmpty() && !state.isRefreshing) {
            item {
                GTHintBox(
                    text = stringResource(R.string.history_empty),
                    modifier = Modifier.padding(horizontal = 18.dp),
                )
            }
        }
        items(
            items = state.days,
            key = { day -> day.date.toString() },
        ) { day ->
            HistoryDaySection(
                day = day,
                onOpenRecord = onOpenRecord,
                modifier = Modifier.padding(horizontal = 18.dp),
            )
        }
        if (state.showNeedsNetworkHint) {
            item {
                GTHintBox(
                    text = stringResource(R.string.history_old_cache_hint),
                    modifier = Modifier.padding(horizontal = 18.dp),
                )
            }
        }
        item {
            Spacer(Modifier.height(10.dp))
        }
    }

    if (statusSheetVisible) {
        StatusSheet(
            selected = state.status,
            onSelect = { status ->
                onStatusChange(status)
                statusSheetVisible = false
            },
            onDismiss = { statusSheetVisible = false },
        )
    }
}

@Composable
private fun HistoryHeader(
    state: HistoryScreenState,
    onToggleFilter: (HistoryFilter) -> Unit,
    onSearchChange: (String) -> Unit,
    onStatusClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = stringResource(R.string.history_title),
                color = GT.colors.ink,
                style = GT.type.serifTitle,
                maxLines = 1,
            )
            Spacer(Modifier.weight(1f))
            val statusDescription = stringResource(R.string.history_status_content_description)
            GTIconButton(
                onClick = onStatusClick,
                modifier = Modifier.semantics { contentDescription = statusDescription },
            ) {
                FilterGlyph()
            }
        }
        SearchField(
            value = state.search,
            onValueChange = onSearchChange,
            modifier = Modifier.padding(top = 12.dp),
        )
        Row(
            modifier = Modifier
                .padding(top = 10.dp)
                .horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            FilterChip(
                label = stringResource(R.string.history_filter_cgm),
                active = HistoryFilter.WithCgm in state.filters,
                onClick = { onToggleFilter(HistoryFilter.WithCgm) },
            )
            FilterChip(
                label = stringResource(R.string.history_filter_insulin),
                active = HistoryFilter.WithInsulin in state.filters,
                onClick = { onToggleFilter(HistoryFilter.WithInsulin) },
            )
            FilterChip(
                label = stringResource(R.string.history_filter_low_confidence),
                active = HistoryFilter.LowConfidence in state.filters,
                onClick = { onToggleFilter(HistoryFilter.LowConfidence) },
            )
            FilterChip(
                label = stringResource(R.string.history_filter_photo),
                active = HistoryFilter.PhotoOnly in state.filters,
                onClick = { onToggleFilter(HistoryFilter.PhotoOnly) },
            )
            FilterChip(
                label = stringResource(R.string.history_status_button, state.status.label()),
                active = state.status != HistoryStatusFilter.Active,
                onClick = onStatusClick,
            )
        }
        GTHairlineDivider(modifier = Modifier.padding(top = 12.dp))
    }
}

@Composable
private fun SearchField(
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val description = stringResource(R.string.history_search_content_description)
    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(44.dp)
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .padding(horizontal = 12.dp)
            .semantics { contentDescription = description },
        contentAlignment = Alignment.CenterStart,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            SearchGlyph(modifier = Modifier.size(16.dp))
            Spacer(Modifier.width(8.dp))
            Box(modifier = Modifier.weight(1f)) {
                if (value.isBlank()) {
                    Text(
                        text = stringResource(R.string.history_search_hint),
                        color = GT.colors.muted,
                        style = GT.type.sansBody,
                        maxLines = 1,
                    )
                }
                BasicTextField(
                    value = value,
                    onValueChange = onValueChange,
                    textStyle = GT.type.sansBody.copy(color = GT.colors.ink),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
    }
}

@Composable
private fun FilterChip(
    label: String,
    active: Boolean,
    onClick: () -> Unit,
) {
    Box(
        modifier = Modifier
            .heightIn(min = GT.space.touch)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        GTTag(text = label, active = active)
    }
}

@Composable
private fun HistoryDaySection(
    day: HistoryDayUi,
    onOpenRecord: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.Top) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = dayTitle(day.date),
                    color = GT.colors.ink,
                    style = GT.type.serifSection,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = day.summaryText(),
                    modifier = Modifier.padding(top = 3.dp),
                    color = GT.colors.muted,
                    style = GT.type.monoLabel,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Sparkline(
                points = day.sparkline,
                color = GT.colors.info,
                modifier = Modifier
                    .padding(start = 10.dp, top = 4.dp)
                    .size(width = 72.dp, height = 28.dp),
            )
        }
        Column(
            modifier = Modifier
                .padding(top = 8.dp)
                .fillMaxWidth()
                .background(GT.colors.surface, GT.shapes.card)
                .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card),
        ) {
            day.rows.forEachIndexed { index, row ->
                HistoryMealRow(
                    row = row,
                    onOpenRecord = onOpenRecord,
                )
                if (index < day.rows.lastIndex) {
                    GTHairlineDivider(modifier = Modifier.padding(horizontal = 14.dp))
                }
            }
        }
    }
}

@Composable
private fun HistoryMealRow(
    row: HistoryMealRowUi,
    onOpenRecord: (String) -> Unit,
) {
    val clickId = row.recordId ?: row.outboxId
    val clickModifier = clickId?.let { id ->
        Modifier.clickable { onOpenRecord(id) }
    } ?: Modifier
    Box(modifier = clickModifier) {
        GTMealRow(
            time = row.eatenAt.timeText(),
            photo = row.photo,
            name = row.title ?: fallbackTitle(row),
            meta = stringResource(
                R.string.today_meal_meta,
                sourceLabel(row.source),
                statusLabel(row.status),
            ),
            primaryRight = row.totalCarbsG?.let { stringResource(R.string.today_right_carbs, formatGrams(it)) }
                ?: stringResource(R.string.glucose_value_empty),
            secondaryRight = row.totalKcal?.let { stringResource(R.string.today_right_kcal, formatKcal(it)) }
                ?: stringResource(R.string.glucose_value_empty),
            status = row.status.toMealRowStatus(row.kind),
            muted = row.kind == HistoryMealRowKind.Pending,
        )
    }
}

@Composable
private fun HistoryDayUi.summaryText(): String {
    val balance = totals?.netBalanceKcal
        ?.roundToLong()
        ?.let(::formatSignedKcal)
        ?: stringResource(R.string.history_balance_empty)
    return stringResource(
        R.string.history_day_summary,
        totals?.mealCount ?: rows.count { it.kind == HistoryMealRowKind.Accepted },
        formatGrams(totals?.carbsG ?: 0.0),
        formatKcal(totals?.kcal ?: 0.0),
        balance,
    )
}

@Composable
private fun fallbackTitle(row: HistoryMealRowUi): String =
    if (row.source == HistoryMealSource.Photo && row.kind == HistoryMealRowKind.Pending) {
        stringResource(R.string.today_pending_photo_title)
    } else {
        stringResource(R.string.today_meal_fallback)
    }

@Composable
private fun sourceLabel(source: HistoryMealSource): String =
    when (source) {
        HistoryMealSource.Photo -> stringResource(R.string.today_source_photo)
        HistoryMealSource.Pattern -> stringResource(R.string.today_source_pattern)
        HistoryMealSource.Manual -> stringResource(R.string.today_source_manual)
        HistoryMealSource.Mixed -> stringResource(R.string.today_source_mixed)
        HistoryMealSource.Text -> stringResource(R.string.today_source_text)
    }

@Composable
private fun statusLabel(status: HistoryMealStatus): String =
    when (status) {
        HistoryMealStatus.Accepted -> stringResource(R.string.today_status_accepted)
        HistoryMealStatus.Estimating -> stringResource(R.string.today_status_estimating)
        HistoryMealStatus.Queued -> stringResource(R.string.today_status_queued)
        HistoryMealStatus.Conflict -> stringResource(R.string.today_status_conflict)
    }

@Composable
private fun HistoryMealStatus.toMealRowStatus(kind: HistoryMealRowKind): GTMealRowStatus? =
    when (this) {
        HistoryMealStatus.Accepted -> null
        HistoryMealStatus.Estimating -> GTMealRowStatus(
            icon = "\u25CB",
            text = stringResource(R.string.today_status_estimating),
            tone = GTStatusTone.Info,
        )
        HistoryMealStatus.Queued -> GTMealRowStatus(
            icon = "\u2303",
            text = stringResource(R.string.today_status_queued),
            tone = if (kind == HistoryMealRowKind.Pending) GTStatusTone.Muted else GTStatusTone.Info,
        )
        HistoryMealStatus.Conflict -> GTMealRowStatus(
            icon = "!",
            text = stringResource(R.string.today_status_conflict),
            tone = GTStatusTone.Warn,
        )
    }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun StatusSheet(
    selected: HistoryStatusFilter,
    onSelect: (HistoryStatusFilter) -> Unit,
    onDismiss: () -> Unit,
) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        containerColor = GT.colors.surface,
        contentColor = GT.colors.ink,
        tonalElevation = 0.dp,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .navigationBarsPadding()
                .padding(horizontal = 18.dp, vertical = 20.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(
                text = stringResource(R.string.history_status_sheet_title),
                color = GT.colors.ink,
                style = GT.type.serifSection,
            )
            HistoryStatusFilter.entries.forEach { status ->
                GTOutlineButton(
                    text = status.label(),
                    onClick = { onSelect(status) },
                    enabled = status != selected,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
    }
}

@Composable
private fun HistoryStatusFilter.label(): String =
    when (this) {
        HistoryStatusFilter.Active -> stringResource(R.string.history_status_active)
        HistoryStatusFilter.Accepted -> stringResource(R.string.history_status_accepted)
        HistoryStatusFilter.Drafts -> stringResource(R.string.history_status_drafts)
        HistoryStatusFilter.All -> stringResource(R.string.history_status_all)
    }

@Composable
private fun Sparkline(
    points: List<Double>,
    color: Color,
    modifier: Modifier = Modifier,
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
                strokeWidth = 1.3.dp.toPx(),
                cap = StrokeCap.Round,
            )
        }
    }
}

@Composable
private fun SearchGlyph(modifier: Modifier = Modifier) {
    val color = GT.colors.muted
    Canvas(modifier = modifier) {
        drawCircle(
            color = color,
            radius = size.minDimension * 0.32f,
            center = Offset(size.width * 0.42f, size.height * 0.42f),
            style = Stroke(width = 1.3.dp.toPx()),
        )
        drawLine(
            color = color,
            start = Offset(size.width * 0.64f, size.height * 0.64f),
            end = Offset(size.width * 0.9f, size.height * 0.9f),
            strokeWidth = 1.3.dp.toPx(),
            cap = StrokeCap.Round,
        )
    }
}

@Composable
private fun FilterGlyph() {
    val color = GT.colors.ink2
    Canvas(modifier = Modifier.size(16.dp)) {
        val stroke = Stroke(width = 1.3.dp.toPx(), cap = StrokeCap.Round)
        drawLine(color, Offset(2.dp.toPx(), 4.dp.toPx()), Offset(14.dp.toPx(), 4.dp.toPx()), stroke.width)
        drawLine(color, Offset(4.dp.toPx(), 8.dp.toPx()), Offset(12.dp.toPx(), 8.dp.toPx()), stroke.width)
        drawLine(color, Offset(6.dp.toPx(), 12.dp.toPx()), Offset(10.dp.toPx(), 12.dp.toPx()), stroke.width)
    }
}

private fun dayTitle(date: LocalDate): String =
    date.toJavaLocalDate().format(DateTimeFormatter.ofPattern("EEEE, d MMMM", Locale("ru")))

private fun Instant.timeText(): String {
    val time = toLocalDateTime(TimeZone.currentSystemDefault()).time
    return "${time.hour.toString().padStart(2, '0')}:${time.minute.toString().padStart(2, '0')}"
}
