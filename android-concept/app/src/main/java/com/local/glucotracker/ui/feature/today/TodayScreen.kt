package com.local.glucotracker.ui.feature.today

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.ui.graphics.Color
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
            modifier = Modifier.fillMaxSize(),
            verticalArrangement = Arrangement.spacedBy(if (brandAccentColor != null) 6.dp else 14.dp),
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
                if (brandAccentColor == null) {
                    TodayKpiGrid(
                        totals = state.totals,
                        goals = state.goals,
                        pendingQueueCount = state.pendingQueueCount,
                        modifier = Modifier.padding(horizontal = 18.dp),
                    )
                } else {
                    TarelkaTodaySummary(
                        state = state,
                        accentColor = brandAccentColor,
                        now = now,
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
                    MealListHeader(
                        rows = state.rows,
                        modifier = Modifier.padding(horizontal = 18.dp),
                    )
                }
            }
            item {
                LocalGlucoseSurfaces.current.TodayRows(
                    date = state.date,
                    rows = state.rows,
                ) { row, extraMetaContent ->
                    SwipeMealRow(
                        row = row,
                        lastAddedId = lastQueuedOutboxId ?: state.lastAddedId,
                        onOpenRow = onOpenRow,
                        onDeleteRow = { candidate -> deleteCandidate = candidate },
                        isOnline = state.isOnline,
                        compact = brandAccentColor != null,
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
                style = if (foodBrand) GT.type.serifTitle.copy(fontSize = 32.sp) else GT.type.serifTitle,
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

@Composable
private fun TodayKpiGrid(
    totals: DayTotals,
    goals: UserGoals,
    pendingQueueCount: Int,
    modifier: Modifier = Modifier,
) {
    val kcalGoal = goals.dailyKcal
    val carbsGoal = goals.dailyCarbsG
    val remaining = kcalGoal?.let { it - totals.kcal }
    Column(modifier = modifier) {
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            GTKpiCard(
                label = stringResource(R.string.today_kpi_kcal),
                value = formatKcal(totals.kcal),
                sub = kcalGoal?.let { stringResource(R.string.today_kpi_goal_sub, formatKcal(it)) }
                    ?: stringResource(R.string.today_kpi_day_sub),
                progress = progressOf(totals.kcal, kcalGoal),
                progressColor = GT.colors.good.copy(alpha = 0.65f),
                extra = pendingQueueCount.takeIf { it > 0 }
                    ?.let { stringResource(R.string.today_kpi_queue_kicker, it) },
                modifier = Modifier.weight(1f),
            )
            GTKpiCard(
                label = stringResource(R.string.today_kpi_protein),
                value = formatGrams(totals.proteinG),
                sub = stringResource(R.string.today_kpi_day_sub),
                progress = 0f,
                progressColor = GT.colors.info.copy(alpha = 0.65f),
                modifier = Modifier.weight(1f),
            )
        }
        Row(
            modifier = Modifier.padding(top = 10.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            GTKpiCard(
                label = stringResource(R.string.today_kpi_carbs),
                value = formatGrams(totals.carbsG),
                sub = carbsGoal?.let { stringResource(R.string.today_kpi_goal_sub, formatGrams(it.toDouble())) }
                    ?: stringResource(R.string.today_kpi_day_sub),
                progress = progressOf(totals.carbsG, carbsGoal),
                progressColor = GT.colors.accent.copy(alpha = 0.68f),
                modifier = Modifier.weight(1f),
            )
            GTKpiCard(
                label = stringResource(R.string.today_kpi_remaining),
                value = remaining?.let { formatSignedKcal(it.roundToLong()) } ?: "—",
                sub = kcalGoal?.let { stringResource(R.string.today_kpi_goal_sub, formatKcal(it)) }
                    ?: stringResource(R.string.today_kpi_no_goal_sub),
                progress = remaining?.let { progressOf(it.coerceAtLeast(0.0), kcalGoal) } ?: 0f,
                progressColor = GT.colors.good.copy(alpha = 0.5f),
                modifier = Modifier.weight(1f),
            )
        }
    }
}

@Composable
private fun TarelkaTodaySummary(
    state: TodayState.Day,
    accentColor: Color,
    now: LocalTime,
    modifier: Modifier = Modifier,
) {
    val totals = state.totals
    val kcalGoal = state.goals.dailyKcal
    val currentKcal = formatKcal(totals.kcal)
    val goalKcal = kcalGoal?.let(::formatKcal)
    val remaining = kcalGoal?.let { it - totals.kcal }
    val remainingDescription = remaining?.let { formatSignedKcal(it.roundToLong()) }
    val dayKcal = totals.kcal.roundToLong().toInt()
    val dayCharacter = characterizeDay(dayKcal, state.typicalKcal14d, now)
    val observation = tarelkaObservation(
        consumed = dayKcal,
        typical = state.typicalKcal14d,
        goal = kcalGoal,
        date = state.date,
        accentColor = accentColor,
    )
    val overflowProgress = overflowProgress(totals.kcal, kcalGoal)
    val ringContentDescription = if (goalKcal == null) {
        stringResource(R.string.today_ring_no_goal_content_description, currentKcal)
    } else {
        stringResource(
            R.string.today_ring_content_description,
            currentKcal,
            goalKcal,
            remainingDescription.orEmpty(),
        )
    }
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        GTKcalRing(
            value = currentKcal,
            goalText = goalKcal?.let { stringResource(R.string.today_ring_goal_label, it) }
                ?: stringResource(R.string.today_ring_goal_unset),
            progress = kcalGoal?.let { progressOf(totals.kcal, it) },
            ringColor = accentColor,
            remainingValue = "",
            remainingLabel = "",
            observation = observation,
            contentDescription = ringContentDescription,
            headline = dayCharacter?.label(),
            overflowProgress = overflowProgress,
            overflowNote = overflowProgress
                ?.takeIf { it > 0f }
                ?.let { stringResource(R.string.tarelka_overflow_note) },
        )
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            GTMacroBar(
                label = stringResource(R.string.today_kpi_protein),
                value = stringResource(R.string.today_macro_value, formatGrams(totals.proteinG)),
                percentOfDay = macroProgress(totals.proteinG, kcalGoal, caloriesPerGram = 4.0),
                color = GT.colors.info,
                contentDescription = stringResource(
                    R.string.today_macro_content_description,
                    stringResource(R.string.today_kpi_protein),
                    formatGrams(totals.proteinG),
                ),
            )
            GTMacroBar(
                label = stringResource(R.string.today_kpi_fat),
                value = stringResource(R.string.today_macro_value, formatGrams(totals.fatG)),
                percentOfDay = macroProgress(totals.fatG, kcalGoal, caloriesPerGram = 9.0),
                color = GT.colors.warn,
                contentDescription = stringResource(
                    R.string.today_macro_content_description,
                    stringResource(R.string.today_kpi_fat),
                    formatGrams(totals.fatG),
                ),
            )
            GTMacroBar(
                label = stringResource(R.string.today_kpi_carbs),
                value = stringResource(R.string.today_macro_value, formatGrams(totals.carbsG)),
                percentOfDay = macroProgress(totals.carbsG, kcalGoal, caloriesPerGram = 4.0),
                color = GT.colors.accent,
                contentDescription = stringResource(
                    R.string.today_macro_content_description,
                    stringResource(R.string.today_kpi_carbs),
                    formatGrams(totals.carbsG),
                ),
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

    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 18.dp)
            .background(bg, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .then(clickModifier),
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
                time = row.eatenAt.timeText(),
                photo = row.photo,
                name = row.title ?: fallbackTitle(row),
                meta = row.pendingErrorText()
                    ?: stringResource(
                        R.string.today_meal_meta,
                        row.eatenAt.timeText(),
                        sourceLabel(row.source),
                    ),
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
private fun primaryRightText(row: TodayMealRowUi, isOnline: Boolean): String =
    if (row.kind == TodayMealRowKind.Pending) {
        pendingStatusText(row, isOnline)
    } else {
        row.totalCarbsG?.let { stringResource(R.string.today_right_carbs, formatGrams(it)) } ?: "—"
    }

@Composable
private fun secondaryRightText(row: TodayMealRowUi): String =
    if (row.kind == TodayMealRowKind.Pending) {
        ""
    } else {
        row.totalKcal?.let { stringResource(R.string.today_right_kcal, formatKcal(it)) } ?: "—"
    }

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
    date.toJava().format(DateTimeFormatter.ofPattern("d MMMM yyyy", Locale("ru")))

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
