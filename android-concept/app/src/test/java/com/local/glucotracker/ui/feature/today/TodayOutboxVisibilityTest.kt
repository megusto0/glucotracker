package com.local.glucotracker.ui.feature.today

import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import kotlinx.datetime.Instant
import org.junit.Assert.assertEquals
import org.junit.Test

class TodayOutboxVisibilityTest {
    private val capturedAt = Instant.parse("2026-07-21T15:07:46Z")

    @Test
    fun linkedPhotoStaysVisibleWhileServerEstimateIsPending() {
        val item = OutboxItem(
            id = "outbox-1",
            kind = OutboxKind.CapturedMeal(
                localPhotoPath = "/photos/capture.jpg",
                capturedAt = capturedAt,
                source = "photo",
                idempotencyKey = "capture-key",
            ),
            state = OutboxState.Queued,
            createdAt = capturedAt,
            lastAttemptAt = capturedAt,
            attempts = 1,
            serverIdOnSuccess = "meal-1",
            errorMessage = null,
            linkedMealId = "meal-1",
        )

        assertEquals(listOf(item), visibleTodayOutbox(listOf(item), acceptedMeals = emptyList()))
    }
}
