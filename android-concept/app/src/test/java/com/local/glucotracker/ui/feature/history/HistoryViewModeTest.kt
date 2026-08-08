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
}
