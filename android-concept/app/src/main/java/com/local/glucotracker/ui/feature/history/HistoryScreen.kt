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
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
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
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.design.primitives.GTTag
import com.local.glucotracker.ui.format.formatGrams
import com.local.glucotracker.ui.format.formatKcal
import com.local.glucotracker.ui.format.formatSignedKcal
import com.local.glucotracker.ui.glucose.LocalGlucoseSurfaces
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.max
import kotlin.math.roundToLong
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toJavaLocalDate
import kotlinx.datetime.toLocalDateTime

@Composable
fun HistoryRoute(
    onOpenRecord: (String) -> Unit,
    onOpenDay: (LocalDate) -> Unit = {},
    searchRequestCounter: Int = 0,
    brandAccentColor: Color? = null,
    viewModel: HistoryViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    HistoryScreen(
        state = state,
        onOpenRecord = onOpenRecord,
        onOpenDay = onOpenDay,
        onToggleFilter = viewModel::toggleFilter,
        onClearFilters = viewModel::clearFilters,
        onStatusChange = viewModel::setStatus,
        onSearchChange = viewModel::setSearch,
        onLoadMore = viewModel::loadMore,
        searchRequestCounter = searchRequestCounter,
        brandAccentColor = brandAccentColor,
    )
}

@Composable
fun HistoryScreen(
    state: HistoryScreenState,
    onOpenRecord: (String) -> Unit,
    onOpenDay: (LocalDate) -> Unit,
    onToggleFilter: (HistoryFilter) -> Unit,
    onClearFilters: () -> Unit,
    onStatusChange: (HistoryStatusFilter) -> Unit,
    onSearchChange: (String) -> Unit,
    onLoadMore: () -> Unit,
    modifier: Modifier = Modifier,
    searchRequestCounter: Int = 0,
    brandAccentColor: Color? = null,
) {
    var statusSheetVisible by remember { mutableStateOf(false) }
    var searchVisible by remember { mutableStateOf(state.search.isNotBlank()) }
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

    LaunchedEffect(searchRequestCounter) {
        if (searchRequestCounter > 0) searchVisible = true
    }

    LazyColumn(
        state = listState,
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            if (brandAccentColor != null) {
                FoodHistoryHeader(
                    state = state,
                    searchVisible = searchVisible,
                    onToggleFilter = onToggleFilter,
                    onClearFilters = onClearFilters,
                    onSearchChange = onSearchChange,
                    modifier = Modifier.padding(horizontal = 18.dp, vertical = 10.dp),
                )
            } else {
                HistoryHeader(
                    state = state,
                    onToggleFilter = onToggleFilter,
                    onSearchChange = onSearchChange,
                    onStatusClick = { statusSheetVisible = true },
                    modifier = Modifier.padding(horizontal = 18.dp, vertical = 10.dp),
                )
            }
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
            if (brandAccentColor != null) {
                HistoryDayCard(
                    day = day,
                    markerColor = brandAccentColor,
                    onOpenDay = onOpenDay,
                    modifier = Modifier.padding(horizontal = 18.dp),
                )
            } else {
                HistoryDaySection(
                    day = day,
                    onOpenRecord = onOpenRecord,
                    modifier = Modifier.padding(horizontal = 18.dp),
                )
            }
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

    if (statusSheetVisible && brandAccentColor == null) {
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
private fun FoodHistoryHeader(
    state: HistoryScreenState,
    searchVisible: Boolean,
    onToggleFilter: (HistoryFilter) -> Unit,
    onClearFilters: () -> Unit,
    onSearchChange: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier.fillMaxWidth()) {
        Text(
            text = stringResource(R.string.history_title),
            color = GT.colors.ink,
            style = GT.type.serifTitle,
            maxLines = 1,
        )
        Text(
            text = stringResource(R.string.history_header_meta, state.totalDays, state.totalRecords),
            modifier = Modifier.padding(top = 4.dp),
            color = GT.colors.muted,
            style = GT.type.monoLabel,
            maxLines = 1,
        )
        if (searchVisible) {
            SearchField(
                value = state.search,
                onValueChange = onSearchChange,
                modifier = Modifier.padding(top = 12.dp),
            )
        }
        Row(
            modifier = Modifier
                .padding(top = 12.dp)
                .horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            FilterChip(
                label = stringResource(R.string.history_filter_all),
                active = state.filters.isEmpty(),
                onClick = onClearFilters,
            )
            FilterChip(
                label = stringResource(R.string.history_filter_photo),
                active = HistoryFilter.PhotoOnly in state.filters,
                onClick = { onToggleFilter(HistoryFilter.PhotoOnly) },
            )
            FilterChip(
                label = stringResource(R.string.history_filter_sweet),
                active = HistoryFilter.Sweet in state.filters,
                onClick = { onToggleFilter(HistoryFilter.Sweet) },
            )
            FilterChip(
                label = stringResource(R.string.history_filter_breakfast),
                active = HistoryFilter.Breakfast in state.filters,
                onClick = { onToggleFilter(HistoryFilter.Breakfast) },
            )
            FilterChip(
                label = stringResource(R.string.history_filter_low_confidence),
                active = HistoryFilter.LowConfidence in state.filters,
                onClick = { onToggleFilter(HistoryFilter.LowConfidence) },
            )
        }
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
private fun HistoryDayCard(
    day: HistoryDayUi,
    markerColor: Color,
    onOpenDay: (LocalDate) -> Unit,
    modifier: Modifier = Modifier,
) {
    val totals = day.totals
    val kcal = totals?.kcal ?: day.rows.sumOf { it.totalKcal ?: 0.0 }
    val average = day.dailyAverageKcalForPeriod
    val delta = average?.let { (kcal - it).roundToLong() }
    val description = stringResource(
        R.string.history_day_sub,
        totals?.mealCount ?: day.rows.count { it.kind == HistoryMealRowKind.Accepted },
        day.photoCount,
    )
    Column(
        modifier = modifier
            .fillMaxWidth()
            .clickable { onOpenDay(day.date) }
            .semantics {
                contentDescription = "${dayTitle(day.date)}, ${formatKcal(kcal)} ккал, $description"
            },
    ) {
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
                    text = description,
                    modifier = Modifier.padding(top = 3.dp),
                    color = GT.colors.muted,
                    style = GT.type.monoLabel,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    text = formatKcal(kcal),
                    color = GT.colors.ink,
                    style = GT.type.monoNumber,
                    maxLines = 1,
                )
                if (delta != null) {
                    Text(
                        text = stringResource(R.string.history_delta_average, formatSignedKcal(delta)),
                        modifier = Modifier.padding(top = 2.dp),
                        color = GT.colors.muted,
                        style = GT.type.monoLabel,
                        maxLines = 1,
                    )
                }
            }
        }
        HistorySparkline(
            rows = day.rows,
            markerColor = markerColor,
            modifier = Modifier
                .padding(top = 12.dp)
                .fillMaxWidth()
                .height(32.dp),
        )
        Text(
            text = stringResource(
                R.string.history_macro_summary,
                formatGrams(totals?.proteinG ?: day.rows.sumOf { it.totalProteinG ?: 0.0 }),
                formatGrams(totals?.fatG ?: day.rows.sumOf { it.totalFatG ?: 0.0 }),
                formatGrams(totals?.carbsG ?: day.rows.sumOf { it.totalCarbsG ?: 0.0 }),
            ),
            modifier = Modifier.padding(top = 10.dp),
            color = GT.colors.muted,
            style = GT.type.monoLabel,
            maxLines = 1,
        )
        GTHairlineDivider(modifier = Modifier.padding(top = 14.dp))
    }
}

@Composable
private fun HistorySparkline(
    rows: List<HistoryMealRowUi>,
    markerColor: Color,
    modifier: Modifier = Modifier,
) {
    val colors = GT.colors
    val acceptedRows = remember(rows) {
        rows
            .filter { it.kind == HistoryMealRowKind.Accepted && (it.totalKcal ?: 0.0) > 0.0 }
            .sortedBy { it.eatenAt }
    }
    Canvas(modifier = modifier) {
        val baseline = size.height - 2.dp.toPx()
        if (acceptedRows.isEmpty()) {
            drawLine(
                color = colors.hairline2,
                start = Offset(0f, baseline),
                end = Offset(size.width, baseline),
                strokeWidth = 1.2.dp.toPx(),
            )
            return@Canvas
        }

        val total = max(acceptedRows.sumOf { it.totalKcal ?: 0.0 }.toFloat(), 1f)
        var cumulative = 0f
        val points = acceptedRows.map { row ->
            cumulative += (row.totalKcal ?: 0.0).toFloat()
            val time = row.eatenAt.toLocalDateTime(TimeZone.currentSystemDefault()).time
            val minuteOfDay = time.hour * 60 + time.minute
            val x = size.width * (minuteOfDay / 1_439f)
            val y = baseline - (baseline - 2.dp.toPx()) * (cumulative / total)
            row to Offset(x.coerceIn(0f, size.width), y.coerceIn(2.dp.toPx(), baseline))
        }
        val path = Path().apply {
            moveTo(0f, baseline)
            points.forEach { (_, point) -> lineTo(point.x, point.y) }
            lineTo(size.width, points.last().second.y)
        }
        drawPath(
            path = path,
            color = colors.ink,
            style = Stroke(width = 1.5.dp.toPx(), cap = StrokeCap.Round),
        )
        points
            .filter { (row, _) -> row.isSweet }
            .forEach { (_, point) ->
                drawCircle(
                    color = markerColor,
                    radius = 2.5.dp.toPx(),
                    center = point,
                )
            }
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
            LocalGlucoseSurfaces.current.HistoryDayCgmSparkline(day.date)
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
            meta = row.pendingErrorText()
                ?: stringResource(
                    R.string.today_meal_meta,
                    row.eatenAt.timeText(),
                    sourceLabel(row.source),
                ),
            primaryRight = primaryRightText(row),
            secondaryRight = secondaryRightText(row),
            status = null,
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
        HistoryMealSource.Restaurant -> stringResource(R.string.today_source_restaurant)
        HistoryMealSource.Pattern -> stringResource(R.string.today_source_pattern)
        HistoryMealSource.Manual -> stringResource(R.string.today_source_manual)
        HistoryMealSource.Mixed -> stringResource(R.string.today_source_mixed)
        HistoryMealSource.Text -> stringResource(R.string.today_source_text)
    }

@Composable
private fun primaryRightText(row: HistoryMealRowUi): String =
    if (row.kind == HistoryMealRowKind.Pending) {
        pendingStatusText(row.status)
    } else {
        row.totalCarbsG?.let { stringResource(R.string.today_right_carbs, formatGrams(it)) }
            ?: stringResource(R.string.value_empty)
    }

@Composable
private fun secondaryRightText(row: HistoryMealRowUi): String =
    if (row.kind == HistoryMealRowKind.Pending) {
        ""
    } else {
        row.totalKcal?.let { stringResource(R.string.today_right_kcal, formatKcal(it)) }
            ?: stringResource(R.string.value_empty)
    }

@Composable
private fun pendingStatusText(status: HistoryMealStatus): String =
    when (status) {
        HistoryMealStatus.Estimating -> stringResource(R.string.today_status_estimating)
        HistoryMealStatus.Uploading -> stringResource(R.string.today_status_uploading)
        HistoryMealStatus.Queued -> stringResource(R.string.today_status_queued)
        HistoryMealStatus.Stuck -> stringResource(R.string.today_status_conflict)
        HistoryMealStatus.Accepted -> stringResource(R.string.today_status_estimating)
    }

@Composable
private fun HistoryMealRowUi.pendingErrorText(): String? =
    errorMessage
        ?.takeIf { kind == HistoryMealRowKind.Pending && it.isNotBlank() }
        ?.let { stringResource(R.string.today_pending_error, it.take(120)) }

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
    date.toJavaLocalDate()
        .format(DateTimeFormatter.ofPattern("EEEE, d MMMM", Locale("ru")))
        .replaceFirstChar { char ->
            if (char.isLowerCase()) char.titlecase(Locale("ru")) else char.toString()
        }

private fun Instant.timeText(): String {
    val time = toLocalDateTime(TimeZone.currentSystemDefault()).time
    return "${time.hour.toString().padStart(2, '0')}:${time.minute.toString().padStart(2, '0')}"
}
