package com.local.glucotracker.ui.feature.history

import org.junit.Assert.assertEquals
import org.junit.Test

class HistoryViewModeTest {
    @Test
    fun gluco_opens_with_the_episode_list() {
        assertEquals(HistoryViewMode.List, defaultHistoryViewMode("gluco"))
    }

    @Test
    fun food_opens_with_the_showcase() {
        assertEquals(HistoryViewMode.Showcase, defaultHistoryViewMode("food"))
    }

    @Test
    fun showcase_uses_three_columns_by_default() {
        assertEquals(3, storedHistoryTileColumns(null))
        assertEquals(3, storedHistoryTileColumns(1))
        assertEquals(3, storedHistoryTileColumns(5))
    }

    @Test
    fun showcase_accepts_every_supported_tile_size() {
        assertEquals(2, storedHistoryTileColumns(2))
        assertEquals(3, storedHistoryTileColumns(3))
        assertEquals(4, storedHistoryTileColumns(4))
    }
}
