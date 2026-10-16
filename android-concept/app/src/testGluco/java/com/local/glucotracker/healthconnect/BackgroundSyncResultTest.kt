package com.local.glucotracker.healthconnect

import androidx.work.ListenableWorker
import org.junit.Assert.assertEquals
import org.junit.Test

class BackgroundSyncResultTest {
    @Test
    fun `a successful upload succeeds`() {
        assertEquals(ListenableWorker.Result.success(), backgroundSyncResult(synced = true, runAttemptCount = 0))
    }

    @Test
    fun `a failed upload retries a few times, then gives way to the next run`() {
        // 2026-10-05: unbounded exponential retries reached attempt 18 and held
        // every later Bridge batch back for hours.
        (0 until MaxBackgroundRetries).forEach { attempt ->
            assertEquals(ListenableWorker.Result.retry(), backgroundSyncResult(synced = false, runAttemptCount = attempt))
        }
        assertEquals(
            ListenableWorker.Result.success(),
            backgroundSyncResult(synced = false, runAttemptCount = MaxBackgroundRetries),
        )
    }
}
