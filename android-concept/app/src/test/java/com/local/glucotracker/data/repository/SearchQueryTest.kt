package com.local.glucotracker.data.repository

import org.junit.Assert.assertEquals
import org.junit.Test

class SearchQueryTest {
    @Test
    fun ftsQueryDropsRussianPrepositions() {
        assertEquals("ролл* стрипсами*", "ролл с стрипсами".toFtsQuery())
        assertEquals("ролл* стрипсами*", "ролл со стрипсами".toFtsQuery())
        assertEquals("ролл* стрипсами*", "ролл стрипсами".toFtsQuery())
    }
}
