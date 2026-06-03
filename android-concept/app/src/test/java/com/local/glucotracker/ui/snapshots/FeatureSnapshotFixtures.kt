package com.local.glucotracker.ui.snapshots

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import app.cash.paparazzi.Paparazzi
import com.local.glucotracker.data.settings.NotificationToggles
import com.local.glucotracker.domain.model.DayTotals
import com.local.glucotracker.domain.model.HistoryFilter
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.domain.model.Product
import com.local.glucotracker.domain.model.StatsInsight
import com.local.glucotracker.domain.model.StatsPeriod
import com.local.glucotracker.domain.model.HistoryStatusFilter
import com.local.glucotracker.domain.model.SyncStatus
import com.local.glucotracker.domain.model.Template
import com.local.glucotracker.domain.model.UiPrefs
import com.local.glucotracker.domain.model.UserGoals
import com.local.glucotracker.ui.design.GTTheme
import com.local.glucotracker.ui.feature.auth.LoginScreen
import com.local.glucotracker.ui.feature.auth.LoginUiState
import com.local.glucotracker.ui.feature.base.BaseFilter
import com.local.glucotracker.ui.feature.base.BaseItem
import com.local.glucotracker.ui.feature.base.BaseScreen
import com.local.glucotracker.ui.feature.base.BaseState
import com.local.glucotracker.ui.feature.capture.ManualEntrySearchSheetContent
import com.local.glucotracker.ui.feature.history.HistoryDayUi
import com.local.glucotracker.ui.feature.history.HistoryMealRowKind
import com.local.glucotracker.ui.feature.history.HistoryMealRowUi
import com.local.glucotracker.ui.feature.history.HistoryMealSource
import com.local.glucotracker.ui.feature.history.HistoryMealStatus
import com.local.glucotracker.ui.feature.history.HistoryScreen
import com.local.glucotracker.ui.feature.history.HistoryScreenState
import com.local.glucotracker.ui.feature.more.MoreScreen
import com.local.glucotracker.ui.feature.more.MoreState
import com.local.glucotracker.ui.feature.record.RecordScreen
import com.local.glucotracker.ui.feature.record.RecordState
import com.local.glucotracker.ui.feature.record.RecordStatus
import com.local.glucotracker.ui.feature.record.RecordUi
import com.local.glucotracker.ui.feature.sync.OutboxInspectorScreen
import com.local.glucotracker.ui.feature.sync.OutboxInspectorState
import com.local.glucotracker.ui.feature.stats.StatsDay
import com.local.glucotracker.ui.feature.stats.StatsScreen
import com.local.glucotracker.ui.feature.stats.StatsState
import com.local.glucotracker.ui.feature.today.TodayMealRowKind
import com.local.glucotracker.ui.feature.today.TodayMealRowUi
import com.local.glucotracker.ui.feature.today.TodayMealSource
import com.local.glucotracker.ui.feature.today.TodayMealStatus
import com.local.glucotracker.ui.feature.today.TodayScreen
import com.local.glucotracker.ui.feature.today.TodayState
import com.local.glucotracker.ui.navigation.GTOfflineBanner
import com.local.glucotracker.ui.navigation.OfflineBannerUiState
import kotlinx.datetime.DatePeriod
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.LocalTime
import kotlinx.datetime.plus

internal val SnapshotDate: LocalDate = LocalDate.parse("2026-05-05")
internal val SnapshotTime: Instant = Instant.parse("2026-05-05T09:15:00Z")

internal fun Paparazzi.snapshotThemed(name: String, content: @Composable () -> Unit) {
    snapshot(name) {
        GTTheme {
            content()
        }
    }
}

@Composable
internal fun TodaySnapshot(
    state: TodayState,
    brandAccentColor: Color? = null,
    now: LocalTime = LocalTime(18, 0),
) {
    TodayScreen(
        state = state,
        onOpenRow = {},
        onDeleteRow = {},
        onRefresh = {},
        onPreviousDay = {},
        onNextDay = {},
        onOpenStats = {},
        brandAccentColor = brandAccentColor,
        now = now,
    )
}

@Composable
internal fun StatsSnapshot(state: StatsState, brandAccentColor: Color? = null) {
    StatsScreen(state = state, brandAccentColor = brandAccentColor)
}

@Composable
internal fun HistorySnapshot(state: HistoryScreenState, brandAccentColor: Color? = null) {
    HistoryScreen(
        state = state,
        onOpenMealStack = { _, _ -> },
        onOpenDay = {},
        onToggleFilter = {},
        onClearFilters = {},
        onStatusChange = {},
        onSearchChange = {},
        onLoadMore = {},
        brandAccentColor = brandAccentColor,
    )
}

@Composable
internal fun RecordSnapshot() {
    RecordScreen(
        state = RecordState.Loaded(record = sampleRecord(), outboxItem = null),
        onClose = {},
        onSaveTitle = {},
        onSaveTime = {},
        onSaveWeight = {},
        onCreatePortion = {},
        onDelete = {},
        onRetryStuck = {},
    )
}

@Composable
internal fun DraftSnapshot() {
    RecordScreen(
        state = RecordState.Loaded(
            record = sampleRecord().copy(
                id = "draft",
                serverId = null,
                outboxId = "draft",
                isPending = true,
                title = "Фото завтрака",
                status = RecordStatus.Estimating,
                kcal = null,
                carbsG = null,
                proteinG = null,
                fatG = null,
                fiberG = null,
            ),
            outboxItem = null,
        ),
        onClose = {},
        onSaveTitle = {},
        onSaveTime = {},
        onSaveWeight = {},
        onCreatePortion = {},
        onDelete = {},
        onRetryStuck = {},
    )
}

@Composable
internal fun BaseSnapshot() {
    BaseScreen(
        state = baseReadyState(),
        onQueryChange = {},
        onFilterChange = {},
        onUseInJournal = {},
    )
}

@Composable
internal fun ComposeSheetEmptySnapshot() {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(com.local.glucotracker.ui.design.GT.colors.bg),
    ) {
        ManualEntrySearchSheetContent(
            openCount = 0,
            onDismiss = {},
            onSubmitText = {},
            onSubmitProduct = {},
            onSubmitTemplate = {},
            searchProducts = { _, _, callback -> callback(emptyList()) },
            searchTemplates = { _, callback -> callback(emptyList()) },
        )
    }
}

@Composable
internal fun ComposeSheetResultsSnapshot() {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(com.local.glucotracker.ui.design.GT.colors.bg),
    ) {
        ManualEntrySearchSheetContent(
            openCount = 1,
            onDismiss = {},
            onSubmitText = {},
            onSubmitProduct = {},
            onSubmitTemplate = {},
            searchProducts = { _, _, callback -> callback(emptyList()) },
            searchTemplates = { _, callback -> callback(emptyList()) },
            initialText = "воп",
            initialProducts = composeSheetProducts(),
            initialTemplates = composeSheetTemplates(),
        )
    }
}

@Composable
internal fun ComposeSheetNoMatchSnapshot() {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(com.local.glucotracker.ui.design.GT.colors.bg),
    ) {
        ManualEntrySearchSheetContent(
            openCount = 4,
            onDismiss = {},
            onSubmitText = {},
            onSubmitProduct = {},
            onSubmitTemplate = {},
            searchProducts = { _, _, callback -> callback(emptyList()) },
            searchTemplates = { _, callback -> callback(emptyList()) },
            initialText = "салат с тунцом",
        )
    }
}

@Composable
internal fun LoginSnapshot() {
    LoginScreen(
        state = LoginUiState(username = "tarelka", password = "password"),
        onUsernameChange = {},
        onPasswordChange = {},
        onLogin = {},
    )
}

@Composable
internal fun MoreSnapshot(brandAccentColor: Color? = null) {
    MoreScreen(
        state = MoreState(
            goals = UserGoals(dailyKcal = 2100, dailyProteinG = 120, dailyCarbsG = 220, dailyFatG = 70, weightKg = 72.4),
            uiPrefs = UiPrefs(glucoseMode = "raw", useCompactRows = false),
            cacheSizeLabel = "18 МБ",
            productCount = 312,
            templateCount = 18,
            outboxCount = 2,
            outboxStuckCount = 1,
            notifications = NotificationToggles(
                mealReminder = true,
                nsFail = false,
                lowConfidence = true,
                outboxStuck = false,
            ),
            rhythm = null,
        ),
        onOpenBase = {},
        onOpenOutbox = {},
        onClearCache = {},
        onSaveGoals = { _, _, _, _, _ -> },
        onToggleNotification = {},
        onSetRhythmOverride = {},
        onClearRhythmOverride = {},
        onLogout = {},
        brandAccentColor = brandAccentColor,
    )
}

@Composable
internal fun OutboxInspectorSnapshot() {
    OutboxInspectorScreen(
        state = OutboxInspectorState(
            active = listOf(sampleOutboxItem("active", OutboxState.Uploading, attempts = 2)),
            stuck = listOf(
                sampleOutboxItem(
                    id = "stuck",
                    state = OutboxState.Stuck,
                    errorCode = "estimate_timeout",
                    errorMessage = "оценка не пришла за 10 минут",
                ),
            ),
        ),
        focusId = "stuck",
        onBack = {},
        onRetry = {},
        onDelete = {},
        onOpenJournal = {},
    )
}

@Composable
internal fun BannerSnapshot(state: OfflineBannerUiState) {
    GTOfflineBanner(state = state, onTap = {})
}

internal fun todayFullState(): TodayState.Day =
    TodayState.Day(
        date = SnapshotDate,
        totals = totals(SnapshotDate, mealCount = 3),
        goals = UserGoals(dailyKcal = 2100, dailyProteinG = 120, dailyCarbsG = 220, dailyFatG = 70, weightKg = 72.4),
        rows = listOf(
            todayRow("breakfast", "Омлет и тост", 420.0, 32.0, SnapshotTime),
            todayRow("lunch", "Гречка с курицей", 680.0, 74.0, Instant.parse("2026-05-05T12:35:00Z")),
            todayRow("snack", "Йогурт", 180.0, 18.0, Instant.parse("2026-05-05T16:10:00Z")),
        ),
        pendingQueueCount = 0,
        syncStatus = SyncStatus(queueDepth = 0, lastSyncAt = SnapshotTime, isSyncing = false),
        isRefreshing = false,
        lastAddedId = null,
        canGoNext = false,
    )

internal fun todayEmptyState(): TodayState.Empty =
    TodayState.Empty(
        date = SnapshotDate,
        syncStatus = SyncStatus(queueDepth = 0, lastSyncAt = null, isSyncing = false),
        isRefreshing = false,
        canGoNext = false,
    )

internal fun todayPendingState(): TodayState.Day =
    todayFullState().copy(
        pendingQueueCount = 1,
        syncStatus = SyncStatus(queueDepth = 1, lastSyncAt = SnapshotTime, isSyncing = true),
        rows = todayFullState().rows + todayRow(
            id = "pending",
            title = "Фото",
            kcal = null,
            carbs = null,
            time = Instant.parse("2026-05-05T18:40:00Z"),
            kind = TodayMealRowKind.Pending,
            status = TodayMealStatus.Queued,
        ),
    )

internal fun todayAgedPendingState(): TodayState.Day =
    todayFullState().copy(
        pendingQueueCount = 1,
        rows = todayFullState().rows + todayRow(
            id = "stuck",
            title = "Фото",
            kcal = null,
            carbs = null,
            time = Instant.parse("2026-05-05T18:40:00Z"),
            kind = TodayMealRowKind.Pending,
            status = TodayMealStatus.Stuck,
            outboxId = "stuck",
            enteredCurrentStateAt = Instant.parse("2026-05-05T18:20:00Z"),
            errorMessage = "оценка не пришла",
        ),
    )

internal fun todayNoGoalState(): TodayState.Day =
    todayFullState().copy(goals = UserGoals(dailyKcal = null, dailyProteinG = null, dailyCarbsG = null, dailyFatG = null, weightKg = null))

internal fun todaySoftObservationState(): TodayState.Day =
    todayFullState().copy(softObservation = "Похоже на твой обычный завтрак")

internal fun foodTodayOverGoalState(): TodayState.Day =
    todayFullState().copy(
        totals = totals(SnapshotDate, mealCount = 4).copy(
            kcal = 2420.0,
            carbsG = 260.0,
            proteinG = 118.0,
            fatG = 86.0,
        ),
        goals = UserGoals(dailyKcal = 2200, dailyProteinG = 120, dailyCarbsG = 230, dailyFatG = 75, weightKg = 72.4),
        typicalKcal14d = 1980,
    )

internal fun foodTodayUnderGoalState(): TodayState.Day =
    todayFullState().copy(
        totals = totals(SnapshotDate, mealCount = 2).copy(
            kcal = 1380.0,
            carbsG = 136.0,
            proteinG = 78.0,
            fatG = 42.0,
        ),
        goals = UserGoals(dailyKcal = 1900, dailyProteinG = 110, dailyCarbsG = 210, dailyFatG = 65, weightKg = 72.4),
        typicalKcal14d = 1780,
    )

internal fun foodTodayOnTargetState(): TodayState.Day =
    todayFullState().copy(
        totals = totals(SnapshotDate, mealCount = 3).copy(kcal = 1810.0),
        goals = UserGoals(dailyKcal = 1850, dailyProteinG = 110, dailyCarbsG = 210, dailyFatG = 65, weightKg = 72.4),
        typicalKcal14d = 1830,
    )

internal fun foodTodayNoGoalState(): TodayState.Day =
    todayNoGoalState().copy(typicalKcal14d = 1800)

internal fun statsFullState(): StatsState.Charts =
    StatsState.Charts(
        date = SnapshotDate,
        days = (0..6).map { offset ->
            val date = SnapshotDate.plus(DatePeriod(days = offset - 6))
            StatsDay(date = date, totals = totals(date, mealCount = 3 + offset % 2))
        },
        staleCacheAt = null,
    )

internal fun foodStatsFullState(): StatsState.Charts =
    statsFullState().copy(
        period = StatsPeriod.Fortnight,
        insights = listOf(
            StatsInsight(
                id = "consistent",
                kind = "consistent",
                text = "Привычный для тебя ритм. Около 1 970 ккал в день.",
            ),
            StatsInsight(
                id = "weekday",
                kind = "weekday_pattern_sweet",
                text = "По средам и пятницам вечером сладкого больше всего — около 380 ккал из десертов и напитков.",
            ),
            StatsInsight(
                id = "time",
                kind = "time_of_day_eating",
                text = "Чаще всего ешь в 13:00 и 18:00.",
                supportingNumbers = mapOf("first_hour" to "13", "second_hour" to "18"),
            ),
        ),
    )

internal fun foodStatsNoInsightState(): StatsState.Charts =
    statsFullState().copy(period = StatsPeriod.Fortnight, insights = emptyList())

internal fun foodStatsSparseState(): StatsState.Sparse =
    StatsState.Sparse(date = SnapshotDate, trackedDays = 2, period = StatsPeriod.Fortnight)

internal fun foodStatsEmptyState(): StatsState.Sparse =
    StatsState.Sparse(date = SnapshotDate, trackedDays = 0, period = StatsPeriod.Fortnight)

internal fun statsSparseState(): StatsState.Sparse =
    StatsState.Sparse(date = SnapshotDate, trackedDays = 2)

internal fun statsEmptyState(): StatsState.Sparse =
    StatsState.Sparse(date = SnapshotDate, trackedDays = 0)

internal fun historyFullState(): HistoryScreenState =
    HistoryScreenState(
        filters = emptySet(),
        status = HistoryStatusFilter.Active,
        search = "",
        days = listOf(
            historyDay(SnapshotDate, "breakfast", "Омлет и тост"),
            historyDay(SnapshotDate.plus(DatePeriod(days = -1)), "dinner", "Рис с рыбой"),
        ),
        isRefreshing = false,
        showNeedsNetworkHint = false,
        totalDays = 42,
        totalRecords = 167,
    )

internal fun historySweetHeavyState(): HistoryScreenState =
    HistoryScreenState(
        filters = setOf(HistoryFilter.Sweet),
        status = HistoryStatusFilter.Active,
        search = "",
        days = listOf(
            historyDay(SnapshotDate, "sweet", "Шоколадный десерт", isSweet = true),
            historyDay(
                SnapshotDate.plus(DatePeriod(days = -1)),
                "dinner",
                "Рис с рыбой",
                kcal = 1712.0,
                isSweet = false,
            ),
        ),
        isRefreshing = false,
        showNeedsNetworkHint = false,
        totalDays = 7,
        totalRecords = 24,
    )

internal fun historyTimelineVariedState(): HistoryScreenState =
    historyTimelineState(
        rows = listOf(
            historyRow("coffee", "Кофе", 20.0, "drink", Instant.parse("2026-05-05T04:40:00Z")),
            historyRow("breakfast", "Омлет", 420.0, "main_meal", Instant.parse("2026-05-05T06:25:00Z")),
            historyRow("dessert", "Шоколад", 140.0, "dessert", Instant.parse("2026-05-05T10:05:00Z"), isSweet = true),
            historyRow("lunch", "Рис с рыбой", 690.0, "main_meal", Instant.parse("2026-05-05T12:35:00Z")),
            historyRow("snack", "Йогурт", 170.0, "snack", Instant.parse("2026-05-05T15:20:00Z")),
            historyRow("dinner", "Курица и овощи", 560.0, "main_meal", Instant.parse("2026-05-05T18:45:00Z")),
        ),
    )

internal fun historyTimelineSingleState(): HistoryScreenState =
    historyTimelineState(
        rows = listOf(
            historyRow("single", "Суп", 355.0, "main_meal", Instant.parse("2026-05-05T13:18:00Z")),
        ),
    )

internal fun historyTimelineDenseState(): HistoryScreenState =
    historyTimelineState(
        rows = (0 until 18).map { index ->
            historyRow(
                id = "dense-$index",
                title = "Перекус",
                kcal = 60.0 + index * 18.0,
                mealRole = if (index % 5 == 0) "main_meal" else "snack",
                time = Instant.parse("2026-05-05T${(7 + index / 2).toString().padStart(2, '0')}:${(index % 2 * 7).toString().padStart(2, '0')}:00Z"),
            )
        },
    )

internal fun historyTimelineMixedStatusState(): HistoryScreenState =
    historyTimelineState(
        rows = listOf(
            historyRow("accepted", "Завтрак", 430.0, "main_meal", Instant.parse("2026-05-05T07:20:00Z")),
            historyRow(
                id = "pending",
                title = "Фото",
                kcal = null,
                mealRole = null,
                time = Instant.parse("2026-05-05T11:40:00Z"),
                kind = HistoryMealRowKind.Pending,
                status = HistoryMealStatus.Queued,
            ),
            historyRow(
                id = "stuck",
                title = "Ужин",
                kcal = 610.0,
                mealRole = "main_meal",
                time = Instant.parse("2026-05-05T18:30:00Z"),
                kind = HistoryMealRowKind.Pending,
                status = HistoryMealStatus.Stuck,
            ),
        ),
    )

internal fun historyEmptyState(): HistoryScreenState =
    HistoryScreenState(
        filters = setOf(HistoryFilter.PhotoOnly),
        status = HistoryStatusFilter.Active,
        search = "",
        days = emptyList(),
        isRefreshing = false,
        showNeedsNetworkHint = false,
        totalDays = 0,
        totalRecords = 0,
    )

private fun todayRow(
    id: String,
    title: String,
    kcal: Double?,
    carbs: Double?,
    time: Instant,
    kind: TodayMealRowKind = TodayMealRowKind.Accepted,
    status: TodayMealStatus = TodayMealStatus.Accepted,
    outboxId: String? = null,
    enteredCurrentStateAt: Instant? = null,
    errorMessage: String? = null,
): TodayMealRowUi =
    TodayMealRowUi(
        id = id,
        recordId = if (kind == TodayMealRowKind.Accepted) id else null,
        outboxId = outboxId,
        kind = kind,
        eatenAt = time,
        title = title,
        source = TodayMealSource.Photo,
        status = status,
        photo = null,
        totalKcal = kcal,
        totalCarbsG = carbs,
        totalProteinG = 24.0,
        totalFatG = 18.0,
        errorMessage = errorMessage,
        enteredCurrentStateAt = enteredCurrentStateAt,
    )

private fun sampleOutboxItem(
    id: String,
    state: OutboxState,
    attempts: Int = 0,
    errorCode: String? = null,
    errorMessage: String? = null,
): OutboxItem =
    OutboxItem(
        id = id,
        kind = OutboxKind.CapturedMeal(
            localPhotoPath = null,
            capturedAt = SnapshotTime,
            source = "photo",
            optimisticName = if (id == "active") "Творог со сметаной" else null,
        ),
        state = state,
        createdAt = SnapshotTime,
        lastAttemptAt = SnapshotTime,
        nextAttemptAt = null,
        attempts = attempts,
        serverIdOnSuccess = null,
        errorMessage = errorMessage,
        enteredCurrentStateAt = SnapshotTime,
        lastErrorCode = errorCode,
        lastErrorMessage = errorMessage,
    )

private fun historyDay(
    date: LocalDate,
    id: String,
    title: String,
    kcal: Double = 510.0,
    isSweet: Boolean = false,
): HistoryDayUi =
    HistoryDayUi(
        date = date,
        totals = totals(date, mealCount = 2).copy(
            kcal = kcal,
            dailyAverageKcalForPeriod = 2200.0,
            photoCount = 1,
        ),
        rows = listOf(
            HistoryMealRowUi(
                id = id,
                recordId = id,
                outboxId = null,
                kind = HistoryMealRowKind.Accepted,
                eatenAt = SnapshotTime,
                title = title,
                source = HistoryMealSource.Photo,
                status = HistoryMealStatus.Accepted,
                photo = null,
                totalKcal = kcal,
                totalCarbsG = 54.0,
                totalProteinG = 24.0,
                totalFatG = 18.0,
                isSweet = isSweet,
                mealRole = if (isSweet) "dessert" else "main_meal",
                errorMessage = null,
            ),
        ),
        dailyAverageKcalForPeriod = 2200.0,
        photoCount = 1,
    )

private fun historyTimelineState(rows: List<HistoryMealRowUi>): HistoryScreenState =
    HistoryScreenState(
        filters = emptySet(),
        status = HistoryStatusFilter.Active,
        search = "",
        days = listOf(
            HistoryDayUi(
                date = SnapshotDate,
                totals = totals(SnapshotDate, mealCount = rows.count { it.kind == HistoryMealRowKind.Accepted }).copy(
                    kcal = rows.sumOf { it.totalKcal ?: 0.0 },
                    carbsG = rows.sumOf { it.totalCarbsG ?: 0.0 },
                    proteinG = rows.sumOf { it.totalProteinG ?: 0.0 },
                    fatG = rows.sumOf { it.totalFatG ?: 0.0 },
                    dailyAverageKcalForPeriod = 1800.0,
                    photoCount = rows.count { it.photo != null || it.source == HistoryMealSource.Photo },
                ),
                rows = rows.sortedByDescending { it.eatenAt },
                dailyAverageKcalForPeriod = 1800.0,
                photoCount = rows.count { it.photo != null || it.source == HistoryMealSource.Photo },
            ),
        ),
        isRefreshing = false,
        showNeedsNetworkHint = false,
        totalDays = 1,
        totalRecords = rows.size,
    )

private fun historyRow(
    id: String,
    title: String,
    kcal: Double?,
    mealRole: String?,
    time: Instant,
    isSweet: Boolean = false,
    kind: HistoryMealRowKind = HistoryMealRowKind.Accepted,
    status: HistoryMealStatus = HistoryMealStatus.Accepted,
    responseKey: String? = null,
): HistoryMealRowUi =
    HistoryMealRowUi(
        id = id,
        recordId = if (kind == HistoryMealRowKind.Accepted) id else null,
        outboxId = if (kind == HistoryMealRowKind.Pending) id else null,
        kind = kind,
        eatenAt = time,
        title = title,
        source = HistoryMealSource.Photo,
        status = status,
        photo = null,
        totalKcal = kcal,
        totalCarbsG = kcal?.div(10.0),
        totalProteinG = kcal?.div(20.0),
        totalFatG = kcal?.div(30.0),
        isSweet = isSweet,
        mealRole = mealRole,
        errorMessage = null,
        responseKey = responseKey,
    )

private fun sampleRecord(): RecordUi =
    RecordUi(
        id = "record",
        serverId = "record",
        outboxId = null,
        primaryItemId = "item",
        isPending = false,
        title = "Гречка с курицей",
        eatenAt = SnapshotTime,
        capturedAt = SnapshotTime,
        photo = null,
        source = "photo",
        status = RecordStatus.Accepted,
        kcal = 680.0,
        carbsG = 74.0,
        proteinG = 42.0,
        fatG = 18.0,
        fiberG = 6.0,
        weightGrams = 320.0,
        defaultWeightGrams = 320.0,
        nightscoutStatus = null,
        nightscoutSyncedAt = null,
        nightscoutLastAttemptAt = null,
        nightscoutError = null,
        postprandialResponse = null,
        canCreatePortion = true,
    )

private fun composeSheetProducts(): List<Product> =
    listOf(
        Product(
            id = "whopper",
            name = "Воппер",
            kind = "restaurant",
            subtitle = "Burger King",
            brand = "bk",
            aliases = listOf("whopper"),
            imageUrl = null,
            kcal = 720.0,
            carbsG = 48.0,
            proteinG = 28.0,
            fatG = 44.0,
            fiberG = 4.0,
            defaultGrams = 285.0,
            usageCount = 2,
            lastUsedAt = SnapshotTime,
        ),
        Product(
            id = "junior",
            name = "Воппер Джуниор",
            kind = "restaurant",
            subtitle = "Burger King",
            brand = "bk",
            aliases = listOf("junior whopper"),
            imageUrl = null,
            kcal = 370.0,
            carbsG = 31.0,
            proteinG = 16.0,
            fatG = 21.0,
            fiberG = 2.0,
            defaultGrams = 160.0,
            usageCount = 1,
            lastUsedAt = SnapshotTime,
        ),
    )

private fun composeSheetTemplates(): List<Template> =
    listOf(
        Template(
            id = "whopper-roll",
            name = "Воппер Ролл",
            aliases = listOf("воп ролл"),
            imageUrl = null,
            defaultKcal = 540.0,
            defaultCarbsG = 52.0,
            defaultProteinG = 23.0,
            defaultFatG = 27.0,
            defaultFiberG = 4.0,
            defaultGrams = 240.0,
            usageCount = 3,
            lastUsedAt = SnapshotTime,
        ),
    )

private fun baseReadyState(): BaseState.Ready =
    BaseState.Ready(
        query = "",
        filter = BaseFilter.Frequent,
        items = listOf(
            BaseItem.Product(
                Product(
                    id = "buckwheat",
                    name = "Гречка вареная",
                    kind = "product",
                    subtitle = "на 100 г",
                    brand = null,
                    aliases = listOf("гречневая каша"),
                    imageUrl = null,
                    kcal = 110.0,
                    carbsG = 21.0,
                    proteinG = 4.0,
                    fatG = 1.2,
                    fiberG = 2.7,
                    defaultGrams = 180.0,
                    usageCount = 18,
                    lastUsedAt = SnapshotTime,
                ),
            ),
            BaseItem.Template(
                Template(
                    id = "breakfast",
                    name = "Омлет и тост",
                    aliases = listOf("завтрак"),
                    imageUrl = null,
                    defaultKcal = 420.0,
                    defaultCarbsG = 32.0,
                    defaultProteinG = 26.0,
                    defaultFatG = 20.0,
                    defaultFiberG = 4.0,
                    defaultGrams = 260.0,
                    usageCount = 9,
                    lastUsedAt = SnapshotTime,
                ),
            ),
        ),
    )

private fun totals(date: LocalDate, mealCount: Int): DayTotals =
    DayTotals(
        date = date,
        kcal = 1560.0,
        carbsG = 172.0,
        proteinG = 92.0,
        fatG = 54.0,
        fiberG = 18.0,
        mealCount = mealCount,
        fetchedAt = SnapshotTime,
        netBalanceKcal = -140.0,
        tdeeKcal = 1700.0,
    )
