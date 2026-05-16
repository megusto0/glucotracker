package com.local.glucotracker.ui.navigation

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OfflineBannerStateMachineTest {
    @Test
    fun resolvesMatrixWithStuckPriority() {
        assertEquals(
            OfflineBannerUiState.Hidden,
            OfflineBannerUiState.resolve(true, queueDepth = 0, stuckDepth = 0, offlineGraceElapsed = false, dataAt = "12:34"),
        )
        assertEquals(
            OfflineBannerUiState.SyncQueue(2),
            OfflineBannerUiState.resolve(true, queueDepth = 2, stuckDepth = 0, offlineGraceElapsed = false, dataAt = "12:34"),
        )
        assertEquals(
            OfflineBannerUiState.OfflineStale("12:34"),
            OfflineBannerUiState.resolve(false, queueDepth = 0, stuckDepth = 0, offlineGraceElapsed = true, dataAt = "12:34"),
        )
        assertEquals(
            OfflineBannerUiState.OfflineQueue(1),
            OfflineBannerUiState.resolve(false, queueDepth = 1, stuckDepth = 0, offlineGraceElapsed = true, dataAt = "12:34"),
        )
        assertEquals(
            OfflineBannerUiState.Stuck(1),
            OfflineBannerUiState.resolve(true, queueDepth = 1, stuckDepth = 1, offlineGraceElapsed = false, dataAt = "12:34"),
        )
        assertEquals(
            OfflineBannerUiState.Stuck(3),
            OfflineBannerUiState.resolve(false, queueDepth = 0, stuckDepth = 3, offlineGraceElapsed = true, dataAt = "12:34"),
        )
    }

    @Test
    fun everyVisibleBannerIsTappable() {
        listOf(
            OfflineBannerUiState.SyncQueue(1),
            OfflineBannerUiState.OfflineStale("12:34"),
            OfflineBannerUiState.OfflineQueue(1),
            OfflineBannerUiState.Stuck(1),
        ).forEach { state ->
            assertTrue(state.tappable)
        }
    }
}
