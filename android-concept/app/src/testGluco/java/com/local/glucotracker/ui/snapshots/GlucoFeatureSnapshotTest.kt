package com.local.glucotracker.ui.snapshots

import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import app.cash.paparazzi.DeviceConfig
import app.cash.paparazzi.Paparazzi
import com.local.glucotracker.ui.glucose.LocalGlucoseSurfaces
import com.local.glucotracker.ui.navigation.OfflineBannerUiState
import org.junit.Rule
import org.junit.Test

class GlucoFeatureSnapshotTest {
    @get:Rule
    val paparazzi = Paparazzi(deviceConfig = DeviceConfig.PIXEL_5)

    @Test fun todayFullDay() = glucoSnapshot("gluco_today_full") {
        TodaySnapshot(todayFullState())
    }

    @Test fun todayEmptyDay() = glucoSnapshot("gluco_today_empty") {
        TodaySnapshot(todayEmptyState())
    }

    @Test fun todayNoGoal() = glucoSnapshot("gluco_today_no_goal") {
        TodaySnapshot(todayNoGoalState())
    }

    @Test fun todayWithSoftObservation() = glucoSnapshot("gluco_today_soft_observation") {
        TodaySnapshot(todaySoftObservationState())
    }

    @Test fun todayWithPending() = glucoSnapshot("gluco_today_pending") {
        TodaySnapshot(todayPendingState())
    }

    @Test fun todayWithAgedPending() = glucoSnapshot("gluco_today_aged_pending") {
        TodaySnapshot(todayAgedPendingState())
    }

    @Test fun statsFullWeek() = glucoSnapshot("gluco_stats_full") {
        StatsSnapshot(statsFullState())
    }

    @Test fun statsNoInsightQualifying() = glucoSnapshot("gluco_stats_no_insight") {
        StatsSnapshot(statsFullState().copy(insights = emptyList()))
    }

    @Test fun statsSparseWeek() = glucoSnapshot("gluco_stats_sparse") {
        StatsSnapshot(statsSparseState())
    }

    @Test fun statsEmpty() = glucoSnapshot("gluco_stats_empty") {
        StatsSnapshot(statsEmptyState())
    }

    @Test fun historyMultiDay() = glucoSnapshot("gluco_history_multi_day") {
        HistorySnapshot(historyFullState())
    }

    @Test fun historySweetHeavyDay() = glucoSnapshot("gluco_history_sweet_heavy") {
        HistorySnapshot(historySweetHeavyState())
    }

    @Test fun historyEmpty() = glucoSnapshot("gluco_history_empty") {
        HistorySnapshot(historyEmptyState())
    }

    @Test fun historyTimelineVaried() = glucoSnapshot("gluco_history_timeline_varied") {
        HistorySnapshot(historyTimelineVariedState())
    }

    @Test fun historyTimelineSingle() = glucoSnapshot("gluco_history_timeline_single") {
        HistorySnapshot(historyTimelineSingleState())
    }

    @Test fun historyTimelineDense() = glucoSnapshot("gluco_history_timeline_dense") {
        HistorySnapshot(historyTimelineDenseState())
    }

    @Test fun historyTimelineMixedStatus() = glucoSnapshot("gluco_history_timeline_mixed_status") {
        HistorySnapshot(historyTimelineMixedStatusState())
    }

    @Test fun composeSheetEmpty() = glucoSnapshot("gluco_compose_sheet_empty") {
        ComposeSheetEmptySnapshot()
    }

    @Test fun composeSheetWithResults() = glucoSnapshot("gluco_compose_sheet_results") {
        ComposeSheetResultsSnapshot()
    }

    @Test fun composeSheetNoMatch() = glucoSnapshot("gluco_compose_sheet_no_match") {
        ComposeSheetNoMatchSnapshot()
    }

    @Test fun draft() = glucoSnapshot("gluco_draft") {
        DraftSnapshot()
    }

    @Test fun record() = glucoSnapshot("gluco_record") {
        RecordSnapshot()
    }

    @Test fun base() = glucoSnapshot("gluco_base") {
        BaseSnapshot()
    }

    @Test fun more() = glucoSnapshot("gluco_more") {
        MoreSnapshot()
    }

    @Test fun outboxInspector() = glucoSnapshot("gluco_outbox_inspector") {
        OutboxInspectorSnapshot()
    }

    @Test fun bannerStates() {
        listOf(
            "active" to OfflineBannerUiState.SyncQueue(1),
            "offline_stale" to OfflineBannerUiState.OfflineStale("12:34"),
            "offline_queue" to OfflineBannerUiState.OfflineQueue(2),
            "stuck" to OfflineBannerUiState.Stuck(1),
        ).forEach { (name, state) ->
            glucoSnapshot("gluco_banner_$name") {
                BannerSnapshot(state)
            }
        }
    }

    @Test fun login() = glucoSnapshot("gluco_login") {
        LoginSnapshot()
    }

    private fun glucoSnapshot(name: String, content: @Composable () -> Unit) {
        paparazzi.snapshotThemed(name) {
            CompositionLocalProvider(LocalGlucoseSurfaces provides SnapshotGlucoseSurfaces) {
                content()
            }
        }
    }
}
