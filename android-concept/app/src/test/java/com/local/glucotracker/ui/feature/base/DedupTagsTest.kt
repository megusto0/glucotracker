package com.local.glucotracker.ui.feature.base

import org.junit.Assert.assertEquals
import org.junit.Test

class DedupTagsTest {
    @Test
    fun removesExactDuplicates() {
        assertEquals(listOf("restaurant", "fast food"), dedupTags(listOf("restaurant", "fast food", "restaurant")))
    }

    @Test
    fun preservesOrder() {
        assertEquals(listOf("a", "b", "c"), dedupTags(listOf("a", "b", "a", "c", "b")))
    }

    @Test
    fun emptyListReturnsEmpty() {
        assertEquals(emptyList<String>(), dedupTags(emptyList()))
    }

    @Test
    fun noDuplicatesReturnsSame() {
        assertEquals(listOf("x", "y"), dedupTags(listOf("x", "y")))
    }
}
