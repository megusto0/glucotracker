package com.local.glucotracker.ui.feature.today

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Text
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
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
import com.local.glucotracker.domain.model.DayTotals
import com.local.glucotracker.domain.model.SyncStatus
import com.local.glucotracker.domain.model.UserGoals
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTKicker
import com.local.glucotracker.ui.design.primitives.GTIconButton
import com.local.glucotracker.ui.design.primitives.GTKpiCard
import com.local.glucotracker.ui.design.primitives.GTMealRow
import com.local.glucotracker.ui.design.primitives.GTMealRowStatus
import com.local.glucotracker.ui.design.primitives.GTStatusTone
import com.local.glucotracker.ui.format.formatGrams
import com.local.glucotracker.ui.format.formatKcal
import com.local.glucotracker.ui.format.formatMmol
import com.local.glucotracker.ui.format.formatSignedKcal
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToLong
import kotlinx.coroutines.delay
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toJavaLocalDate
import kotlinx.datetime.toLocalDateTime

@Composable
fun TodayRoute(
    onOpenRecord: (String) -> Unit,
    onOpenDraft: (String) -> Unit,
    lastQueuedOutboxId: String? = null,
    onQueuedOutboxConsumed: (String) -> Unit = {},
    viewModel: TodayViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsState()
    LaunchedEffect(lastQueuedOutboxId) {
        val outboxId = lastQueuedOutboxId ?: return@LaunchedEffect
        delay(1_800)
        onQueuedOutboxConsumed(outboxId)
    }
    TodayScreen(
        state = state,
        lastQueuedOutboxId = lastQueuedOutboxId,
        onOpenRow = { row ->
            row.draftOutboxId?.let(onOpenDraft)
                ?: (row.recordId ?: row.outboxId)?.let(onOpenRecord)
        },
        onDeleteRow = viewModel::deleteRow,
        onRefresh = viewModel::refresh,
        onPreviousDay = viewModel::previousDay,
        onNextDay = viewModel::nextDay,
    )
}

@Composable
fun TodayScreen(
    state: TodayState,
    lastQueuedOutboxId: String? = null,
    onOpenRow: (TodayMealRowUi) -> Unit,
    onDeleteRow: (TodayMealRowUi) -> Unit,
    onRefresh: () -> Unit,
    onPreviousDay: () -> Unit,
    onNextDay: () -> Unit,
    modifier: Modifier = Modifier,
) {
    when (state) {
        TodayState.Loading -> LoadingState(modifier = modifier)
        is TodayState.Empty -> EmptyState(
            state = state,
            onPreviousDay = onPreviousDay,
            onNextDay = onNextDay,
            modifier = modifier,
        )
        is TodayState.Day -> DayState(
            state = state,
            lastQueuedOutboxId = lastQueuedOutboxId,
            onOpenRow = onOpenRow,
            onDeleteRow = onDeleteRow,
            onPreviousDay = onPreviousDay,
            onNextDay = onNextDay,
            modifier = modifier,
        )
    }
}

@Composable
private fun LoadingState(modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = stringResource(R.string.today_loading),
            color = GT.colors.muted,
            style = GT.type.sansBody,
        )
    }
}

@Composable
private fun EmptyState(
    state: TodayState.Empty,
    onPreviousDay: () -> Unit,
    onNextDay: () -> Unit,
    modifier: Modifier = Modifier,
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
                modifier = Modifier.padding(horizontal = 18.dp, vertical = 10.dp),
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
    onPreviousDay: () -> Unit,
    onNextDay: () -> Unit,
    modifier: Modifier = Modifier,
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
                modifier = Modifier.padding(horizontal = 18.dp, vertical = 10.dp),
            )
        }
        item {
            TodayKpiGrid(
                totals = state.totals,
                goals = state.goals,
                pendingQueueCount = state.pendingQueueCount,
                modifier = Modifier.padding(horizontal = 18.dp),
            )
        }
        items(
            items = state.rows,
            key = { row -> row.id },
        ) { row ->
            SwipeMealRow(
                row = row,
                lastAddedId = lastQueuedOutboxId ?: state.lastAddedId,
                onOpenRow = onOpenRow,
                onDeleteRow = onDeleteRow,
            )
        }
        item {
            MiniGlucoseCard(
                state = state.glucose,
                modifier = Modifier.padding(horizontal = 18.dp),
            )
        }
        item {
            Spacer(Modifier.height(10.dp))
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
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            GTKicker(text = weekday(date))
            Spacer(Modifier.weight(1f))
            Text(
                text = syncText(syncStatus),
                color = if (syncStatus.queueDepth > 0) GT.colors.warn else GT.colors.muted,
                style = GT.type.monoLabel,
                maxLines = 1,
            )
        }
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 3.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            val dateText = dateTitle(date)
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
                style = GT.type.serifTitle,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                DayNavButton(
                    text = "◀",
                    contentDescription = stringResource(R.string.today_previous_day_content_description),
                    onClick = onPreviousDay,
                )
                DayNavButton(
                    text = "▶",
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
private fun syncText(syncStatus: SyncStatus): String =
    when {
        syncStatus.isSyncing -> stringResource(R.string.today_sync_running)
        syncStatus.queueDepth > 0 -> stringResource(R.string.today_sync_queue, syncStatus.queueDepth)
        else -> stringResource(R.string.today_sync_connected)
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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SwipeMealRow(
    row: TodayMealRowUi,
    lastAddedId: String?,
    onOpenRow: (TodayMealRowUi) -> Unit,
    onDeleteRow: (TodayMealRowUi) -> Unit,
) {
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
private fun MealRowSurface(
    row: TodayMealRowUi,
    lastAddedId: String?,
    onOpenRow: (TodayMealRowUi) -> Unit,
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

    val hasDestination = row.draftOutboxId != null || row.recordId != null || row.outboxId != null
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
        GTMealRow(
            time = row.eatenAt.timeText(),
            photo = row.photo,
            name = row.title ?: fallbackTitle(row),
            meta = stringResource(
                R.string.today_meal_meta,
                sourceLabel(row.source),
                statusLabel(row.status),
            ),
            primaryRight = row.totalCarbsG?.let { stringResource(R.string.today_right_carbs, formatGrams(it)) } ?: "—",
            secondaryRight = row.totalKcal?.let { stringResource(R.string.today_right_kcal, formatKcal(it)) } ?: "—",
            status = row.status.toMealRowStatus(row.kind),
            muted = row.kind == TodayMealRowKind.Pending,
        )
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
        TodayMealSource.Pattern -> stringResource(R.string.today_source_pattern)
        TodayMealSource.Manual -> stringResource(R.string.today_source_manual)
        TodayMealSource.Mixed -> stringResource(R.string.today_source_mixed)
        TodayMealSource.Text -> stringResource(R.string.today_source_text)
    }

@Composable
private fun statusLabel(status: TodayMealStatus): String =
    when (status) {
        TodayMealStatus.Accepted -> stringResource(R.string.today_status_accepted)
        TodayMealStatus.Draft -> stringResource(R.string.today_status_draft)
        TodayMealStatus.Estimating -> stringResource(R.string.today_status_estimating)
        TodayMealStatus.EstimateReady -> stringResource(R.string.today_status_estimate_ready)
        TodayMealStatus.Queued -> stringResource(R.string.today_status_queued)
        TodayMealStatus.Conflict -> stringResource(R.string.today_status_conflict)
    }

@Composable
private fun TodayMealStatus.toMealRowStatus(kind: TodayMealRowKind): GTMealRowStatus? =
    when (this) {
        TodayMealStatus.Accepted -> null
        TodayMealStatus.Draft -> GTMealRowStatus(
            icon = "\u00b7",
            text = stringResource(R.string.today_status_draft),
            tone = GTStatusTone.Muted,
        )
        TodayMealStatus.Estimating -> GTMealRowStatus(
            icon = "○",
            text = stringResource(R.string.today_status_estimating),
            tone = GTStatusTone.Info,
        )
        TodayMealStatus.EstimateReady -> GTMealRowStatus(
            icon = "✓",
            text = stringResource(R.string.today_status_estimate_ready),
            tone = GTStatusTone.Good,
        )
        TodayMealStatus.Queued -> GTMealRowStatus(
            icon = "↑",
            text = stringResource(R.string.today_status_queued),
            tone = if (kind == TodayMealRowKind.Pending) GTStatusTone.Muted else GTStatusTone.Info,
        )
        TodayMealStatus.Conflict -> GTMealRowStatus(
            icon = "!",
            text = stringResource(R.string.today_status_conflict),
            tone = GTStatusTone.Warn,
        )
    }

@Composable
private fun MiniGlucoseCard(
    state: MiniGlucoseUiState,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .height(88.dp)
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .padding(14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        when (state) {
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
                        text = formatMmol(state.valueMmol),
                        color = GT.colors.ink,
                        style = GT.type.monoNumber,
                    )
                    Text(
                        text = if (state.minutesAgo > 10) {
                            stringResource(R.string.today_glucose_stale, state.minutesAgo)
                        } else {
                            state.deltaMmol?.let { formatGlucoseDelta(it) }.orEmpty()
                        },
                        color = GT.colors.muted,
                        style = GT.type.monoLabel,
                    )
                }
                Sparkline(
                    points = state.points,
                    modifier = Modifier
                        .size(width = 112.dp, height = 42.dp),
                    color = GT.colors.info,
                )
            }
        }
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

private fun progressOf(value: Double, goal: Int?): Float =
    if (goal == null || goal <= 0) 0f else (value / goal).toFloat().coerceIn(0f, 1f)

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

private fun Instant.timeText(): String {
    val time = toLocalDateTime(TimeZone.currentSystemDefault()).time
    return "${time.hour.toString().padStart(2, '0')}:${time.minute.toString().padStart(2, '0')}"
}

private fun formatGlucoseDelta(delta: Double): String {
    val sign = if (delta < 0) "−" else "+"
    return "$sign${formatMmol(abs(delta))}"
}
