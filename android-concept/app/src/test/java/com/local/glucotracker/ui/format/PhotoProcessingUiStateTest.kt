package com.local.glucotracker.ui.format

import com.local.glucotracker.domain.model.Meal
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import kotlin.time.Duration.Companion.seconds
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test

class PhotoProcessingUiStateTest {
    private val now = Instant.parse("2026-05-13T12:00:00Z")
    private val capturedKind = OutboxKind.CapturedMeal(
        localPhotoPath = "/tmp/photo.jpg",
        capturedAt = now,
        source = "photo",
    )

    @Test
    fun queuedPhotoShowsQueuePosition() {
        val state = mapOutboxAndMealToPhotoProcessingUiState(
            outboxItem = outboxItem(state = OutboxState.Queued),
            queuePosition = 3,
            queueSize = 3,
        )

        assertEquals(PhotoProcessingStage.WaitingUpload, state?.stage)
        assertEquals("ждёт отправки · очередь 3 из 3", state?.statusText)
        assertEquals("начнём после предыдущих фото", state?.helperText)
    }

    @Test
    fun uploadingPhotoUsesOnlyRealProgress() {
        val state = mapOutboxAndMealToPhotoProcessingUiState(
            outboxItem = outboxItem(state = OutboxState.Uploading),
            uploadProgress = 0.64f,
        )

        assertEquals(PhotoProcessingStage.Uploading, state?.stage)
        assertEquals("отправляем фото · 64%", state?.statusText)
        assertEquals(0.64f, state?.uploadProgress ?: 0f, 0.001f)
    }

    @Test
    fun estimatingPhotoShowsCountdown() {
        val state = estimatingState(
            estimateStartedAt = now - 50.seconds,
            now = now,
        )

        assertEquals(PhotoProcessingStage.Estimating, state.stage)
        assertEquals("модель оценивает · осталось до 40 сек", state.statusText)
        assertEquals(50, state.estimateElapsedSeconds)
    }

    @Test
    fun timedOutEstimateBecomesStuckWithoutRawException() {
        val state = estimatingState(
            estimateStartedAt = now - 95.seconds,
            now = now,
        )

        assertEquals(PhotoProcessingStage.Stuck, state.stage)
        assertEquals("оценка не пришла · исправляем", state.statusText)
        assertFalse(state.statusText.contains("UPDATE statement"))
    }

    @Test
    fun acceptedMealDoesNotGetPendingPipeline() {
        val state = mapOutboxAndMealToPhotoProcessingUiState(
            meal = meal(status = "accepted", estimateStatus = null),
            now = now,
        )

        assertNull(state)
    }

    private fun outboxItem(state: OutboxState): OutboxItem =
        OutboxItem(
            id = "outbox-1",
            kind = capturedKind,
            state = state,
            createdAt = now,
            lastAttemptAt = null,
            attempts = 0,
            serverIdOnSuccess = null,
            errorMessage = "UPDATE statement failed",
            enteredCurrentStateAt = now,
            lastErrorMessage = "UPDATE statement failed",
        )

    private fun meal(
        status: String = "draft",
        estimateStatus: String? = "estimating",
    ): Meal =
        Meal(
            id = "meal-1",
            eatenAt = now,
            eatenAtDay = LocalDate.parse("2026-05-13"),
            title = null,
            status = status,
            source = "photo",
            note = null,
            thumbnailUrl = null,
            totalKcal = 0.0,
            totalCarbsG = 0.0,
            totalProteinG = 0.0,
            totalFatG = 0.0,
            totalFiberG = 0.0,
            updatedAt = now - 10.seconds,
            estimateStatus = estimateStatus,
            estimateError = "UPDATE statement failed",
        )
}
