package com.local.glucotracker.ui.snapshots

import app.cash.paparazzi.DeviceConfig
import app.cash.paparazzi.Paparazzi
import com.local.glucotracker.ui.design.FoodBrandTokens
import com.local.glucotracker.ui.navigation.OfflineBannerUiState
import kotlinx.datetime.LocalTime
import org.junit.Rule
import org.junit.Test

class FoodFeatureSnapshotTest {
    @get:Rule
    val paparazzi = Paparazzi(deviceConfig = DeviceConfig.PIXEL_5)

    @Test fun todayFullDay() = paparazzi.snapshotThemed("food_today_full") {
        TodaySnapshot(todayFullState(), brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun todayEmptyDay() = paparazzi.snapshotThemed("food_today_empty") {
        TodaySnapshot(todayEmptyState(), brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun todayNoGoal() = paparazzi.snapshotThemed("food_today_no_goal") {
        TodaySnapshot(todayNoGoalState(), brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun todayOverGoal() = paparazzi.snapshotThemed("food_today_over_goal") {
        TodaySnapshot(foodTodayOverGoalState(), brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun todayUnderGoal() = paparazzi.snapshotThemed("food_today_under_goal") {
        TodaySnapshot(foodTodayUnderGoalState(), brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun todayOnTarget() = paparazzi.snapshotThemed("food_today_on_target") {
        TodaySnapshot(foodTodayOnTargetState(), brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun todayEarlyNoHeadline() = paparazzi.snapshotThemed("food_today_early_no_headline") {
        TodaySnapshot(
            foodTodayOverGoalState(),
            brandAccentColor = FoodBrandTokens.Tangerine,
            now = LocalTime(8, 30),
        )
    }

    @Test fun todayNoGoalRing() = paparazzi.snapshotThemed("food_today_no_goal_ring") {
        TodaySnapshot(foodTodayNoGoalState(), brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun todayWithSoftObservation() = paparazzi.snapshotThemed("food_today_soft_observation") {
        TodaySnapshot(todaySoftObservationState(), brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun todayWithPending() = paparazzi.snapshotThemed("food_today_pending") {
        TodaySnapshot(todayPendingState(), brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun todayWithAgedPending() = paparazzi.snapshotThemed("food_today_aged_pending") {
        TodaySnapshot(todayAgedPendingState(), brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun statsFullWeek() = paparazzi.snapshotThemed("food_stats_full") {
        StatsSnapshot(foodStatsFullState(), brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun statsNoInsightQualifying() = paparazzi.snapshotThemed("food_stats_no_insight") {
        StatsSnapshot(foodStatsNoInsightState(), brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun statsSparseWeek() = paparazzi.snapshotThemed("food_stats_sparse") {
        StatsSnapshot(foodStatsSparseState(), brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun statsEmpty() = paparazzi.snapshotThemed("food_stats_empty") {
        StatsSnapshot(foodStatsEmptyState(), brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun historyMultiDay() = paparazzi.snapshotThemed("food_history_multi_day") {
        HistorySnapshot(historyFullState(), brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun historySweetHeavyDay() = paparazzi.snapshotThemed("food_history_sweet_heavy") {
        HistorySnapshot(historySweetHeavyState(), brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun historyEmpty() = paparazzi.snapshotThemed("food_history_empty") {
        HistorySnapshot(historyEmptyState(), brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun historyTimelineVaried() = paparazzi.snapshotThemed("food_history_timeline_varied") {
        HistorySnapshot(historyTimelineVariedState(), brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun historyTimelineSingle() = paparazzi.snapshotThemed("food_history_timeline_single") {
        HistorySnapshot(historyTimelineSingleState(), brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun historyTimelineDense() = paparazzi.snapshotThemed("food_history_timeline_dense") {
        HistorySnapshot(historyTimelineDenseState(), brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun historyTimelineMixedStatus() = paparazzi.snapshotThemed("food_history_timeline_mixed_status") {
        HistorySnapshot(historyTimelineMixedStatusState(), brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun composeSheetEmpty() = paparazzi.snapshotThemed("food_compose_sheet_empty") {
        ComposeSheetEmptySnapshot()
    }

    @Test fun composeSheetWithResults() = paparazzi.snapshotThemed("food_compose_sheet_results") {
        ComposeSheetResultsSnapshot()
    }

    @Test fun composeSheetNoMatch() = paparazzi.snapshotThemed("food_compose_sheet_no_match") {
        ComposeSheetNoMatchSnapshot()
    }

    @Test fun draft() = paparazzi.snapshotThemed("food_draft") {
        DraftSnapshot()
    }

    @Test fun record() = paparazzi.snapshotThemed("food_record") {
        RecordSnapshot()
    }

    @Test fun base() = paparazzi.snapshotThemed("food_base") {
        BaseSnapshot()
    }

    @Test fun more() = paparazzi.snapshotThemed("food_more") {
        MoreSnapshot(brandAccentColor = FoodBrandTokens.Tangerine)
    }

    @Test fun outboxInspector() = paparazzi.snapshotThemed("food_outbox_inspector") {
        OutboxInspectorSnapshot()
    }

    @Test fun bannerStates() {
        listOf(
            "active" to OfflineBannerUiState.SyncQueue(1),
            "offline_stale" to OfflineBannerUiState.OfflineStale("12:34"),
            "offline_queue" to OfflineBannerUiState.OfflineQueue(2),
            "stuck" to OfflineBannerUiState.Stuck(1),
        ).forEach { (name, state) ->
            paparazzi.snapshotThemed("food_banner_$name") {
                BannerSnapshot(state)
            }
        }
    }

    @Test fun login() = paparazzi.snapshotThemed("food_login") {
        LoginSnapshot()
    }
}
