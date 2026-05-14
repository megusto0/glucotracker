package com.local.glucotracker.ui.feature.history

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
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
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
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
import com.local.glucotracker.ui.format.pluralizeDay
import com.local.glucotracker.ui.format.pluralizeMeal
import com.local.glucotracker.ui.format.pluralizePhoto
import com.local.glucotracker.ui.format.pluralizeRecord
import com.local.glucotracker.ui.glucose.LocalGlucoseSurfaces
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.roundToLong
import kotlin.math.sqrt
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toJavaLocalDate
import kotlinx.datetime.toLocalDateTime

@Composable
fun HistoryRoute(
    onOpenMealStack: (LocalDate, String) -> Unit,
    onOpenDay: (LocalDate) -> Unit = {},
    searchRequestCounter: Int = 0,
    brandAccentColor: Color? = null,
    viewModel: HistoryViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    HistoryScreen(
        state = state,
        onOpenMealStack = onOpenMealStack,
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

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun HistoryScreen(
    state: HistoryScreenState,
    onOpenMealStack: (LocalDate, String) -> Unit,
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
    val visibleDays = remember(state.days) { state.days.filter { day -> day.rows.isNotEmpty() } }
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
        if (visibleDays.isNotEmpty()) {
            stickyHeader {
                HourScaleHeader(
                    modifier = Modifier
                        .background(GT.colors.bg)
                        .padding(horizontal = 18.dp, vertical = 4.dp),
                )
            }
        }
        if (visibleDays.isEmpty() && !state.isRefreshing) {
            item {
                GTHintBox(
                    text = stringResource(R.string.history_empty),
                    modifier = Modifier.padding(horizontal = 18.dp),
                )
            }
        }
        items(
            items = visibleDays,
            key = { day -> day.date.toString() },
        ) { day ->
            if (brandAccentColor != null) {
                HistoryDayCard(
                    day = day,
                    markerColor = brandAccentColor,
                    onOpenMealStack = onOpenMealStack,
                    onOpenDay = onOpenDay,
                    modifier = Modifier.padding(horizontal = 18.dp),
                )
            } else {
                HistoryDaySection(
                    day = day,
                    onOpenMealStack = onOpenMealStack,
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
            text = stringResource(
                R.string.history_header_meta_compact,
                pluralizeDay(state.totalDays),
                pluralizeRecord(state.totalRecords),
            ),
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
    onOpenMealStack: (LocalDate, String) -> Unit,
    onOpenDay: (LocalDate) -> Unit,
    modifier: Modifier = Modifier,
) {
    val totals = day.totals
    val kcal = totals?.kcal ?: day.rows.sumOf { it.totalKcal ?: 0.0 }
    val average = day.dailyAverageKcalForPeriod
    val delta = average?.let { (kcal - it).roundToLong() }
    val mealCount = totals?.mealCount ?: day.rows.count { it.kind == HistoryMealRowKind.Accepted }
    val description = stringResource(
        R.string.history_day_sub_compact,
        pluralizeMeal(mealCount),
        pluralizePhoto(day.photoCount),
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
                        text = formatCompactDelta(delta),
                        modifier = Modifier.padding(top = 2.dp),
                        color = deltaColor(delta, markerColor),
                        style = GT.type.monoLabel,
                        maxLines = 1,
                    )
                }
            }
        }
        DayTimeline(
            meals = day.rows.toTimelineMeals(),
            accentColor = markerColor,
            onMealTap = { id -> onOpenMealStack(day.date, id) },
            modifier = Modifier
                .padding(top = 12.dp)
                .fillMaxWidth()
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
private fun HourScaleHeader(modifier: Modifier = Modifier) {
    val lineColor = GT.colors.muted.copy(alpha = 0.3f)
    Column(modifier = modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            HourScaleLabels.forEach { label ->
                Text(
                    text = label,
                    color = GT.colors.muted,
                    style = GT.type.monoLabel.copy(fontSize = 9.sp),
                    maxLines = 1,
                )
            }
        }
        Canvas(
            modifier = Modifier
                .padding(top = 3.dp)
                .fillMaxWidth()
                .height(4.dp),
        ) {
            drawLine(
                color = lineColor,
                start = Offset(0f, size.height / 2f),
                end = Offset(size.width, size.height / 2f),
                strokeWidth = 1.dp.toPx(),
                cap = StrokeCap.Round,
            )
        }
    }
}

@Composable
private fun DayTimeline(
    meals: List<MealForTimeline>,
    accentColor: Color,
    onMealTap: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = GT.colors
    val slate = GT.colors.info
    val sortedMeals = remember(meals) { meals.sortedBy { it.minutesOfDay } }
    Canvas(
        modifier = modifier
            .height(32.dp)
            .pointerInput(sortedMeals) {
                detectTapGestures { offset ->
                    val tapped = sortedMeals
                        .asReversed()
                        .firstOrNull { meal ->
                            val radius = computeTimelineRadiusPx(meal.kcal)
                            val hitRadius = maxOf(radius, 12.dp.toPx())
                            val center = Offset(
                                x = size.width * (meal.minutesOfDay / MinutesPerDayFloat),
                                y = size.height / 2f,
                            )
                            (offset - center).getDistance() <= hitRadius
                        }
                    tapped?.let { onMealTap(it.id) }
                }
            },
    ) {
        val baselineY = size.height / 2f
        drawLine(
            color = colors.muted.copy(alpha = 0.3f),
            start = Offset(0f, baselineY),
            end = Offset(size.width, baselineY),
            strokeWidth = 1.dp.toPx(),
            cap = StrokeCap.Round,
        )
        sortedMeals.forEach { meal ->
            val x = size.width * (meal.minutesOfDay / MinutesPerDayFloat)
            val radius = computeTimelineRadiusPx(meal.kcal)
            val color = when {
                meal.status == HistoryMealStatus.Stuck -> colors.warn
                meal.isMainMeal -> accentColor
                else -> slate
            }
            if (meal.kind == HistoryMealRowKind.Accepted) {
                drawCircle(
                    color = color.copy(alpha = 0.85f),
                    radius = radius,
                    center = Offset(x.coerceIn(0f, size.width), baselineY),
                )
            } else {
                drawCircle(
                    color = color.copy(alpha = 0.9f),
                    radius = radius,
                    center = Offset(x.coerceIn(0f, size.width), baselineY),
                    style = Stroke(width = 1.2.dp.toPx()),
                )
            }
        }
    }
}

@Composable
private fun HistoryDaySection(
    day: HistoryDayUi,
    onOpenMealStack: (LocalDate, String) -> Unit,
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
        DayTimeline(
            meals = day.rows.toTimelineMeals(),
            accentColor = GT.colors.accent,
            onMealTap = { id -> onOpenMealStack(day.date, id) },
            modifier = Modifier
                .padding(top = 10.dp)
                .fillMaxWidth(),
        )
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
                    onOpenMealStack = { id -> onOpenMealStack(day.date, id) },
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
    onOpenMealStack: (String) -> Unit,
) {
    val clickId = row.recordId ?: row.outboxId
    val clickModifier = clickId?.let { id ->
        Modifier.clickable { onOpenMealStack(id) }
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
    val mealCount = totals?.mealCount ?: rows.count { it.kind == HistoryMealRowKind.Accepted }
    return stringResource(
        R.string.history_day_summary_compact,
        pluralizeMeal(mealCount),
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

private fun List<HistoryMealRowUi>.toTimelineMeals(): List<MealForTimeline> =
    mapNotNull { row ->
        val id = row.recordId ?: row.outboxId ?: return@mapNotNull null
        val time = row.eatenAt.toLocalDateTime(TimeZone.currentSystemDefault()).time
        val minutesOfDay = (time.hour * 60 + time.minute).coerceIn(0, MinutesPerDay - 1)
        MealForTimeline(
            id = id,
            minutesOfDay = minutesOfDay,
            kcal = row.totalKcal?.roundToLong()?.toInt()?.coerceAtLeast(0),
            kind = row.kind,
            status = row.status,
            isMainMeal = row.isMainMealForTimeline(),
        )
    }

private fun HistoryMealRowUi.isMainMealForTimeline(): Boolean =
    when (mealRole) {
        "main_meal",
        "composite",
        "meal",
        -> true
        "snack",
        "drink",
        "dessert",
        -> false
        else -> (totalKcal ?: 0.0) >= TimelineSnackKcalThreshold
    }

private fun Density.computeTimelineRadiusPx(kcal: Int?): Float {
    val normalized = sqrt(((kcal ?: 0) / TimelineKcalNormalization).coerceIn(0f, 1f))
    return TimelineMinRadius.toPx() + normalized * (TimelineMaxRadius.toPx() - TimelineMinRadius.toPx())
}

private fun formatCompactDelta(delta: Long): String =
    when {
        delta > 0 -> "+${formatKcal(delta)}"
        delta < 0 -> formatSignedKcal(delta)
        else -> "\u00B10"
    }

@Composable
private fun deltaColor(delta: Long, accentColor: Color): Color =
    when {
        delta > 0 -> accentColor
        delta < 0 -> GT.colors.info
        else -> GT.colors.muted
    }

private data class MealForTimeline(
    val id: String,
    val minutesOfDay: Int,
    val kcal: Int?,
    val kind: HistoryMealRowKind,
    val status: HistoryMealStatus,
    val isMainMeal: Boolean,
)

private val HourScaleLabels = listOf("00", "06", "12", "18", "24")
private val TimelineMinRadius = 4.dp
private val TimelineMaxRadius = 14.dp
private const val MinutesPerDay = 1_440
private const val MinutesPerDayFloat = 1_440f
private const val TimelineKcalNormalization = 700f
private const val TimelineSnackKcalThreshold = 150.0

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
        .format(DateTimeFormatter.ofPattern("EEEE · d MMMM", Locale("ru")))
        .replaceFirstChar { char ->
            if (char.isLowerCase()) char.titlecase(Locale("ru")) else char.toString()
        }

private fun Instant.timeText(): String {
    val time = toLocalDateTime(TimeZone.currentSystemDefault()).time
    return "${time.hour.toString().padStart(2, '0')}:${time.minute.toString().padStart(2, '0')}"
}
