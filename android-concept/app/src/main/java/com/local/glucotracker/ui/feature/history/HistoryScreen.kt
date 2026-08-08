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
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.aspectRatio
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
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
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
import com.local.glucotracker.ui.design.primitives.FoodCurveMeal
import com.local.glucotracker.ui.design.primitives.FoodDayCurve
import com.local.glucotracker.ui.design.primitives.GTHintBox
import com.local.glucotracker.ui.design.primitives.GTIconButton
import com.local.glucotracker.ui.design.primitives.GTMealRow
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.design.primitives.GTPhotoGlyph
import com.local.glucotracker.ui.design.primitives.GTTag
import com.local.glucotracker.ui.image.rememberApiImageModel
import coil3.compose.AsyncImage
import com.local.glucotracker.ui.format.formatGrams
import com.local.glucotracker.ui.format.formatKcal
import com.local.glucotracker.ui.format.formatPercent
import com.local.glucotracker.ui.format.formatSignedKcal
import com.local.glucotracker.ui.format.formatSignedMmol
import com.local.glucotracker.ui.format.pluralizeDay
import com.local.glucotracker.ui.format.pluralizeDish
import com.local.glucotracker.ui.format.pluralizeMeal
import com.local.glucotracker.ui.format.pluralizePhoto
import com.local.glucotracker.ui.format.pluralizeRecord
import com.local.glucotracker.ui.glucose.HistoryTimelineCircleInput
import com.local.glucotracker.ui.glucose.HistoryTimelineMeal
import com.local.glucotracker.ui.glucose.LocalGlucoseSurfaces
import com.local.glucotracker.ui.glucose.layoutHistoryTimelineCircles
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.roundToLong
import kotlin.math.roundToInt
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
        onViewModeChange = viewModel::setViewMode,
        onShowcaseColumnsChange = viewModel::setShowcaseColumns,
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
    onViewModeChange: (HistoryViewMode) -> Unit = {},
    onShowcaseColumnsChange: (Int) -> Unit = {},
    onSearchChange: (String) -> Unit,
    onLoadMore: () -> Unit,
    modifier: Modifier = Modifier,
    searchRequestCounter: Int = 0,
    brandAccentColor: Color? = null,
) {
    var statusSheetVisible by remember { mutableStateOf(false) }
    var viewSheetVisible by remember { mutableStateOf(false) }
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
                    onToggleFilter = onToggleFilter,
                    onClearFilters = onClearFilters,
                    onSearchChange = onSearchChange,
                    viewMode = state.viewMode,
                    onViewClick = { viewSheetVisible = true },
                    modifier = Modifier.padding(horizontal = 18.dp, vertical = 10.dp),
                )
            } else {
                HistoryHeader(
                    state = state,
                    onToggleFilter = onToggleFilter,
                    onSearchChange = onSearchChange,
                    onStatusClick = { statusSheetVisible = true },
                    viewMode = state.viewMode,
                    onViewClick = { viewSheetVisible = true },
                    modifier = Modifier.padding(horizontal = 18.dp, vertical = 10.dp),
                )
            }
        }
        // The hour scale used to be pinned above the whole list, separated
        // from the sparklines it labels by a divider and a day heading, so it
        // read as page furniture. It now sits directly on top of each day's
        // own timeline.
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
            if (brandAccentColor != null && state.viewMode == HistoryViewMode.Showcase) {
                HistoryDayCard(
                    day = day,
                    showcaseColumns = state.showcaseColumns,
                    dailyKcalGoal = state.dailyKcalGoal,
                    onOpenMealStack = onOpenMealStack,
                    onOpenDay = onOpenDay,
                    modifier = Modifier.padding(horizontal = 18.dp),
                )
            } else {
                HistoryDaySection(
                    day = day,
                    onOpenMealStack = onOpenMealStack,
                    showcaseMeals = state.viewMode == HistoryViewMode.Showcase,
                    showcaseColumns = state.showcaseColumns,
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
    if (viewSheetVisible) {
        ViewModeSheet(
            selected = state.viewMode,
            showcaseColumns = state.showcaseColumns,
            onSelect = { mode ->
                onViewModeChange(mode)
            },
            onShowcaseColumnsSelect = onShowcaseColumnsChange,
            onDismiss = { viewSheetVisible = false },
        )
    }
}

@Composable
private fun FoodHistoryHeader(
    state: HistoryScreenState,
    onToggleFilter: (HistoryFilter) -> Unit,
    onClearFilters: () -> Unit,
    onSearchChange: (String) -> Unit,
    viewMode: HistoryViewMode,
    onViewClick: () -> Unit,
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
            CompactHistorySearchField(
                value = state.search,
                onValueChange = onSearchChange,
                modifier = Modifier
                    .padding(start = 12.dp)
                    .weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            HistoryViewButton(viewMode = viewMode, onClick = onViewClick)
        }
        Row(
            modifier = Modifier
                .padding(top = 8.dp)
                .horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            FilterChip(
                label = stringResource(R.string.food_history_filter_all),
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
        GTHairlineDivider(modifier = Modifier.padding(top = 8.dp))
    }
}

@Composable
private fun CompactHistorySearchField(
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .height(34.dp)
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .padding(horizontal = 10.dp),
        contentAlignment = Alignment.CenterStart,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            SearchGlyph(modifier = Modifier.size(14.dp))
            Spacer(Modifier.width(7.dp))
            Box(modifier = Modifier.weight(1f)) {
                if (value.isBlank()) {
                    Text(
                        text = stringResource(R.string.history_search_hint),
                        color = GT.colors.muted,
                        style = GT.type.sansLabel,
                    )
                }
                BasicTextField(
                    value = value,
                    onValueChange = onValueChange,
                    modifier = Modifier.fillMaxWidth(),
                    textStyle = GT.type.sansLabel.copy(color = GT.colors.ink),
                    singleLine = true,
                )
            }
        }
    }
}

@Composable
private fun HistoryHeader(
    state: HistoryScreenState,
    onToggleFilter: (HistoryFilter) -> Unit,
    onSearchChange: (String) -> Unit,
    onStatusClick: () -> Unit,
    viewMode: HistoryViewMode,
    onViewClick: () -> Unit,
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
            HistoryViewButton(viewMode = viewMode, onClick = onViewClick)
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
private fun HistoryViewButton(
    viewMode: HistoryViewMode,
    onClick: () -> Unit,
) {
    val description = stringResource(R.string.history_view_content_description)
    GTIconButton(
        onClick = onClick,
        modifier = Modifier.semantics { contentDescription = description },
    ) {
        HistoryViewGlyph(viewMode)
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
    showcaseColumns: Int,
    dailyKcalGoal: Int?,
    onOpenMealStack: (LocalDate, String) -> Unit,
    onOpenDay: (LocalDate) -> Unit,
    modifier: Modifier = Modifier,
) {
    val totals = day.totals
    val kcal = totals?.kcal ?: day.rows.sumOf { it.totalKcal ?: 0.0 }
    val mealCount = totals?.mealCount ?: day.rows.count { it.kind == HistoryMealRowKind.Accepted }
    val dayKcalGoal = totals?.tdeeKcal
        ?.takeIf { it > 0.0 }
        ?.roundToInt()
        ?: dailyKcalGoal
    val goalShare = dayKcalGoal
        ?.takeIf { it > 0 }
        ?.let { goal -> formatPercent(kcal / goal * 100.0) }
        ?: stringResource(R.string.value_empty)
    val eatingWindow = day.rows.foodEatingWindow()
    val description = stringResource(
        R.string.food_history_day_summary,
        pluralizeDish(mealCount),
        formatKcal(kcal),
        goalShare,
        eatingWindow,
    )
    val balance = dayKcalGoal?.let { goal -> kcal - goal }
    val curveMeals = day.rows.toFoodCurveMeals()
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
            balance?.let { value ->
                Text(
                    text = formatSignedKcal(value.roundToLong()),
                    color = if (value <= 0.0) GT.colors.accent else GT.colors.warn,
                    style = GT.type.monoLabel.copy(fontSize = 11.5.sp),
                    maxLines = 1,
                )
            }
        }
        FoodDayCurve(
            meals = curveMeals,
            totalKcal = kcal,
            goalKcal = dayKcalGoal,
            contentDescription = stringResource(
                R.string.food_curve_content_description,
                formatKcal(kcal),
            ),
            modifier = Modifier
                .padding(top = 8.dp)
                .fillMaxWidth()
                .height(56.dp),
        )
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            FoodHistoryHourLabels.forEach { hour ->
                Text(
                    text = hour,
                    color = GT.colors.hairline2,
                    style = GT.type.monoLabel.copy(fontSize = 9.sp),
                )
            }
        }
        HistoryShowcase(
            rows = day.rows,
            columns = showcaseColumns,
            onOpenMealStack = { id -> onOpenMealStack(day.date, id) },
            showKindRail = true,
            modifier = Modifier.padding(top = 12.dp),
        )
        GTHairlineDivider(modifier = Modifier.padding(top = 14.dp))
    }
}

private fun List<HistoryMealRowUi>.toFoodCurveMeals(): List<FoodCurveMeal> =
    filter { it.kind == HistoryMealRowKind.Accepted }.map { row ->
        val time = row.eatenAt.toLocalDateTime(TimeZone.currentSystemDefault()).time
        FoodCurveMeal(
            minutesOfDay = time.hour * 60 + time.minute,
            kcal = row.totalKcal ?: 0.0,
            kind = if (row.mealRole?.lowercase() in FoodHistorySnackRoles) {
                FoodCurveMeal.Kind.Snack
            } else {
                FoodCurveMeal.Kind.Meal
            },
        )
    }

private fun List<HistoryMealRowUi>.foodEatingWindow(): String {
    val accepted = filter { it.kind == HistoryMealRowKind.Accepted }
    val first = accepted.minOfOrNull { it.eatenAt } ?: return "—"
    val last = accepted.maxOfOrNull { it.eatenAt } ?: return "—"
    val minutes = ((last.epochSeconds - first.epochSeconds) / 60).coerceAtLeast(0)
    return "${minutes / 60}:${(minutes % 60).toString().padStart(2, '0')}"
}

private val FoodHistorySnackRoles = setOf("snack", "drink", "dessert")
private val FoodHistoryHourLabels = listOf("00", "06", "12", "18", "24")

/**
 * The day's food as a shelf of pictures rather than a column of lines.
 *
 * History answers two different questions and a list only answers one. «What
 * happened that day» is sequence and numbers, which is what the gluco list is
 * for. «Show me the thing I ate» is recognition, and a 36 dp thumbnail is not a
 * picture — it is an icon meaning "there was a photo". Three to a row, each a
 * third of the screen, is the size at which food is actually identifiable.
 *
 * The grid is the food flavor's default and an optional recognition-first view
 * in gluco. It deliberately carries dishes rather than insulin context; gluco
 * keeps the episode-rich list as its default.
 *
 * Built from plain rows, not a lazy grid: this sits inside a LazyColumn item,
 * where a nested lazy container has no bounded height to measure against.
 */
@Composable
private fun HistoryShowcase(
    rows: List<HistoryMealRowUi>,
    columns: Int,
    onOpenMealStack: (String) -> Unit,
    showKindRail: Boolean = false,
    modifier: Modifier = Modifier,
) {
    val entries = remember(rows) { rows.filter { it.kind == HistoryMealRowKind.Accepted } }
    if (entries.isEmpty()) return
    val columnCount = columns.coerceIn(2, 4)
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(9.dp),
    ) {
        entries.chunked(columnCount).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(9.dp)) {
                row.forEach { entry ->
                    ShowcaseTile(
                        row = entry,
                        onOpen = { (entry.recordId ?: entry.outboxId)?.let(onOpenMealStack) },
                        showKindRail = showKindRail,
                        modifier = Modifier.weight(1f),
                    )
                }
                // Keeps the last row's tiles the width of every other row's.
                repeat(columnCount - row.size) {
                    Spacer(Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
private fun ShowcaseTile(
    row: HistoryMealRowUi,
    onOpen: () -> Unit,
    showKindRail: Boolean,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.clickable(onClick = onOpen),
        verticalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        // Branch on the resolved model, not on the URL. `apiImageModel`
        // returns null for an API-hosted picture until the access token is in
        // hand — and never has one under Paparazzi — so testing the URL drew
        // an empty square for every photo that had not loaded yet.
        val model = rememberApiImageModel(row.photo)
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(1f)
                .clip(GT.shapes.card)
                .background(GT.colors.bg),
            contentAlignment = if (model == null && row.photo == null) {
                Alignment.BottomStart
            } else {
                Alignment.Center
            },
        ) {
            when {
                model != null -> AsyncImage(
                    model = model,
                    contentDescription = null,
                    modifier = Modifier.matchParentSize(),
                    contentScale = ContentScale.Crop,
                )
                // There is a picture, it just is not here yet. Say so, rather
                // than showing a number that will be replaced by an image.
                row.photo != null -> GTPhotoGlyph(glyphSize = 26.dp)
                // Genuinely no picture: the square goes to the number. An empty
                // frame would break the shelf's rhythm to say nothing.
                else -> Text(
                    text = row.totalKcal?.let { formatKcal(it) }
                        ?: stringResource(R.string.value_empty),
                    modifier = Modifier.padding(10.dp),
                    color = GT.colors.ink2,
                    style = GT.type.monoNumber.copy(fontSize = 17.sp),
                    maxLines = 1,
                )
            }
            if (showKindRail) {
                val railColor = if (row.mealRole?.lowercase() in FoodHistorySnackRoles) {
                    GT.colors.kindSnack
                } else {
                    GT.colors.kindMeal
                }
                Box(
                    modifier = Modifier
                        .align(Alignment.TopCenter)
                        .fillMaxWidth()
                        .height(3.dp)
                        .background(railColor),
                )
            }
        }
        Text(
            text = row.title ?: fallbackTitle(row),
            color = GT.colors.ink,
            style = GT.type.sansLabel.copy(fontSize = 11.5.sp),
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        Text(
            text = listOfNotNull(
                row.totalKcal?.let { formatKcal(it) },
                row.eatenAt.timeText(),
            ).joinToString(" · "),
            color = GT.colors.muted,
            style = GT.type.monoLabel.copy(fontSize = 10.sp),
            maxLines = 1,
        )
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
    meals: List<HistoryTimelineMeal>,
    accentColor: Color,
    onMealTap: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = GT.colors
    val sortedMeals = remember(meals) { meals.sortedBy { it.minutesOfDay } }
    Canvas(
        modifier = modifier
            .height(28.dp)
            .pointerInput(sortedMeals) {
                detectTapGestures { offset ->
                    val baselineY = size.height / 2f
                    val laidOut = layoutHistoryTimelineCircles(
                        meals = sortedMeals.map { meal ->
                            HistoryTimelineCircleInput(
                                id = meal.id,
                                x = size.width * (meal.minutesOfDay / MinutesPerDayFloat),
                                naturalY = baselineY,
                                radius = computeTimelineRadiusPx(meal.kcal),
                            )
                        },
                        padding = 2.dp.toPx(),
                    )
                    val tapped = laidOut
                        .asReversed()
                        .firstOrNull { layout ->
                            val hitRadius = maxOf(layout.radius, 12.dp.toPx())
                            val center = Offset(layout.x.coerceIn(0f, size.width.toFloat()), layout.y)
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
        val laidOut = layoutHistoryTimelineCircles(
            meals = sortedMeals.map { meal ->
                HistoryTimelineCircleInput(
                    id = meal.id,
                    x = size.width * (meal.minutesOfDay / MinutesPerDayFloat),
                    naturalY = baselineY,
                    radius = computeTimelineRadiusPx(meal.kcal),
                )
            },
            padding = 2.dp.toPx(),
        )
        laidOut.forEach { layout ->
            val center = Offset(layout.x.coerceIn(0f, size.width), layout.y)
            drawCircle(
                color = accentColor.copy(alpha = 0.5f),
                radius = layout.radius,
                center = center,
            )
            drawCircle(
                color = accentColor.copy(alpha = 0.8f),
                radius = layout.radius,
                center = center,
                style = Stroke(width = 1.dp.toPx()),
            )
        }
    }
}

@Composable
private fun HistoryDaySection(
    day: HistoryDayUi,
    onOpenMealStack: (LocalDate, String) -> Unit,
    showcaseMeals: Boolean = false,
    showcaseColumns: Int = DefaultShowcaseColumns,
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
                // What went in, then how it went. Absent for the food flavor.
                LocalGlucoseSurfaces.current.HistoryDayGlucoseSummary(
                    date = day.date,
                    modifier = Modifier.padding(top = 2.dp),
                )
            }
        }
        HourScaleHeader(modifier = Modifier.padding(top = 10.dp))
        LocalGlucoseSurfaces.current.HistoryDayTimeline(
            date = day.date,
            meals = day.rows.toTimelineMeals(),
            onMealTap = { id -> onOpenMealStack(day.date, id) },
            modifier = Modifier
                .padding(top = 10.dp)
                .fillMaxWidth(),
        )
        // No day-wide card any more: each episode carries its own, the way
        // Today does. Wrapping the whole day in one and separating sittings
        // with a hairline is what left every time in a left gutter with
        // nothing to state what the sitting was.
        if (showcaseMeals) {
            HistoryShowcase(
                rows = day.rows,
                columns = showcaseColumns,
                onOpenMealStack = { id -> onOpenMealStack(day.date, id) },
                modifier = Modifier.padding(top = 12.dp),
            )
            GTHairlineDivider(modifier = Modifier.padding(top = 14.dp))
        } else {
            Column(
                modifier = Modifier.padding(top = 8.dp).fillMaxWidth(),
            ) {
                LocalGlucoseSurfaces.current.HistoryRows(
                    date = day.date,
                    rows = day.rows,
                    rowContent = { row, tone, framed, showTime, extraMetaContent ->
                        HistoryMealRow(
                            row = row,
                            tone = tone,
                            framed = framed,
                            showTime = showTime,
                            onOpenMealStack = { id -> onOpenMealStack(day.date, id) },
                            extraMetaContent = extraMetaContent,
                        )
                    },
                    divider = { Spacer(Modifier.height(14.dp)) },
                )
            }
        }
    }
}

@Composable
private fun HistoryMealRow(
    row: HistoryMealRowUi,
    tone: HistoryEntryTone?,
    onOpenMealStack: (String) -> Unit,
    framed: Boolean = true,
    showTime: Boolean = true,
    extraMetaContent: @Composable ColumnScope.() -> Unit = {},
) {
    val clickId = row.recordId ?: row.outboxId
    val clickModifier = clickId?.let { id ->
        Modifier.clickable { onOpenMealStack(id) }
    } ?: Modifier
    // The mark moved onto the photo, where the thing it describes is. Against
    // the row's outer edge it sat furthest from the entry and spent a column of
    // width doing it. Every tone still says its name in the meta line, so
    // colour is never the only thing carrying the kind.
    val kindColor = toneColor(tone)
    val surface = if (framed) {
        Modifier
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
    } else {
        Modifier
    }
    Box(modifier = surface.then(clickModifier)) {
        GTMealRow(
            time = if (showTime) row.eatenAt.timeText() else "",
            // Inside an episode card the header states the minute, so the
            // column goes rather than blanking out — reserved and empty it
            // pushed every photo a column in from the card's own edge.
            reserveTimeGutter = framed,
            photo = row.photo,
            name = row.title ?: fallbackTitle(row),
            // The time already sits in the gutter and the thumbnail already
            // says there is a photo, so this line used to carry nothing new.
            // It now reports how the meal landed, and falls back to the source
            // only when no glucose response was recorded and the source is not
            // already visible as a picture.
            meta = row.pendingErrorText()
                ?: listOfNotNull(tone?.label, outcomeText(row))
                    .takeIf { it.isNotEmpty() }
                    ?.joinToString(" · ")
                ?: sourceMeta(row.source),
            primaryRight = primaryRightText(row),
            secondaryRight = secondaryRightText(row),
            status = null,
            muted = row.kind == HistoryMealRowKind.Pending,
            kindColor = kindColor,
            extraMetaContent = extraMetaContent,
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
        pluralizeDish(mealCount),
        formatGrams(totals?.carbsG ?: 0.0),
        formatKcal(totals?.kcal ?: 0.0),
        balance,
    )
}

/**
 * Palette per entry kind, from the existing tokens only.
 *
 * A plain meal gets no rail: tinting the common case would leave nothing for
 * the uncommon ones to stand out against.
 */
@Composable
/**
 * Kind tokens, not repurposed status colours.
 *
 * A rescue was drawn in `warn` and a correction in `info`, which say "warning"
 * and "information" — the wrong words for two kinds of treatment, and both
 * already carry those meanings elsewhere on the screen. The kind palette exists
 * to be read as kind and nothing else.
 *
 * A meal stays untinted: it is the commonest kind, and a rail beside every row
 * is a rail beside none.
 */
private fun toneColor(tone: HistoryEntryTone?): Color? = when (tone?.kind) {
    HistoryEntryTone.Kind.Snack -> GT.colors.kindSnack
    HistoryEntryTone.Kind.CarbCorrection -> GT.colors.kindCarbRescue
    HistoryEntryTone.Kind.InsulinCorrection -> GT.colors.kindInsulinCorrection
    // A meal is marked too, in graphite. As a rail against the row's edge it
    // was left blank, because a rail beside every row is a rail beside none —
    // but on the photo the mark is the entry's own, and a plate with no bar
    // beside a snack with one reads as "unclassified" rather than "ordinary".
    HistoryEntryTone.Kind.Meal -> GT.colors.kindMeal
    null -> null
}

/**
 * How far glucose rose after the meal, when that was measured.
 *
 * One number, not a verdict: the review page owns the curve and the judgement.
 * Here it only has to make a day scannable for which meals moved the needle.
 */
@Composable
private fun outcomeText(row: HistoryMealRowUi): String? {
    if (row.kind != HistoryMealRowKind.Accepted) return null
    val delta = row.deltaMaxMmolL ?: return null
    return stringResource(R.string.history_meal_outcome, formatSignedMmol(delta))
}

@Composable
private fun fallbackTitle(row: HistoryMealRowUi): String =
    if (row.source == HistoryMealSource.Photo && row.kind == HistoryMealRowKind.Pending) {
        stringResource(R.string.today_pending_photo_title)
    } else {
        stringResource(R.string.today_meal_fallback)
    }

/** The source, unless the thumbnail beside it has already said so. */
@Composable
private fun sourceMeta(source: HistoryMealSource): String =
    if (source == HistoryMealSource.Photo) "" else sourceLabel(source)

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
/**
 * One line, not two stacked. «449 · 5,4 г» is the same two numbers in half the
 * height, and height is the whole point of a list read by scanning it.
 */
private fun primaryRightText(row: HistoryMealRowUi): String =
    if (row.kind == HistoryMealRowKind.Pending) {
        pendingStatusText(row.status)
    } else {
        listOfNotNull(
            row.totalKcal?.let { formatKcal(it) },
            row.totalCarbsG?.let { stringResource(R.string.today_right_carbs, formatGrams(it)) },
        ).takeIf { it.isNotEmpty() }
            ?.joinToString(" · ")
            ?: stringResource(R.string.value_empty)
    }

@Composable
private fun secondaryRightText(row: HistoryMealRowUi): String = ""

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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ViewModeSheet(
    selected: HistoryViewMode,
    showcaseColumns: Int,
    onSelect: (HistoryViewMode) -> Unit,
    onShowcaseColumnsSelect: (Int) -> Unit,
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
                .padding(bottom = 14.dp),
        ) {
            Text(
                text = stringResource(R.string.history_view_sheet_title),
                modifier = Modifier.padding(horizontal = 18.dp),
                color = GT.colors.ink,
                style = GT.type.kicker,
            )
            Row(
                modifier = Modifier
                    .padding(horizontal = 18.dp, vertical = 10.dp)
                    .fillMaxWidth()
                    .selectableGroup(),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                HistoryViewMode.entries.forEach { mode ->
                    ViewModeOption(
                        mode = mode,
                        selected = mode == selected,
                        onSelect = { onSelect(mode) },
                        modifier = Modifier.weight(1f),
                    )
                }
            }
            GTHairlineDivider()
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 18.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = stringResource(R.string.history_view_tile_size),
                    modifier = Modifier.weight(1f),
                    color = if (selected == HistoryViewMode.Showcase) GT.colors.ink else GT.colors.muted,
                    style = GT.type.sansBody,
                )
                TileSizeSelector(
                    selectedColumns = showcaseColumns,
                    enabled = selected == HistoryViewMode.Showcase,
                    onSelect = onShowcaseColumnsSelect,
                )
            }
        }
    }
}

@Composable
private fun ViewModeOption(
    mode: HistoryViewMode,
    selected: Boolean,
    onSelect: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val selectedDescription = stringResource(R.string.history_view_selected)
    Column(
        modifier = modifier.selectable(
            selected = selected,
            onClick = onSelect,
            role = Role.RadioButton,
        ).semantics {
            if (selected) stateDescription = selectedDescription
        },
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(104.dp)
                .background(GT.colors.surface2, GT.shapes.card)
                .border(
                    width = if (selected) 1.dp else GT.space.hairline,
                    color = if (selected) GT.colors.ink else GT.colors.hairline2,
                    shape = GT.shapes.card,
                ),
        ) {
            ViewModePreview(
                mode = mode,
                modifier = Modifier
                    .fillMaxSize()
                    .padding(10.dp),
            )
            if (selected) {
                SelectionCheck(
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .padding(5.dp)
                        .size(18.dp),
                )
            }
        }
        Text(
            text = mode.label(),
            modifier = Modifier.padding(top = 7.dp),
            color = GT.colors.ink,
            style = GT.type.sansLabel,
            maxLines = 1,
        )
        Text(
            text = mode.hint(),
            modifier = Modifier.padding(top = 2.dp),
            color = GT.colors.muted,
            style = GT.type.sansLabel.copy(fontSize = 10.sp),
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun ViewModePreview(
    mode: HistoryViewMode,
    modifier: Modifier = Modifier,
) {
    val line = GT.colors.hairline2
    val tile = GT.colors.hairline
    Canvas(modifier = modifier) {
        if (mode == HistoryViewMode.List) {
            val rowHeight = size.height / 5f
            repeat(4) { index ->
                val top = rowHeight * index + rowHeight * 0.18f
                drawRoundRect(
                    color = tile,
                    topLeft = Offset(0f, top),
                    size = Size(rowHeight * 0.64f, rowHeight * 0.64f),
                    cornerRadius = CornerRadius(2.dp.toPx()),
                )
                drawRoundRect(
                    color = line,
                    topLeft = Offset(rowHeight * 0.85f, top + rowHeight * 0.12f),
                    size = Size(size.width * 0.58f, 3.dp.toPx()),
                    cornerRadius = CornerRadius(2.dp.toPx()),
                )
                drawRoundRect(
                    color = line,
                    topLeft = Offset(size.width * 0.83f, top + rowHeight * 0.12f),
                    size = Size(size.width * 0.17f, 3.dp.toPx()),
                    cornerRadius = CornerRadius(2.dp.toPx()),
                )
            }
        } else {
            val gap = 5.dp.toPx()
            val tileWidth = (size.width - gap * 2) / 3f
            val tileHeight = (size.height - gap) / 2f
            repeat(2) { row ->
                repeat(3) { column ->
                    drawRoundRect(
                        color = tile,
                        topLeft = Offset(column * (tileWidth + gap), row * (tileHeight + gap)),
                        size = Size(tileWidth, tileHeight),
                        cornerRadius = CornerRadius(3.dp.toPx()),
                    )
                }
            }
        }
    }
}

@Composable
private fun SelectionCheck(modifier: Modifier = Modifier) {
    val color = GT.colors.ink
    val surface = GT.colors.surface
    Canvas(modifier = modifier) {
        drawCircle(color = surface, radius = size.minDimension / 2f)
        drawCircle(
            color = color,
            radius = size.minDimension / 2f - 0.5.dp.toPx(),
            style = Stroke(width = 1.dp.toPx()),
        )
        drawLine(
            color = color,
            start = Offset(size.width * 0.28f, size.height * 0.52f),
            end = Offset(size.width * 0.44f, size.height * 0.68f),
            strokeWidth = 1.4.dp.toPx(),
            cap = StrokeCap.Round,
        )
        drawLine(
            color = color,
            start = Offset(size.width * 0.44f, size.height * 0.68f),
            end = Offset(size.width * 0.74f, size.height * 0.32f),
            strokeWidth = 1.4.dp.toPx(),
            cap = StrokeCap.Round,
        )
    }
}

@Composable
private fun TileSizeSelector(
    selectedColumns: Int,
    enabled: Boolean,
    onSelect: (Int) -> Unit,
) {
    Row(
        modifier = Modifier
            .height(GT.space.touch)
            .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.iconButton)
            .padding(horizontal = 2.dp)
            .selectableGroup(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        (2..4).forEach { columns ->
            val description = stringResource(R.string.history_view_tile_columns, columns)
            Box(
                modifier = Modifier
                    .width(30.dp)
                    .fillMaxSize()
                    .selectable(
                        selected = columns == selectedColumns,
                        enabled = enabled,
                        onClick = { onSelect(columns) },
                        role = Role.RadioButton,
                    )
                    .semantics { contentDescription = description },
                contentAlignment = Alignment.Center,
            ) {
                Box(
                    modifier = Modifier
                        .size(width = 26.dp, height = 24.dp)
                        .background(
                            color = if (columns == selectedColumns) GT.colors.ink else Color.Transparent,
                            shape = GT.shapes.tag,
                        ),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = columns.toString(),
                        color = when {
                            columns == selectedColumns -> GT.colors.surface
                            enabled -> GT.colors.ink2
                            else -> GT.colors.muted
                        },
                        style = GT.type.monoLabel,
                    )
                }
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
private fun HistoryViewMode.label(): String =
    when (this) {
        HistoryViewMode.List -> stringResource(R.string.history_view_list)
        HistoryViewMode.Showcase -> stringResource(R.string.history_view_showcase)
    }

@Composable
private fun HistoryViewMode.hint(): String =
    when (this) {
        HistoryViewMode.List -> stringResource(R.string.history_view_list_hint)
        HistoryViewMode.Showcase -> stringResource(R.string.history_view_showcase_hint)
    }

private fun List<HistoryMealRowUi>.toTimelineMeals(): List<HistoryTimelineMeal> =
    mapNotNull { row ->
        val id = row.recordId ?: row.outboxId ?: return@mapNotNull null
        val time = row.eatenAt.toLocalDateTime(TimeZone.currentSystemDefault()).time
        val minutesOfDay = (time.hour * 60 + time.minute).coerceIn(0, MinutesPerDay - 1)
        HistoryTimelineMeal(
            id = id,
            minutesOfDay = minutesOfDay,
            kcal = row.totalKcal?.roundToLong()?.toInt()?.coerceAtLeast(0),
            carbsG = row.totalCarbsG,
            accepted = row.kind == HistoryMealRowKind.Accepted,
            stuck = row.status == HistoryMealStatus.Stuck,
            mainMeal = row.isMainMealForTimeline(),
            responseKey = row.responseKey,
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
private fun HistoryViewGlyph(viewMode: HistoryViewMode) {
    val color = GT.colors.ink2
    Canvas(modifier = Modifier.size(16.dp)) {
        val stroke = Stroke(width = 1.3.dp.toPx(), cap = StrokeCap.Round)
        if (viewMode == HistoryViewMode.List) {
            listOf(4f, 8f, 12f).forEach { y ->
                drawCircle(
                    color = color,
                    radius = 0.9.dp.toPx(),
                    center = Offset(2.5.dp.toPx(), y.dp.toPx()),
                )
                drawLine(
                    color,
                    Offset(5.dp.toPx(), y.dp.toPx()),
                    Offset(14.dp.toPx(), y.dp.toPx()),
                    stroke.width,
                )
            }
        } else {
            listOf(
                Offset(2.dp.toPx(), 2.dp.toPx()),
                Offset(9.dp.toPx(), 2.dp.toPx()),
                Offset(2.dp.toPx(), 9.dp.toPx()),
                Offset(9.dp.toPx(), 9.dp.toPx()),
            ).forEach { topLeft ->
                drawRoundRect(
                    color = color,
                    topLeft = topLeft,
                    size = Size(5.dp.toPx(), 5.dp.toPx()),
                    cornerRadius = CornerRadius(1.dp.toPx()),
                    style = stroke,
                )
            }
        }
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
