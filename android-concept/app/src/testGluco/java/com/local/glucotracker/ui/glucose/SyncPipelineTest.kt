package com.local.glucotracker.ui.glucose

import com.local.glucotracker.wearable.HelioBridgeStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SyncPipelineTest {
    private val minute = 60_000L
    private val now = 1_791_190_000_000L

    private val bridge = HelioBridgeStatus(
        installed = true,
        phase = "idle",
        connected = true,
        lastCompleteAt = now - 2 * minute,
        dataThroughAt = now - 3 * minute,
    )
    private val upload = HcSyncStatus(
        lastSyncAt = now - minute,
        records = 6,
        latestHeartRateBpm = 70,
        latestHeartRateAt = now - 4 * minute,
    )

    private fun pipeline(
        bridge: HelioBridgeStatus = this.bridge,
        upload: HcSyncStatus = this.upload,
        uploading: Boolean = false,
    ) = syncPipeline(bridge, upload, uploading, uploadedSoFar = 0, now = now)

    @Test
    fun `fresh data through every hop is all ok`() {
        val p = pipeline()
        assertTrue(p.allOk)
        assertNull(p.headline)
        assertEquals(SyncDetail.DataThrough(now - 3 * minute), p.strap.detail)
        assertEquals(SyncDetail.HeartRate(70), p.healthConnect.detail)
        assertEquals(SyncDetail.Uploaded(6), p.server.detail)
    }

    @Test
    fun `transfers that bring no new strap data blame the strap`() {
        // 2026-10-05: Bridge "complete" at 12:21 while the newest sample was 09:40.
        val silentSince = now - 27 * 60 * minute
        val p = pipeline(bridge = bridge.copy(dataThroughAt = silentSince))
        assertEquals(SyncStepState.Waiting, p.strap.state)
        assertEquals(SyncDetail.StrapSilent(silentSince), p.headline?.detail)
    }

    @Test
    fun `a batch handed over after the last upload is waiting for the server`() {
        // The upload after that batch sat in exponential retry for hours.
        val p = pipeline(upload = upload.copy(lastSyncAt = now - 90 * minute))
        assertEquals(SyncStepState.Waiting, p.server.state)
        assertEquals(SyncDetail.UploadPending, p.headline?.detail)
    }

    @Test
    fun `a failed upload outranks a stall and names its error`() {
        val p = pipeline(
            bridge = bridge.copy(dataThroughAt = now - 120 * minute),
            upload = upload.copy(error = "HTTP 502"),
        )
        assertEquals(SyncDetail.UploadFailed("HTTP 502"), p.headline?.detail)
    }

    @Test
    fun `health connect behind bridge is its own stall`() {
        val p = pipeline(upload = upload.copy(latestHeartRateAt = now - 60 * minute))
        assertEquals(SyncStepState.Waiting, p.healthConnect.state)
    }

    @Test
    fun `bridge errors and work in progress`() {
        assertEquals(
            SyncDetail.NotPaired,
            pipeline(bridge = bridge.copy(error = "not_paired", phase = "error")).headline?.detail,
        )
        assertEquals(
            SyncDetail.ConnectTimeout,
            pipeline(bridge = bridge.copy(error = "connect_timeout", phase = "error")).headline?.detail,
        )
        assertEquals(
            SyncDetail.Fetching,
            pipeline(bridge = bridge.copy(phase = "device_sync")).headline?.detail,
        )
        assertEquals(SyncStepState.Working, pipeline(uploading = true).server.state)
    }

    @Test
    fun `an older bridge without the new fields reads as unknown, not stalled`() {
        val p = pipeline(bridge = bridge.copy(lastCompleteAt = -1L, dataThroughAt = -1L))
        assertEquals(SyncDetail.NoStrapData, p.strap.detail)
        assertEquals(SyncStepState.Ok, p.server.state)
    }
}
