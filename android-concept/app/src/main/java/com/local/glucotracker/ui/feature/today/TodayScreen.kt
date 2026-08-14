package com.local.glucotracker.ui.feature.today

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
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
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Text
import androidx.compose.material3.rememberSwipeToDismissBoxState
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
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.DayTotals
import com.local.glucotracker.domain.model.SyncStatus
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.domain.model.UserGoals
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.GTTheme
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.FoodCurveMeal
import com.local.glucotracker.ui.design.primitives.FoodDayCurve
import com.local.glucotracker.ui.design.primitives.GTKicker
import com.local.glucotracker.ui.design.primitives.GTKcalRing
import com.local.glucotracker.ui.design.primitives.GTIconButton
import com.local.glucotracker.ui.design.primitives.GTKpiCard
import com.local.glucotracker.ui.design.primitives.GTMacroBar
import com.local.glucotracker.ui.design.primitives.GTMealRow
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.design.primitives.GTPhotoProcessingPipeline
import com.local.glucotracker.ui.design.primitives.GTPhotoProcessingProgressBar
import com.local.glucotracker.ui.design.primitives.GTPhotoSlot
import com.local.glucotracker.ui.feature.more.GoalsOnboardingSheet
import com.local.glucotracker.ui.format.PhotoProcessingFailureStep
import com.local.glucotracker.ui.format.PhotoProcessingStage
import com.local.glucotracker.ui.format.PhotoProcessingUiState
import com.local.glucotracker.ui.format.formatGrams
import com.local.glucotracker.ui.format.formatKcal
import com.local.glucotracker.ui.format.formatPercent
import com.local.glucotracker.ui.format.formatSignedKcal
import com.local.glucotracker.ui.format.RowState
import com.local.glucotracker.ui.format.computeRowState
import com.local.glucotracker.ui.glucose.LocalGlucoseSurfaces
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToLong
import kotlinx.coroutines.delay
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.LocalTime
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toJavaLocalDate
import kotlinx.datetime.toLocalDateTime

@Composable
fun TodayRoute(
    onOpenMealStack: (LocalDate, String) -> Unit,
    onOpenOutbox: (String) -> Unit = {},
    onOpenOutboxSummary: () -> Unit = {},
    lastQueuedOutboxId: String? = null,
    onQueuedOutboxConsumed: (String) -> Unit = {},
    brandAccentColor: Color? = null,
    initialDate: LocalDate? = null,
    showPagerDots: Boolean = true,
    pagerPage: Int = 0,
    onOpenStats: () -> Unit = {},
    onOpenMore: () -> Unit = {},
    viewModel: TodayViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var showGoalsOnboarding by remember { mutableStateOf(false) }
    LaunchedEffect(initialDate) {
        initialDate?.let(viewModel::selectDate)
    }
    LaunchedEffect(lastQueuedOutboxId) {
        val outboxId = lastQueuedOutboxId ?: return@LaunchedEffect
        delay(1_800)
        onQueuedOutboxConsumed(outboxId)
    }
    val needsGoalsOnboarding = when (val s = state) {
        is TodayState.Day -> !s.goals.goalsSetupCompleted && !s.goals.hasAnyDailyTarget()
        else -> false
    }
    LaunchedEffect(brandAccentColor, needsGoalsOnboarding) {
        if (brandAccentColor != null && needsGoalsOnboarding) {
            showGoalsOnboarding = true
        } else {
            showGoalsOnboarding = false
        }
    }
    if (showGoalsOnboarding) {
        GoalsOnboardingSheet(
            onDismiss = {
                showGoalsOnboarding = false
                viewModel.skipGoalsOnboarding()
            },
            onSaveGoals = { kcal, protein, carbs, fat ->
                showGoalsOnboarding = false
                viewModel.saveOnboardingGoals(kcal, protein, carbs, fat)
            },
            onSkip = {
                showGoalsOnboarding = false
                viewModel.skipGoalsOnboarding()
            },
        )
    }
    TodayScreen(
        state = state,
        lastQueuedOutboxId = lastQueuedOutboxId,
        onOpenRow = { row ->
            (row.recordId ?: row.outboxId)?.let { id ->
                onOpenMealStack(row.eatenAt.localDate(), id)
            }
        },
        onDeleteRow = viewModel::deleteRow,
        onOpenOutboxSummary = onOpenOutboxSummary,
        onRefresh = viewModel::refresh,
        onPreviousDay = viewModel::previousDay,
        onNextDay = viewModel::nextDay,
        onOpenStats = onOpenStats,
        onOpenMore = onOpenMore,
        brandAccentColor = brandAccentColor,
        showPagerDots = showPagerDots,
        pagerPage = pagerPage,
    )
}

@Composable
fun TodayScreen(
    state: TodayState,
    lastQueuedOutboxId: String? = null,
    onOpenRow: (TodayMealRowUi) -> Unit,
    onDeleteRow: (TodayMealRowUi) -> Unit,
    onOpenOutboxSummary: () -> Unit = {},
    onRefresh: () -> Unit,
    onPreviousDay: () -> Unit,
    onNextDay: () -> Unit,
    onOpenStats: () -> Unit,
    onOpenMore: () -> Unit = {},
    modifier: Modifier = Modifier,
    brandAccentColor: Color? = null,
    showPagerDots: Boolean = true,
    pagerPage: Int = 0,
    now: LocalTime = Clock.System.now().toLocalDateTime(TimeZone.currentSystemDefault()).time,
) {
    when (state) {
        TodayState.Loading -> LoadingState(
            modifier = modifier,
            onPreviousDay = onPreviousDay,
            onNextDay = onNextDay,
            onOpenStats = onOpenStats,
            showPagerDots = showPagerDots,
            pagerPage = pagerPage,
            brandAccentColor = brandAccentColor,
        )
        is TodayState.Empty -> EmptyState(
            state = state,
            onPreviousDay = onPreviousDay,
            onNextDay = onNextDay,
            onOpenStats = onOpenStats,
            modifier = modifier,
            brandAccentColor = brandAccentColor,
            showPagerDots = showPagerDots,
            pagerPage = pagerPage,
        )
        is TodayState.Day -> DayState(
            state = state,
            lastQueuedOutboxId = lastQueuedOutboxId,
            onOpenRow = onOpenRow,
            onDeleteRow = onDeleteRow,
            onOpenOutboxSummary = onOpenOutboxSummary,
            onPreviousDay = onPreviousDay,
            onNextDay = onNextDay,
            onOpenStats = onOpenStats,
            onOpenMore = onOpenMore,
            modifier = modifier,
            brandAccentColor = brandAccentColor,
            showPagerDots = showPagerDots,
            pagerPage = pagerPage,
            now = now,
        )
    }
}

@Composable
private fun LoadingState(
    modifier: Modifier = Modifier,
    onPreviousDay: () -> Unit,
    onNextDay: () -> Unit,
    onOpenStats: () -> Unit,
    showPagerDots: Boolean,
    pagerPage: Int,
    brandAccentColor: Color?,
) {
    val today = Clock.System.now().toLocalDateTime(TimeZone.currentSystemDefault()).date
    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .foodDaySwipe(
                enabled = brandAccentColor != null,
                canGoNext = false,
                onPreviousDay = onPreviousDay,
                onNextDay = onNextDay,
            )
            .background(GT.colors.bg),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            TodayHeader(
                date = today,
                syncStatus = SyncStatus(queueDepth = 0, lastSyncAt = null, isSyncing = false),
                canGoNext = false,
                onPreviousDay = onPreviousDay,
                onNextDay = onNextDay,
                onOpenStats = onOpenStats,
                showPagerDots = showPagerDots,
                pagerPage = pagerPage,
                modifier = Modifier.padding(horizontal = 18.dp, vertical = 10.dp),
                foodBrand = brandAccentColor != null,
            )
        }
        item {
            TodaySkeletonKpis(modifier = Modifier.padding(horizontal = 18.dp))
        }
    }
}

@Composable
private fun EmptyState(
    state: TodayState.Empty,
    onPreviousDay: () -> Unit,
    onNextDay: () -> Unit,
    onOpenStats: () -> Unit,
    modifier: Modifier = Modifier,
    brandAccentColor: Color? = null,
    showPagerDots: Boolean = true,
    pagerPage: Int = 0,
) {
    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .foodDaySwipe(
                enabled = brandAccentColor != null,
                canGoNext = state.canGoNext,
                onPreviousDay = onPreviousDay,
                onNextDay = onNextDay,
            )
            .background(GT.colors.bg),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            TodayHeader(
                date = state.date,
                syncStatus = state.syncStatus,
                canGoNext = state.canGoNext,
                onPreviousDay = onPreviousDay,
                onNextDay = onNextDay,
                onOpenStats = onOpenStats,
                showPagerDots = showPagerDots,
                pagerPage = pagerPage,
                modifier = Modifier.padding(horizontal = 18.dp, vertical = 10.dp),
                foodBrand = brandAccentColor != null,
            )
        }
        item {
            Text(
                text = if (state.canGoNext) {
                    stringResource(R.string.today_empty_day)
                } else {
                    stringResource(R.string.today_empty)
                },
                modifier = Modifier.padding(horizontal = 24.dp, vertical = 32.dp),
                color = GT.colors.ink2,
                style = GT.type.serifSection,
            )
        }
    }
}

@Composable
private fun DayState(
    state: TodayState.Day,
    lastQueuedOutboxId: String?,
    onOpenRow: (TodayMealRowUi) -> Unit,
    onDeleteRow: (TodayMealRowUi) -> Unit,
    onOpenOutboxSummary: () -> Unit,
    onPreviousDay: () -> Unit,
    onNextDay: () -> Unit,
    onOpenStats: () -> Unit,
    onOpenMore: () -> Unit = {},
    modifier: Modifier = Modifier,
    brandAccentColor: Color? = null,
    showPagerDots: Boolean = true,
    pagerPage: Int = 0,
    now: LocalTime = Clock.System.now().toLocalDateTime(TimeZone.currentSystemDefault()).time,
) {
    var deleteCandidate by remember { mutableStateOf<TodayMealRowUi?>(null) }

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg),
    ) {
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .foodDaySwipe(
                    enabled = brandAccentColor != null,
                    canGoNext = state.canGoNext,
                    onPreviousDay = onPreviousDay,
                    onNextDay = onNextDay,
                ),
            verticalArrangement = Arrangement.spacedBy(if (brandAccentColor != null) 0.dp else 14.dp),
        ) {
            item {
                TodayHeader(
                    date = state.date,
                    syncStatus = state.syncStatus,
                    canGoNext = state.canGoNext,
                    onPreviousDay = onPreviousDay,
                    onNextDay = onNextDay,
                    onOpenStats = onOpenStats,
                    showPagerDots = showPagerDots,
                    pagerPage = pagerPage,
                    modifier = if (brandAccentColor != null) {
                        Modifier.padding(start = 18.dp, top = 10.dp, end = 18.dp, bottom = 6.dp)
                    } else {
                        Modifier.padding(horizontal = 18.dp, vertical = 10.dp)
                    },
                    foodBrand = brandAccentColor != null,
                )
            }
            item {
                if (brandAccentColor == null) {
                    // Full bleed: the band is ruled edge to edge, so it must
                    // not sit inside the page's card margin.
                    TodayKpiGrid(
                        date = state.date,
                        totals = state.totals,
                        goals = state.goals,
                        pendingQueueCount = state.pendingQueueCount,
                    )
                } else {
                    FoodTodaySummary(
                        state = state,
                        modifier = Modifier.padding(horizontal = 18.dp),
                    )
                }
            }
            photoProcessingSummary(state.rows)?.let { summary ->
                item {
                    PhotoProcessingSummaryBanner(
                        summary = summary,
                        onClick = onOpenOutboxSummary,
                        modifier = Modifier.padding(horizontal = 18.dp),
                    )
                }
            }
            if (brandAccentColor != null) {
                item {
                    FoodMealJournal(
                        rows = state.rows,
                        dailyKcalGoal = state.goals.dailyKcal,
                        lastAddedId = lastQueuedOutboxId ?: state.lastAddedId,
                        isOnline = state.isOnline,
                        onOpenRow = onOpenRow,
                        onDeleteRow = { candidate -> deleteCandidate = candidate },
                    )
                }
                item {
                    FoodDayCurveSection(
                        rows = state.rows,
                        totals = state.totals,
                        dailyKcalGoal = state.goals.dailyKcal,
                        modifier = Modifier.padding(horizontal = 18.dp),
                    )
                }
            } else {
                item {
                    LocalGlucoseSurfaces.current.TodayRows(
                        date = state.date,
                        rows = state.rows,
                    ) { row, framed, showTime, kindColor, extraMetaContent ->
                        SwipeMealRow(
                            row = row,
                            lastAddedId = lastQueuedOutboxId ?: state.lastAddedId,
                            onOpenRow = onOpenRow,
                            onDeleteRow = { candidate -> deleteCandidate = candidate },
                            isOnline = state.isOnline,
                            framed = framed,
                            showTime = showTime,
                            kindColor = kindColor,
                            extraMetaContent = extraMetaContent,
                        )
                    }
                }
                item {
                    Column {
                        LocalGlucoseSurfaces.current.MiniGlucoseCard(
                            modifier = Modifier.padding(horizontal = 18.dp),
                        )
                        Spacer(Modifier.height(10.dp))
                    }
                }
            }
        }

        deleteCandidate?.let { candidate ->
            TodayDeleteConfirmSheet(
                onDismiss = { deleteCandidate = null },
                onConfirm = {
                    deleteCandidate = null
                    onDeleteRow(candidate)
                },
                modifier = Modifier.align(Alignment.BottomCenter),
            )
        }
    }
}

@Composable
private fun TodayHeader(
    date: LocalDate,
    syncStatus: SyncStatus,
    canGoNext: Boolean,
    onPreviousDay: () -> Unit,
    onNextDay: () -> Unit,
    onOpenStats: () -> Unit,
    showPagerDots: Boolean,
    pagerPage: Int,
    modifier: Modifier = Modifier,
    foodBrand: Boolean = false,
) {
    if (foodBrand) {
        FoodTodayHeader(
            date = date,
            canGoNext = canGoNext,
            onPreviousDay = onPreviousDay,
            onNextDay = onNextDay,
            modifier = modifier,
        )
        return
    }
    Column(modifier = modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(if (foodBrand) 20.dp else 28.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (showPagerDots) {
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    repeat(2) { index ->
                        Box(
                            modifier = Modifier
                                .size(4.dp)
                                .background(
                                    color = if (pagerPage == index) GT.colors.ink else Color.Transparent,
                                    shape = androidx.compose.foundation.shape.CircleShape,
                                )
                                .border(
                                    width = GT.space.hairline,
                                    color = if (pagerPage == index) GT.colors.ink else GT.colors.hairline2,
                                    shape = androidx.compose.foundation.shape.CircleShape,
                                ),
                        )
                    }
                }
                Spacer(Modifier.width(6.dp))
            }
            GTKicker(text = weekday(date))
            Spacer(Modifier.weight(1f))
            if (!foodBrand) {
                Text(
                    text = stringResource(R.string.today_stats_action),
                    modifier = Modifier
                        .heightIn(min = 28.dp)
                        .clickable(onClick = onOpenStats)
                        .padding(start = 10.dp, top = 6.dp),
                    color = GT.colors.ink2,
                    style = GT.type.sansLabel.copy(fontSize = 11.5.sp),
                    maxLines = 1,
                )
            }
        }
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(44.dp)
                .padding(top = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            val dateText = if (foodBrand) foodDateTitle(date) else dateTitle(date)
            val dateContentDescription = stringResource(
                R.string.today_date_content_description,
                dateText,
                weekdaySpoken(date),
            )
            Text(
                text = dateText,
                modifier = Modifier
                    .weight(1f)
                    .semantics {
                        contentDescription = dateContentDescription
                    },
                color = GT.colors.ink,
                style = if (foodBrand) {
                    GT.type.serifTitle.copy(fontSize = 32.sp)
                } else {
                    // Smaller than it was: the date was the largest thing on a
                    // screen where it is the least actionable, while the
                    // episode outcome sat at ten point in a corner.
                    GT.type.serifTitle.copy(fontSize = 24.sp)
                },
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                DayNavButton(
                    text = if (foodBrand) "‹" else "◀",
                    contentDescription = stringResource(R.string.today_previous_day_content_description),
                    onClick = onPreviousDay,
                )
                DayNavButton(
                    text = if (foodBrand) "›" else "▶",
                    contentDescription = stringResource(R.string.today_next_day_content_description),
                    onClick = onNextDay,
                    enabled = canGoNext,
                )
            }
        }
        GTHairlineDivider(modifier = Modifier.padding(top = 10.dp))
    }
}

@Composable
private fun DayNavButton(
    text: String,
    contentDescription: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    GTIconButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.semantics {
            this.contentDescription = contentDescription
        },
    ) {
        Text(
            text = text,
            color = if (enabled) GT.colors.ink2 else GT.colors.muted.copy(alpha = 0.45f),
            style = GT.type.sansLabel,
            maxLines = 1,
        )
    }
}

@Composable
private fun TodaySkeletonKpis(modifier: Modifier = Modifier) {
    Column(modifier = modifier) {
        repeat(2) { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                repeat(2) {
                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .height(92.dp)
                            .background(GT.colors.surface, GT.shapes.card)
                            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
                            .padding(GT.space.md),
                    ) {
                        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth(0.44f)
                                    .height(9.dp)
                                    .background(GT.colors.hairline, GT.shapes.tag),
                            )
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth(0.7f)
                                    .height(22.dp)
                                    .background(GT.colors.hairline, GT.shapes.tag),
                            )
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth(0.55f)
                                    .height(8.dp)
                                    .background(GT.colors.hairline, GT.shapes.tag),
                            )
                        }
                    }
                }
            }
            if (row == 0) Spacer(Modifier.height(10.dp))
        }
    }
}

/**
 * The day's totals as one band instead of four cards.
 *
 * Two rows of KPI cards spent most of a phone screen on four numbers and their
 * borders, so the day's records — the thing the screen is for — started below
 * the fold. The same four numbers now read in one band: the headline against
 * its goal, one progress line, and the rest as a row of columns.
 *
 * Ruled top and bottom rather than boxed. Inside a screen already made of
 * cards, a band is what says "this is the day, the cards below are its parts".
 */
@Composable
private fun TodayKpiGrid(
    date: LocalDate,
    totals: DayTotals,
    goals: UserGoals,
    pendingQueueCount: Int,
    modifier: Modifier = Modifier,
) {
    val kcalGoal = goals.dailyKcal
    val remaining = kcalGoal?.let { it - totals.kcal }
    val hairlineColor = GT.colors.hairline
    Column(
        modifier = modifier
            .fillMaxWidth()
            .drawBehind {
                val stroke = 1.dp.toPx()
                drawRect(
                    color = hairlineColor,
                    topLeft = Offset(0f, 0f),
                    size = Size(size.width, stroke),
                )
                drawRect(
                    color = hairlineColor,
                    topLeft = Offset(0f, size.height - stroke),
                    size = Size(size.width, stroke),
                )
            }
            .padding(horizontal = 18.dp)
            .padding(top = 12.dp, bottom = 12.dp),
    ) {
        Row(verticalAlignment = Alignment.Bottom) {
            Text(
                text = formatKcal(totals.kcal),
                color = GT.colors.ink,
                style = GT.type.monoNumber.copy(fontSize = 28.sp),
                maxLines = 1,
            )
            kcalGoal?.let { goal ->
                Text(
                    text = stringResource(R.string.today_kpi_of_goal, formatKcal(goal)),
                    modifier = Modifier.padding(start = 7.dp, bottom = 3.dp),
                    color = GT.colors.muted,
                    style = GT.type.monoLabel.copy(fontSize = 12.sp),
                    maxLines = 1,
                )
            }
            Spacer(Modifier.weight(1f))
            remaining?.let {
                Text(
                    text = formatSignedKcal(it.roundToLong()),
                    modifier = Modifier.padding(bottom = 3.dp),
                    color = GT.colors.accent,
                    style = GT.type.monoLabel.copy(fontSize = 12.sp),
                    maxLines = 1,
                )
            }
        }
        Box(
            modifier = Modifier
                .padding(top = 9.dp)
                .fillMaxWidth()
                .height(3.dp)
                .background(GT.colors.hairline, GT.shapes.tag),
        ) {
            Box(
                modifier = Modifier
                    .fillMaxWidth(progressOf(totals.kcal, kcalGoal))
                    .height(3.dp)
                    .background(GT.colors.accent, GT.shapes.tag),
            )
        }
        Row(modifier = Modifier.padding(top = 11.dp)) {
            TodayStat(
                label = stringResource(R.string.today_kpi_protein),
                value = formatGrams(totals.proteinG),
                modifier = Modifier.weight(1f),
            )
            TodayStat(
                label = stringResource(R.string.today_kpi_carbs),
                value = formatGrams(totals.carbsG),
                modifier = Modifier.weight(1f),
            )
            val drewGlucoseStat = LocalGlucoseSurfaces.current.TodayGlucoseStat(
                modifier = Modifier.weight(1f),
            )
            if (!drewGlucoseStat) {
                TodayStat(
                    label = stringResource(R.string.today_kpi_remaining),
                    value = remaining?.let { formatSignedKcal(it.roundToLong()) } ?: "—",
                    modifier = Modifier.weight(1f),
                )
            }
        }
        pendingQueueCount.takeIf { it > 0 }?.let { queued ->
            Text(
                text = stringResource(R.string.today_kpi_queue_kicker, queued),
                modifier = Modifier.padding(top = 8.dp),
                color = GT.colors.muted,
                style = GT.type.monoLabel.copy(fontSize = 10.sp),
                maxLines = 1,
            )
        }
        LocalGlucoseSurfaces.current.TodayBodyStates(
            date = date,
            modifier = Modifier.padding(top = 10.dp),
        )
    }
}

/** One column of the day band: a kicker over a number. */
@Composable
private fun TodayStat(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
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
            text = value,
            modifier = Modifier.padding(top = 3.dp),
            color = GT.colors.ink,
            style = GT.type.monoNumber.copy(fontSize = 16.sp),
            maxLines = 1,
        )
    }
}

@Composable
private fun FoodTodaySummary(
    state: TodayState.Day,
    modifier: Modifier = Modifier,
) {
    val totals = state.totals
    val goals = state.goals
    val kcalGoal = goals.dailyKcal
    val remaining = kcalGoal?.let { it - totals.kcal }
    val hairline = GT.colors.hairline
    val hairlineWidth = GT.space.hairline
    Column(
        modifier = modifier
            .fillMaxWidth()
            .drawBehind {
                val stroke = hairlineWidth.toPx()
                drawLine(hairline, Offset(0f, 0f), Offset(size.width, 0f), stroke)
                drawLine(hairline, Offset(0f, size.height), Offset(size.width, size.height), stroke)
            }
            .padding(vertical = 12.dp),
    ) {
        Row(verticalAlignment = Alignment.Bottom) {
            Text(
                text = formatKcal(totals.kcal),
                color = GT.colors.ink,
                style = GT.type.monoNumber.copy(fontSize = 30.sp),
                maxLines = 1,
            )
            kcalGoal?.let { goal ->
                Text(
                    text = stringResource(R.string.today_kpi_of_goal, formatKcal(goal)),
                    modifier = Modifier.padding(start = 8.dp, bottom = 4.dp),
                    color = GT.colors.muted,
                    style = GT.type.monoLabel.copy(fontSize = 12.sp),
                    maxLines = 1,
                )
            }
            Spacer(Modifier.weight(1f))
            remaining?.let { value ->
                Text(
                    text = if (value >= 0) {
                        stringResource(R.string.food_today_remaining, formatKcal(value))
                    } else {
                        stringResource(R.string.food_today_over, formatKcal(-value))
                    },
                    modifier = Modifier.padding(bottom = 4.dp),
                    color = if (value >= 0) GT.colors.accent else GT.colors.warn,
                    style = GT.type.monoLabel.copy(fontSize = 11.sp),
                    maxLines = 1,
                )
            }
        }
        Box(
            modifier = Modifier
                .padding(top = 9.dp)
                .fillMaxWidth()
                .height(3.dp)
                .background(GT.colors.hairline, GT.shapes.tag),
        ) {
            Box(
                modifier = Modifier
                    .fillMaxWidth(progressOf(totals.kcal, kcalGoal))
                    .height(3.dp)
                    .background(GT.colors.accent, GT.shapes.tag),
            )
        }
        Row(
            modifier = Modifier.padding(top = 11.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            FoodMacroStat(
                label = stringResource(R.string.today_kpi_protein),
                value = totals.proteinG,
                goal = goals.dailyProteinG,
                modifier = Modifier.weight(1f),
            )
            FoodMacroStat(
                label = stringResource(R.string.today_kpi_fat),
                value = totals.fatG,
                goal = goals.dailyFatG,
                modifier = Modifier.weight(1f),
            )
            FoodMacroStat(
                label = stringResource(R.string.today_kpi_carbs),
                value = totals.carbsG,
                goal = goals.dailyCarbsG,
                modifier = Modifier.weight(1f),
            )
        }
        if (state.pendingQueueCount > 0) {
            Text(
                text = stringResource(R.string.today_kpi_queue_kicker, state.pendingQueueCount),
                color = GT.colors.muted,
                style = GT.type.monoLabel,
                maxLines = 1,
            )
        }
    }
}

@Composable
private fun FoodTodayHeader(
    date: LocalDate,
    canGoNext: Boolean,
    onPreviousDay: () -> Unit,
    onNextDay: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val dateText = date.toJavaLocalDate()
        .format(DateTimeFormatter.ofPattern("d MMMM", Locale("ru")))
    val dateContentDescription = stringResource(
        R.string.today_date_content_description,
        dateText,
        weekdaySpoken(date),
    )
    Column(modifier = modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.Bottom,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                GTKicker(text = weekday(date))
                Text(
                    text = dateText,
                    modifier = Modifier
                        .padding(top = 3.dp)
                        .semantics { contentDescription = dateContentDescription },
                    color = GT.colors.ink,
                    style = GT.type.serifTitle.copy(fontSize = 27.sp),
                    maxLines = 1,
                )
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                FoodDayNavButton(
                    text = "‹",
                    contentDescription = stringResource(R.string.today_previous_day_content_description),
                    onClick = onPreviousDay,
                )
                FoodDayNavButton(
                    text = "›",
                    contentDescription = stringResource(R.string.today_next_day_content_description),
                    onClick = onNextDay,
                    enabled = canGoNext,
                )
            }
        }
    }
}

private fun Modifier.foodDaySwipe(
    enabled: Boolean,
    canGoNext: Boolean,
    onPreviousDay: () -> Unit,
    onNextDay: () -> Unit,
): Modifier = if (!enabled) {
    this
} else {
    pointerInput(canGoNext, onPreviousDay, onNextDay) {
        var horizontalDrag = 0f
        val threshold = 64.dp.toPx()
        detectHorizontalDragGestures(
            onDragStart = { horizontalDrag = 0f },
            onDragCancel = { horizontalDrag = 0f },
            onDragEnd = {
                when {
                    horizontalDrag > threshold -> onPreviousDay()
                    horizontalDrag < -threshold && canGoNext -> onNextDay()
                }
                horizontalDrag = 0f
            },
            onHorizontalDrag = { _, dragAmount -> horizontalDrag += dragAmount },
        )
    }
}

@Composable
private fun FoodDayNavButton(
    text: String,
    contentDescription: String,
    onClick: () -> Unit,
    enabled: Boolean = true,
) {
    Box(
        modifier = Modifier
            .size(GT.space.touch)
            .semantics { this.contentDescription = contentDescription }
            .clickable(enabled = enabled, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = text,
            color = if (enabled) GT.colors.ink2 else GT.colors.muted.copy(alpha = 0.45f),
            style = GT.type.sansLabel.copy(fontSize = 14.sp),
            maxLines = 1,
        )
    }
}

@Composable
private fun FoodMacroStat(
    label: String,
    value: Double,
    goal: Int?,
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier) {
        Text(
            text = label.uppercase(Locale("ru")),
            color = GT.colors.muted,
            style = GT.type.kicker.copy(fontSize = 9.5.sp),
            maxLines = 1,
        )
        Text(
            text = stringResource(R.string.today_macro_value, formatGrams(value)),
            modifier = Modifier.padding(top = 3.dp),
            color = GT.colors.ink,
            style = GT.type.monoNumber.copy(fontSize = 16.sp),
            maxLines = 1,
        )
        Box(
            modifier = Modifier
                .padding(top = 5.dp)
                .fillMaxWidth()
                .height(2.dp)
                .background(GT.colors.hairline),
        ) {
            Box(
                modifier = Modifier
                    .fillMaxWidth(progressOf(value, goal))
                    .height(2.dp)
                    .background(GT.colors.muted),
            )
        }
    }
}

@Composable
private fun FoodMealJournal(
    rows: List<TodayMealRowUi>,
    dailyKcalGoal: Int?,
    lastAddedId: String?,
    isOnline: Boolean,
    onOpenRow: (TodayMealRowUi) -> Unit,
    onDeleteRow: (TodayMealRowUi) -> Unit,
) {
    val groups = remember(rows) { foodMealGroups(rows) }
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 18.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        groups.forEach { group ->
            val groupColor = if (group.isSnack) GT.colors.kindSnack else GT.colors.kindMeal
            val kcal = group.rows.sumOf { it.totalKcal ?: 0.0 }
            val protein = group.rows.sumOf { it.totalProteinG ?: 0.0 }
            val fat = group.rows.sumOf { it.totalFatG ?: 0.0 }
            val carbs = group.rows.sumOf { it.totalCarbsG ?: 0.0 }
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(GT.shapes.card)
                    .background(GT.colors.surface)
                    .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card),
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Box(
                        modifier = Modifier
                            .size(7.dp)
                            .background(groupColor, GT.shapes.tag),
                    )
                    Text(
                        text = group.timeText,
                        modifier = Modifier.padding(start = 11.dp),
                        color = GT.colors.ink2,
                        style = GT.type.monoLabel.copy(fontSize = 10.5.sp),
                    )
                    Text(
                        text = " · ${group.roleLabel()}${if (group.rows.size > 1) " ${group.rows.size}×" else ""}",
                        modifier = Modifier.weight(1f),
                        color = GT.colors.ink2,
                        style = GT.type.monoLabel.copy(fontSize = 10.5.sp),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        text = stringResource(R.string.today_right_kcal, formatKcal(kcal)),
                        color = GT.colors.muted,
                        style = GT.type.monoLabel.copy(fontSize = 10.5.sp),
                        maxLines = 1,
                    )
                }
                group.rows.forEach { row ->
                    GTHairlineDivider(modifier = Modifier.padding(horizontal = 12.dp))
                    SwipeMealRow(
                        row = row,
                        lastAddedId = lastAddedId,
                        onOpenRow = onOpenRow,
                        onDeleteRow = onDeleteRow,
                        isOnline = isOnline,
                        compact = true,
                        framed = false,
                        showTime = false,
                        kindColor = groupColor,
                    )
                }
                if (group.rows.all { it.kind == TodayMealRowKind.Accepted }) {
                    GTHairlineDivider(modifier = Modifier.padding(horizontal = 12.dp))
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { group.rows.firstOrNull()?.let(onOpenRow) }
                            .padding(horizontal = 12.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            text = stringResource(
                                R.string.today_macros_line,
                                formatGrams(protein),
                                formatGrams(fat),
                                formatGrams(carbs),
                            ),
                            modifier = Modifier.weight(1f),
                            color = GT.colors.muted,
                            style = GT.type.monoLabel.copy(fontSize = 10.sp),
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        dailyKcalGoal?.takeIf { it > 0 }?.let { goal ->
                            Text(
                                text = stringResource(
                                    R.string.food_meal_footer_share,
                                    formatPercent(kcal / goal * 100.0),
                                ),
                                color = GT.colors.muted,
                                style = GT.type.monoLabel.copy(fontSize = 10.sp),
                                maxLines = 1,
                            )
                            Spacer(Modifier.width(7.dp))
                        }
                        Text(
                            text = stringResource(R.string.food_meal_analysis).uppercase(Locale("ru")),
                            color = GT.colors.ink2,
                            style = GT.type.monoLabel.copy(fontSize = 10.sp),
                            maxLines = 1,
                        )
                    }
                }
            }
        }
    }
}

internal data class FoodMealGroup(val rows: List<TodayMealRowUi>) {
    val isSnack: Boolean
        get() = rows.all { row -> row.mealRole?.lowercase() in FoodSnackRoles } ||
            (rows.size == 1 && (rows.first().totalKcal ?: 0.0) < 200.0)

    val timeText: String
        get() = rows.minByOrNull { it.eatenAt }?.eatenAt?.timeText().orEmpty()
}

internal fun foodMealGroups(rows: List<TodayMealRowUi>): List<FoodMealGroup> {
    val groups = mutableListOf<MutableList<TodayMealRowUi>>()
    rows.sortedByDescending { it.eatenAt }.forEach { row ->
        val current = groups.lastOrNull()
        val closest = current?.lastOrNull()
        val gapSeconds = closest?.let { kotlin.math.abs(it.eatenAt.epochSeconds - row.eatenAt.epochSeconds) }
        if (current != null && gapSeconds != null && gapSeconds <= FoodSittingWindowSeconds) {
            current += row
        } else {
            groups += mutableListOf(row)
        }
    }
    return groups.map { FoodMealGroup(it) }
}

@Composable
private fun FoodMealGroup.roleLabel(): String {
    val roles = rows.mapNotNull { it.mealRole?.lowercase() }.toSet()
    val label = when {
        "breakfast" in roles -> stringResource(R.string.food_meal_role_breakfast)
        "lunch" in roles -> stringResource(R.string.food_meal_role_lunch)
        "dinner" in roles -> stringResource(R.string.food_meal_role_dinner)
        isSnack -> stringResource(R.string.food_meal_role_snack)
        else -> stringResource(R.string.food_meal_role_meal)
    }
    return label.uppercase(Locale("ru"))
}

@Composable
private fun FoodDayCurveSection(
    rows: List<TodayMealRowUi>,
    totals: DayTotals,
    dailyKcalGoal: Int?,
    modifier: Modifier = Modifier,
) {
    val acceptedRows = rows.filter { it.kind == TodayMealRowKind.Accepted }
    val meals = foodMealGroups(acceptedRows).map { group ->
        val representative = group.rows.minBy { it.eatenAt }
        val localTime = representative.eatenAt.toLocalDateTime(TimeZone.currentSystemDefault()).time
        FoodCurveMeal(
            minutesOfDay = localTime.hour * 60 + localTime.minute,
            kcal = group.rows.sumOf { it.totalKcal ?: 0.0 },
            kind = if (group.isSnack) {
                FoodCurveMeal.Kind.Snack
            } else {
                FoodCurveMeal.Kind.Meal
            },
            id = representative.recordId ?: representative.outboxId,
        )
    }
    Column(modifier = modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = stringResource(R.string.food_curve_title).uppercase(Locale("ru")),
                modifier = Modifier.weight(1f),
                color = GT.colors.muted,
                style = GT.type.kicker,
            )
            dailyKcalGoal?.takeIf { it > 0 }?.let { goal ->
                Text(
                    text = stringResource(
                        R.string.food_curve_share,
                        formatPercent(totals.kcal / goal * 100.0),
                    ),
                    color = GT.colors.muted,
                    style = GT.type.monoLabel.copy(fontSize = 10.sp),
                )
            }
        }
        FoodDayCurve(
            meals = meals,
            totalKcal = totals.kcal,
            goalKcal = dailyKcalGoal,
            contentDescription = stringResource(
                R.string.food_curve_content_description,
                formatKcal(totals.kcal),
            ),
            modifier = Modifier
                .padding(top = 6.dp)
                .fillMaxWidth()
                .height(64.dp),
        )
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            FoodCurveHourLabels.forEach { hour ->
                Text(
                    text = hour,
                    color = GT.colors.hairline2,
                    style = GT.type.monoLabel.copy(fontSize = 9.sp),
                )
            }
        }
        Spacer(Modifier.height(10.dp))
    }
}

private val FoodSnackRoles = setOf("snack", "drink", "dessert")
private val FoodCurveHourLabels = listOf("00", "06", "12", "18", "24")
private const val FoodSittingWindowSeconds = 10 * 60L

@Composable
private fun MealListHeader(
    rows: List<TodayMealRowUi>,
    modifier: Modifier = Modifier,
) {
    val acceptedRows = rows.filter { it.kind == TodayMealRowKind.Accepted }
    val photoCount = acceptedRows.count { it.source == TodayMealSource.Photo }
    Row(
        modifier = modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        GTKicker(text = stringResource(R.string.today_page_label))
        Spacer(Modifier.weight(1f))
        Text(
            text = stringResource(R.string.today_meal_list_meta, acceptedRows.size, photoCount),
            color = GT.colors.muted,
            style = GT.type.monoLabel,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

private data class PhotoProcessingSummary(
    val title: String,
    val helper: String,
)

private fun photoProcessingSummary(rows: List<TodayMealRowUi>): PhotoProcessingSummary? {
    val states = rows
        .mapNotNull { row -> row.photoProcessing }
        .filterNot { state -> state.stage == PhotoProcessingStage.Done }
    val estimateStuckCount = states.count { state ->
        state.stage == PhotoProcessingStage.Stuck &&
            state.failureStep == PhotoProcessingFailureStep.Estimate
    }
    if (estimateStuckCount > 0) {
        return PhotoProcessingSummary(
            title = "$estimateStuckCount фото без оценки · исправляем",
            helper = "Обновление запустит восстановление",
        )
    }
    val uploadStuckCount = states.count { state -> state.stage == PhotoProcessingStage.Stuck }
    if (uploadStuckCount > 0) {
        return PhotoProcessingSummary(
            title = "$uploadStuckCount не отправилось · посмотреть",
            helper = "Нажмите, чтобы посмотреть очередь",
        )
    }
    val activeCount = states.count { state ->
        state.stage == PhotoProcessingStage.Captured ||
            state.stage == PhotoProcessingStage.WaitingUpload ||
            state.stage == PhotoProcessingStage.Uploading ||
            state.stage == PhotoProcessingStage.Estimating
    }
    return activeCount.takeIf { it > 0 }?.let {
        val verb = if (it == 1) "обрабатывается" else "обрабатываются"
        PhotoProcessingSummary(
            title = "$it фото $verb · обычно до 90 сек",
            helper = "Нажмите, чтобы посмотреть очередь",
        )
    }
}

@Composable
private fun PhotoProcessingSummaryBanner(
    summary: PhotoProcessingSummary,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(3.dp),
    ) {
        Text(
            text = summary.title,
            color = GT.colors.ink2,
            style = GT.type.sansLabel,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Text(
            text = summary.helper,
            color = GT.colors.muted,
            style = GT.type.monoLabel,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SwipeMealRow(
    row: TodayMealRowUi,
    lastAddedId: String?,
    onOpenRow: (TodayMealRowUi) -> Unit,
    onDeleteRow: (TodayMealRowUi) -> Unit,
    isOnline: Boolean = true,
    compact: Boolean = false,
    framed: Boolean = true,
    showTime: Boolean = true,
    kindColor: Color? = null,
    extraMetaContent: @Composable ColumnScope.() -> Unit = {},
) {
    val canDeleteLocally = row.recordId == null && row.outboxId != null
    if (!canDeleteLocally) {
        MealRowSurface(
            row = row,
            lastAddedId = lastAddedId,
            onOpenRow = onOpenRow,
            isOnline = isOnline,
            compact = compact,
            framed = framed,
            showTime = showTime,
            kindColor = kindColor,
            extraMetaContent = extraMetaContent,
        )
        return
    }

    val dismissState = rememberSwipeToDismissBoxState(
        confirmValueChange = { value ->
            if (value == SwipeToDismissBoxValue.EndToStart) {
                onDeleteRow(row)
            }
            false
        },
    )
    SwipeToDismissBox(
        state = dismissState,
        enableDismissFromStartToEnd = false,
        backgroundContent = {
            DismissBackground(row = row)
        },
    ) {
        MealRowSurface(
            row = row,
            lastAddedId = lastAddedId,
            onOpenRow = onOpenRow,
            isOnline = isOnline,
            compact = compact,
            framed = framed,
            showTime = showTime,
            kindColor = kindColor,
            extraMetaContent = extraMetaContent,
        )
    }
}

@Composable
private fun DismissBackground(row: TodayMealRowUi) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(GT.colors.surface2)
            .padding(horizontal = 18.dp),
        contentAlignment = Alignment.CenterEnd,
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            if (row.kind == TodayMealRowKind.Accepted) {
                Text(
                    text = stringResource(R.string.today_duplicate),
                    color = GT.colors.muted,
                    style = GT.type.sansLabel,
                )
            }
            Text(
                text = stringResource(R.string.today_delete),
                color = GT.colors.warn,
                style = GT.type.sansLabel,
            )
        }
    }
}

@Composable
private fun TodayDeleteConfirmSheet(
    onDismiss: () -> Unit,
    onConfirm: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(GT.colors.surface)
            .border(GT.space.hairline, GT.colors.hairline)
            .navigationBarsPadding()
            .padding(GT.space.lg),
        verticalArrangement = Arrangement.spacedBy(GT.space.sm),
    ) {
        Text(
            text = stringResource(R.string.record_delete_confirm_title),
            color = GT.colors.ink,
            style = GT.type.serifSection,
        )
        Text(
            text = stringResource(R.string.record_delete_confirm_body),
            color = GT.colors.ink2,
            style = GT.type.sansBody,
        )
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(GT.space.md),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            GTOutlineButton(text = stringResource(R.string.record_delete_cancel), onClick = onDismiss)
            Spacer(Modifier.weight(1f))
            Text(
                text = stringResource(R.string.record_delete_confirm),
                modifier = Modifier
                    .heightIn(min = GT.space.touch)
                    .clickable(onClick = onConfirm)
                    .padding(horizontal = GT.space.sm, vertical = 12.dp),
                color = GT.colors.warn,
                style = GT.type.sansLabel,
            )
        }
    }
}

@Composable
private fun MealRowSurface(
    row: TodayMealRowUi,
    lastAddedId: String?,
    onOpenRow: (TodayMealRowUi) -> Unit,
    isOnline: Boolean = true,
    compact: Boolean = false,
    framed: Boolean = true,
    showTime: Boolean = true,
    kindColor: Color? = null,
    extraMetaContent: @Composable ColumnScope.() -> Unit = {},
) {
    var highlighted by remember(row.id, lastAddedId) { mutableStateOf(row.id == lastAddedId) }
    val bg by animateColorAsState(
        targetValue = if (highlighted) GT.colors.bg else GT.colors.surface,
        animationSpec = tween(1500),
        label = "meal-highlight",
    )

    LaunchedEffect(highlighted) {
        if (highlighted) highlighted = false
    }

    val hasDestination = row.recordId != null || row.outboxId != null
    val clickModifier = if (hasDestination) {
        Modifier.clickable { onOpenRow(row) }
    } else {
        Modifier
    }

    // framed = false: the row sits inside a shared episode card, so it gets no
    // outer margin, border, or rounded surface of its own — only its click and
    // just-added highlight.
    val surfaceModifier = if (framed) {
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 18.dp)
            .background(bg, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
    } else {
        // Opaque, not transparent. A row inside a card sits on top of the
        // swipe-to-delete background, and a transparent one let «Удалить»
        // show through the entry that had not been swiped at all.
        Modifier
            .fillMaxWidth()
            .background(if (highlighted) bg else GT.colors.surface)
    }

    Box(
        modifier = surfaceModifier.then(clickModifier),
    ) {
        val photoProcessing = row.photoProcessing
        if (photoProcessing != null && row.kind == TodayMealRowKind.Pending && row.source == TodayMealSource.Photo) {
            PendingPhotoMealRow(
                time = row.eatenAt.timeText(),
                photo = row.photo,
                state = photoProcessing,
                hasDestination = hasDestination,
            )
        } else {
            GTMealRow(
                // Blank where the row above it already stated this minute.
                time = if (showTime) row.eatenAt.timeText() else "",
                // framed = false means the row sits in a sitting card whose
                // header states the time, so no row in it wants a gutter.
                reserveTimeGutter = framed,
                kindColor = kindColor,
                photo = row.photo,
                name = row.title ?: fallbackTitle(row),
                // The time used to be repeated here under the title, beside a
                // word naming the source. The gutter already gives the time,
                // and the thumbnail already says it came from a photo.
                meta = row.pendingErrorText() ?: sourceMeta(row.source),
                primaryRight = primaryRightText(row, isOnline),
                secondaryRight = secondaryRightText(row),
                status = null,
                muted = row.kind == TodayMealRowKind.Pending,
                primaryRightColor = if (row.isAgedPending) GT.colors.warn else null,
                compact = compact,
                extraMetaContent = extraMetaContent,
            )
        }
    }
}

@Composable
private fun PendingPhotoMealRow(
    time: String,
    photo: Any?,
    state: PhotoProcessingUiState,
    hasDestination: Boolean,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = 98.dp)
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Text(
            text = time,
            modifier = Modifier.width(36.dp),
            color = GT.colors.muted,
            style = GT.type.monoLabel,
            maxLines = 1,
        )
        GTPhotoSlot(model = photo, modifier = Modifier.size(32.dp))
        Column(
            modifier = Modifier
                .weight(1f)
                .padding(start = 10.dp, end = 8.dp),
            verticalArrangement = Arrangement.spacedBy(7.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = state.title,
                    modifier = Modifier.weight(1f),
                    color = GT.colors.ink2,
                    style = GT.type.sansLabel,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                if (hasDestination) {
                    Text(
                        text = "\u2192",
                        color = GT.colors.muted,
                        style = GT.type.sansLabel,
                        maxLines = 1,
                    )
                }
            }
            Text(
                text = state.statusText,
                color = if (state.stage == PhotoProcessingStage.Stuck) GT.colors.warn else GT.colors.muted,
                style = GT.type.monoLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (state.stage == PhotoProcessingStage.Uploading) {
                GTPhotoProcessingProgressBar(progress = state.uploadProgress)
            }
            GTPhotoProcessingPipeline(state = state)
            state.helperText?.let { helper ->
                Text(
                    text = helper,
                    color = GT.colors.muted,
                    style = GT.type.sansLabel.copy(fontSize = 11.sp),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
private fun fallbackTitle(row: TodayMealRowUi): String =
    if (row.source == TodayMealSource.Photo && row.kind == TodayMealRowKind.Pending) {
        stringResource(R.string.today_pending_photo_title)
    } else {
        stringResource(R.string.today_meal_fallback)
    }

/**
 * The source, except when the thumbnail beside it has already said so.
 *
 * A photo row carried the word "фото" next to its own photo. The other sources
 * have no picture to speak for them, so they keep their label.
 */
@Composable
private fun sourceMeta(source: TodayMealSource): String =
    if (source == TodayMealSource.Photo) "" else sourceLabel(source)

@Composable
private fun sourceLabel(source: TodayMealSource): String =
    when (source) {
        TodayMealSource.Photo -> stringResource(R.string.today_source_photo)
        TodayMealSource.Restaurant -> stringResource(R.string.today_source_restaurant)
        TodayMealSource.Pattern -> stringResource(R.string.today_source_pattern)
        TodayMealSource.Manual -> stringResource(R.string.today_source_manual)
        TodayMealSource.Mixed -> stringResource(R.string.today_source_mixed)
        TodayMealSource.Text -> stringResource(R.string.today_source_text)
    }

@Composable
/** One line, not two stacked: «449 · 5,4 г» in half the height. */
private fun primaryRightText(row: TodayMealRowUi, isOnline: Boolean): String =
    if (row.kind == TodayMealRowKind.Pending) {
        pendingStatusText(row, isOnline)
    } else {
        listOfNotNull(
            row.totalKcal?.let { stringResource(R.string.today_right_kcal, formatKcal(it)) },
            row.totalCarbsG?.let { stringResource(R.string.today_right_carbs, formatGrams(it)) },
        ).takeIf { it.isNotEmpty() }?.joinToString(" · ") ?: "—"
    }

@Composable
private fun secondaryRightText(row: TodayMealRowUi): String = ""

@Composable
private fun TodayMealRowUi.pendingErrorText(): String? =
    errorMessage
        ?.takeIf { kind == TodayMealRowKind.Pending && it.isNotBlank() }
        ?.let { stringResource(R.string.today_pending_error, it.take(120)) }

@Composable
private fun pendingStatusText(row: TodayMealRowUi, isOnline: Boolean): String {
    if (row.outboxId == null) {
        return when (row.status) {
            TodayMealStatus.Estimating -> stringResource(R.string.today_status_estimating)
            TodayMealStatus.Stuck -> row.errorMessage?.takeIf { it.isNotBlank() }
                ?: stringResource(R.string.today_status_estimate_stuck)
            TodayMealStatus.Draft -> stringResource(R.string.today_status_draft)
            else -> stringResource(R.string.today_status_draft)
        }
    }
    val state = computeRowState(
        state = row.status.toOutboxState(),
        lastAttemptAt = null,
        nextAttemptAt = row.nextAttemptAt,
        enteredCurrentStateAt = row.enteredCurrentStateAt ?: row.eatenAt,
        lastErrorCode = row.lastErrorCode,
        lastErrorMessage = row.errorMessage,
        isPhotoDraft = row.source == TodayMealSource.Photo && row.totalKcal == null,
        isOnline = isOnline,
    )
    return rowStateToText(state)
}

@Composable
private fun rowStateToText(state: RowState): String = when (state) {
    is RowState.JustQueued -> stringResource(R.string.outbox_state_just_queued)
    is RowState.TryingNow -> stringResource(R.string.outbox_state_trying_now)
    is RowState.RetryInSeconds -> stringResource(R.string.outbox_state_retry_in, state.seconds)
    is RowState.RetryInMinutes -> stringResource(R.string.outbox_state_retry_in_min, state.minutes)
    is RowState.Estimating -> stringResource(R.string.today_status_estimating)
    is RowState.EstimatingSlow -> stringResource(R.string.outbox_state_estimating_slow)
    is RowState.Stuck -> state.errorMessage?.takeIf { it.isNotBlank() }
        ?: stringResource(R.string.today_status_estimate_stuck)
    is RowState.WaitingNetwork -> stringResource(R.string.today_status_waiting_network)
}

private fun UserGoals.hasAnyDailyTarget(): Boolean =
    listOf(dailyKcal, dailyProteinG, dailyCarbsG, dailyFatG)
        .any { goal -> goal != null && goal > 0 }

private fun TodayMealStatus.toOutboxState(): OutboxState = when (this) {
    TodayMealStatus.Queued -> OutboxState.Queued
    TodayMealStatus.Uploading -> OutboxState.Uploading
    TodayMealStatus.Stuck -> OutboxState.Stuck
    TodayMealStatus.Estimating -> OutboxState.Queued
    TodayMealStatus.Accepted -> OutboxState.Confirmed
    TodayMealStatus.Draft -> OutboxState.Confirmed
}

internal val TodayMealRowUi.isAgedPending: Boolean
    get() = kind == TodayMealRowKind.Pending &&
        status == TodayMealStatus.Stuck

private enum class TarelkaDayCharacter {
    Dense,
    Light,
}

private fun characterizeDay(todayKcal: Int, median14d: Int?, now: LocalTime): TarelkaDayCharacter? {
    val median = median14d?.takeIf { it > 0 } ?: return null
    if (now.hour < 12) return null
    val ratio = todayKcal.toDouble() / median.toDouble()
    return when {
        ratio > 1.15 -> TarelkaDayCharacter.Dense
        ratio < 0.85 -> TarelkaDayCharacter.Light
        else -> null
    }
}

@Composable
private fun TarelkaDayCharacter.label(): String = when (this) {
    TarelkaDayCharacter.Dense -> stringResource(R.string.tarelka_day_dense)
    TarelkaDayCharacter.Light -> stringResource(R.string.tarelka_day_light)
}

@Composable
private fun tarelkaObservation(
    consumed: Int,
    typical: Int?,
    goal: Int?,
    date: LocalDate,
    accentColor: Color,
): AnnotatedString? {
    if (goal == null) {
        return AnnotatedString(
            stringResource(R.string.tarelka_observation_no_goal, formatKcal(consumed)),
        )
    }
    val typicalKcal = typical?.takeIf { it > 0 } ?: return null
    val delta = consumed - typicalKcal
    if (abs(delta) <= 50) {
        return AnnotatedString(stringResource(R.string.tarelka_observation_on_target))
    }
    val deltaText = stringResource(R.string.tarelka_observation_delta_value, formatKcal(abs(delta)))
    return buildAnnotatedString {
        append(stringResource(R.string.tarelka_observation_delta_prefix))
        val start = length
        append(deltaText)
        addStyle(
            SpanStyle(color = accentColor, fontWeight = FontWeight.Bold),
            start = start,
            end = length,
        )
        append(
            if (delta > 0) {
                stringResource(R.string.tarelka_observation_over_suffix, tarelkaOverCloser(date))
            } else {
                stringResource(R.string.tarelka_observation_under_suffix)
            },
        )
    }
}

@Composable
private fun tarelkaOverCloser(date: LocalDate): String = when (date.dayOfMonth % 3) {
    0 -> stringResource(R.string.tarelka_over_closer_0)
    1 -> stringResource(R.string.tarelka_over_closer_1)
    else -> stringResource(R.string.tarelka_over_closer_2)
}

private fun overflowProgress(value: Double, goal: Int?): Float? {
    val safeGoal = goal?.takeIf { it > 0 } ?: return null
    if (value <= safeGoal) return null
    return ((value - safeGoal) / safeGoal).toFloat().coerceIn(0f, 1f)
}

private fun progressOf(value: Double, goal: Int?): Float =
    if (goal == null || goal <= 0) 0f else (value / goal).toFloat().coerceIn(0f, 1f)

private fun macroProgress(grams: Double, kcalGoal: Int?, caloriesPerGram: Double): Float? =
    kcalGoal?.takeIf { it > 0 }?.let { goal ->
        ((grams * caloriesPerGram) / goal).toFloat().coerceIn(0f, 1f)
    }

private fun LocalDate.toJava(): java.time.LocalDate =
    toJavaLocalDate()

private fun weekday(date: LocalDate): String =
    date.toJava()
        .format(DateTimeFormatter.ofPattern("EEEE", Locale("ru")))
        .uppercase(Locale("ru"))

private fun weekdaySpoken(date: LocalDate): String =
    date.toJava().format(DateTimeFormatter.ofPattern("EEEE", Locale("ru")))

private fun dateTitle(date: LocalDate): String =
    date.toJava().format(DateTimeFormatter.ofPattern("d MMMM", Locale("ru")))

private fun foodDateTitle(date: LocalDate): String =
    date.toJava().format(DateTimeFormatter.ofPattern("d MMMM yyyy", Locale("ru")))

private fun Instant.timeText(): String {
    val time = toLocalDateTime(TimeZone.currentSystemDefault()).time
    return "${time.hour.toString().padStart(2, '0')}:${time.minute.toString().padStart(2, '0')}"
}

private fun Instant.localDate(): LocalDate =
    toLocalDateTime(TimeZone.currentSystemDefault()).date

@Preview(showBackground = true, backgroundColor = 0xFFF6F4EF)
@Composable
private fun PendingPhotoWaitingPreview() {
    TodayMealRowPreview(
        row = previewPendingPhotoRow(
            PhotoProcessingUiState(
                stage = PhotoProcessingStage.WaitingUpload,
                title = "Фото",
                statusText = "ждёт отправки · очередь 3 из 3",
                helperText = "начнём после предыдущих фото",
                queuePositionText = "очередь 3 из 3",
                uploadProgress = null,
                estimateElapsedSeconds = null,
                estimateDeadlineSeconds = null,
                canRetry = false,
            ),
        ),
    )
}

@Preview(showBackground = true, backgroundColor = 0xFFF6F4EF)
@Composable
private fun PendingPhotoUploadingPreview() {
    TodayMealRowPreview(
        row = previewPendingPhotoRow(
            PhotoProcessingUiState(
                stage = PhotoProcessingStage.Uploading,
                title = "Фото",
                statusText = "отправляем фото · 64%",
                helperText = null,
                queuePositionText = null,
                uploadProgress = 0.64f,
                estimateElapsedSeconds = null,
                estimateDeadlineSeconds = null,
                canRetry = false,
            ),
        ),
    )
}

@Preview(showBackground = true, backgroundColor = 0xFFF6F4EF)
@Composable
private fun PendingPhotoEstimatingPreview() {
    TodayMealRowPreview(
        row = previewPendingPhotoRow(
            PhotoProcessingUiState(
                stage = PhotoProcessingStage.Estimating,
                title = "Фото",
                statusText = "модель оценивает · осталось до 40 сек",
                helperText = null,
                queuePositionText = null,
                uploadProgress = null,
                estimateElapsedSeconds = 50,
                estimateDeadlineSeconds = 90,
                canRetry = false,
            ),
        ),
    )
}

@Preview(showBackground = true, backgroundColor = 0xFFF6F4EF)
@Composable
private fun PendingPhotoStuckPreview() {
    TodayMealRowPreview(
        row = previewPendingPhotoRow(
            PhotoProcessingUiState(
                stage = PhotoProcessingStage.Stuck,
                title = "Фото",
                statusText = "оценка не пришла · можно повторить",
                helperText = "откройте очередь, чтобы повторить",
                queuePositionText = null,
                uploadProgress = null,
                estimateElapsedSeconds = null,
                estimateDeadlineSeconds = 90,
                canRetry = true,
                failureStep = PhotoProcessingFailureStep.Estimate,
            ),
        ),
    )
}

@Preview(showBackground = true, backgroundColor = 0xFFF6F4EF)
@Composable
private fun AcceptedMealRowPreview() {
    TodayMealRowPreview(
        row = TodayMealRowUi(
            id = "accepted",
            recordId = "meal-1",
            outboxId = null,
            kind = TodayMealRowKind.Accepted,
            eatenAt = Instant.parse("2026-05-13T11:04:00Z"),
            title = "Лаваш с курицей и овощами",
            source = TodayMealSource.Manual,
            status = TodayMealStatus.Accepted,
            photo = null,
            totalKcal = 324.0,
            totalCarbsG = 25.1,
            totalProteinG = 18.0,
            totalFatG = 11.0,
            errorMessage = null,
        ),
    )
}

@Composable
private fun TodayMealRowPreview(row: TodayMealRowUi) {
    GTTheme {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(GT.colors.bg)
                .padding(vertical = 12.dp),
        ) {
            MealRowSurface(
                row = row,
                lastAddedId = null,
                onOpenRow = {},
            )
        }
    }
}

private fun previewPendingPhotoRow(state: PhotoProcessingUiState): TodayMealRowUi =
    TodayMealRowUi(
        id = state.stage.name,
        recordId = null,
        outboxId = "outbox-${state.stage.name}",
        kind = TodayMealRowKind.Pending,
        eatenAt = Instant.parse("2026-05-13T11:04:00Z"),
        title = null,
        source = TodayMealSource.Photo,
        status = when (state.stage) {
            PhotoProcessingStage.Uploading -> TodayMealStatus.Uploading
            PhotoProcessingStage.Stuck -> TodayMealStatus.Stuck
            PhotoProcessingStage.Estimating -> TodayMealStatus.Estimating
            else -> TodayMealStatus.Queued
        },
        photo = null,
        totalKcal = null,
        totalCarbsG = null,
        totalProteinG = null,
        totalFatG = null,
        errorMessage = null,
        photoProcessing = state,
    )
