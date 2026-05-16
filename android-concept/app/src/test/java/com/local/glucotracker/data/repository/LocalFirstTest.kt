package com.local.glucotracker.data.repository

import app.cash.turbine.test
import com.local.glucotracker.domain.model.Source
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.runTest
import kotlinx.datetime.Instant
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalFirstTest {
    @Test
    fun emitsEmptyThenNetworkWhenRefreshPopulatesCache() = runTest {
        val cache = MutableStateFlow<String?>(null)
        val fetchedAt = Instant.parse("2026-05-05T10:00:00Z")

        localFirst(
            cache = { cache },
            refresh = { cache.value = "network" },
            now = { fetchedAt },
        ).test {
            val empty = awaitItem()
            assertNull(empty.value)
            assertEquals(Source.Empty, empty.source)
            assertFalse(empty.isRefreshing)

            val refreshing = awaitItem()
            assertNull(refreshing.value)
            assertEquals(Source.Empty, refreshing.source)
            assertTrue(refreshing.isRefreshing)

            val network = awaitItem()
            assertEquals("network", network.value)
            assertEquals(Source.Network, network.source)
            assertEquals(fetchedAt, network.fetchedAt)
            assertFalse(network.isRefreshing)

            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun emitsCacheThenNetworkThenLaterCacheUpdates() = runTest {
        val cache = MutableStateFlow<String?>("cache")

        localFirst(
            cache = { cache },
            refresh = { cache.value = "network" },
            now = { Instant.parse("2026-05-05T10:00:00Z") },
        ).test {
            assertEquals(Source.Cache, awaitItem().source)
            assertTrue(awaitItem().isRefreshing)

            val network = awaitItem()
            assertEquals("network", network.value)
            assertEquals(Source.Network, network.source)

            cache.value = "cache-again"
            val later = awaitItem()
            assertEquals("cache-again", later.value)
            assertEquals(Source.Cache, later.source)

            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun keepsCacheAndDoesNotEmitErrorWhenNetworkFails() = runTest {
        val cache = MutableStateFlow<String?>("cache")

        localFirst(
            cache = { cache },
            refresh = { error("offline") },
            now = { Instant.parse("2026-05-05T10:00:00Z") },
        ).test {
            val first = awaitItem()
            assertEquals("cache", first.value)
            assertEquals(Source.Cache, first.source)
            assertFalse(first.isRefreshing)

            val refreshing = awaitItem()
            assertEquals("cache", refreshing.value)
            assertTrue(refreshing.isRefreshing)

            val retained = awaitItem()
            assertEquals("cache", retained.value)
            assertEquals(Source.Cache, retained.source)
            assertFalse(retained.isRefreshing)

            expectNoEvents()
            cancelAndIgnoreRemainingEvents()
        }
    }
}
