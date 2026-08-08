package com.local.glucotracker.ui.feature.today

import com.local.glucotracker.domain.model.Meal
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Who owns the row for a photographed meal, and when it changes hands.
 *
 * Before the upload lands the optimistic outbox row is the better one — it has
 * the local file. After it lands the server's draft is, because only that row
 * carries `estimate_status`. Getting the handover wrong is not cosmetic: the
 * Today screen polls for a finished estimate only while a row says one is
 * running, so a row that cannot say it silently stops the refresh loop and the
 * status sits unchanged until something else happens to reload the day.
 *
 * That has now happened twice, from two different directions, which is why the
 * handover is pinned here rather than left to the two row builders to agree on.
 */
class PhotoEstimateRowHandoverTest {

    private val day = LocalDate(2026, 8, 8)
    private val capturedAt = Instant.parse("2026-08-08T02:26:29Z")

    private fun draftMeal(id: String, estimateStatus: String) = Meal(
        id = id,
        eatenAt = capturedAt,
        eatenAtDay = capturedAt.toLocalDateTime(TimeZone.currentSystemDefault()).date,
        title = null,
        status = "draft",
        source = "photo",
        note = null,
        thumbnailUrl = null,
        totalKcal = 0.0,
        totalCarbsG = 0.0,
        totalProteinG = 0.0,
        totalFatG = 0.0,
        totalFiberG = 0.0,
        updatedAt = capturedAt,
        estimateStatus = estimateStatus,
    )

    private fun capture(
        state: OutboxState,
        linkedMealId: String?,
        id: String = "outbox-1",
        at: Instant = capturedAt,
    ) = OutboxItem(
        id = id,
        kind = OutboxKind.CapturedMeal(
            localPhotoPath = "/data/photo.jpg",
            capturedAt = at,
            source = "photo",
        ),
        state = state,
        createdAt = at,
        lastAttemptAt = at,
        attempts = 1,
        serverIdOnSuccess = linkedMealId,
        errorMessage = null,
        linkedMealId = linkedMealId,
    )

    @Test
    fun `a confirmed upload hands the row to the server draft`() {
        val meal = draftMeal("meal-1", estimateStatus = "estimating")

        val rows = buildRows(
            date = day,
            acceptedMeals = emptyList(),
            backendDrafts = listOf(meal),
            outbox = listOf(capture(OutboxState.Confirmed, linkedMealId = "meal-1")),
        )

        assertEquals(1, rows.size)
        val row = rows.single()
        // The server's row, not the optimistic one: it is the only one that
        // knows the estimate is still running.
        assertEquals("meal-1", row.recordId)
        assertEquals("estimating", row.estimateStatus)
        assertEquals(TodayMealStatus.Estimating, row.status)
    }

    @Test
    fun `an upload still in flight keeps the optimistic row`() {
        val rows = buildRows(
            date = day,
            acceptedMeals = emptyList(),
            backendDrafts = listOf(draftMeal("meal-1", estimateStatus = "estimating")),
            outbox = listOf(capture(OutboxState.Uploading, linkedMealId = null)),
        )

        assertEquals(2, rows.size)
        assertTrue(rows.any { it.outboxId == "outbox-1" && it.recordId == null })
    }

    @Test
    fun `a confirmed upload whose meal has not arrived still shows a row`() {
        // The window between the upload confirming and the day cache catching
        // up. Dropping the optimistic row here would blink the entry out.
        val rows = buildRows(
            date = day,
            acceptedMeals = emptyList(),
            backendDrafts = emptyList(),
            outbox = listOf(capture(OutboxState.Confirmed, linkedMealId = "meal-1")),
        )

        assertEquals(1, rows.size)
        assertEquals("outbox-1", rows.single().outboxId)
        // And it says the estimate is running, because it is: a confirmed
        // upload is the moment estimation starts, not the moment it ends.
        assertEquals(TodayMealStatus.Estimating, rows.single().status)
    }

    @Test
    fun `an accepted meal retires the optimistic row`() {
        val accepted = draftMeal("meal-1", estimateStatus = "succeeded")
            .copy(status = "accepted", title = "Ряженка", totalKcal = 165.0)

        val rows = buildRows(
            date = day,
            acceptedMeals = listOf(accepted),
            backendDrafts = emptyList(),
            outbox = listOf(capture(OutboxState.Confirmed, linkedMealId = "meal-1")),
        )

        assertEquals(1, rows.size)
        assertEquals(TodayMealRowKind.Accepted, rows.single().kind)
    }

    @Test
    fun `first accepted photo does not hide a second estimate from the same minute`() {
        val accepted = draftMeal("meal-1", estimateStatus = "succeeded")
            .copy(status = "accepted", title = "First photo", totalKcal = 165.0)
        val first = capture(OutboxState.Confirmed, linkedMealId = "meal-1")
        val second = capture(
            state = OutboxState.Queued,
            linkedMealId = "meal-2",
            id = "outbox-2",
            at = Instant.parse("2026-08-08T02:26:39Z"),
        )

        val visibleOutbox = visibleTodayOutbox(
            outbox = listOf(first, second),
            acceptedMeals = listOf(accepted),
        )
        val rows = buildRows(
            date = day,
            acceptedMeals = listOf(accepted),
            backendDrafts = emptyList(),
            outbox = visibleOutbox,
        )

        assertEquals(listOf("outbox-2"), visibleOutbox.map { it.id })
        assertEquals(2, rows.size)
        val estimating = rows.single { it.outboxId == "outbox-2" }
        assertEquals(TodayMealStatus.Estimating, estimating.status)
    }
}
