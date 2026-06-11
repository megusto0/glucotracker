package com.local.glucotracker.ui.glucose

import com.local.glucotracker.domain.model.CreateNightscoutInsulinOutboxKind
import com.local.glucotracker.domain.model.InsulinEvent
import com.local.glucotracker.domain.model.InsulinEventType
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxState
import kotlin.time.Duration.Companion.minutes
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class InsulinContextMergeTest {

    @Test
    fun pendingOutboxInsulinIsShownOptimistically() {
        val recordedAt = Clock.System.now()
        val merged = mergeInsulinEvents(
            server = emptyList(),
            pending = listOf(PendingInsulin(outboxId = "ob-1", recordedAt = recordedAt, units = 3.5)),
        )

        assertEquals(1, merged.size)
        val event = merged.single()
        assertTrue(event.isPending)
        assertEquals(3.5, event.doseUnits, 0.0)
        assertEquals(recordedAt, event.timestamp)
    }

    @Test
    fun pendingRowIsDroppedWhenServerHasMatchingEvent() {
        val recordedAt = Clock.System.now()
        val serverEvent = serverEvent(timestamp = recordedAt + 1.minutes, dose = 3.5)
        val merged = mergeInsulinEvents(
            server = listOf(serverEvent),
            pending = listOf(PendingInsulin(outboxId = "ob-1", recordedAt = recordedAt, units = 3.5)),
        )

        assertEquals(listOf(serverEvent), merged)
    }

    @Test
    fun pendingRowIsKeptWhenDoseDiffers() {
        val recordedAt = Clock.System.now()
        val merged = mergeInsulinEvents(
            server = listOf(serverEvent(timestamp = recordedAt, dose = 2.0)),
            pending = listOf(PendingInsulin(outboxId = "ob-1", recordedAt = recordedAt, units = 3.5)),
        )

        assertEquals(2, merged.size)
        assertEquals(1, merged.count { it.isPending })
    }

    @Test
    fun outboxItemsAreFilteredToInsulinKindAndDate() {
        val now = Clock.System.now()
        val today = now.toLocalDateTime(TimeZone.currentSystemDefault()).date
        val items = listOf(
            insulinOutboxItem(id = "today", recordedAt = now, units = 2.0),
            insulinOutboxItem(id = "old", recordedAt = now - (26 * 60).minutes, units = 4.0),
        )

        val pending = items.pendingInsulinForDate(today)

        assertEquals(listOf("today"), pending.map { it.outboxId })
    }

    @Test
    fun signatureTracksItemSet() {
        val now = Clock.System.now()
        val one = listOf(PendingInsulin("a", now, 1.0))
        val two = listOf(PendingInsulin("a", now, 1.0), PendingInsulin("b", now, 2.0))

        assertTrue(one.signature() != two.signature())
        assertEquals(one.signature(), listOf(PendingInsulin("a", now, 1.0)).signature())
    }

    private fun serverEvent(timestamp: Instant, dose: Double): InsulinEvent =
        InsulinEvent(
            id = "srv-$dose",
            timestamp = timestamp,
            doseUnits = dose,
            source = "Nightscout",
            sourceEventId = "srv-$dose",
            eventType = InsulinEventType.Bolus,
        )

    private fun insulinOutboxItem(id: String, recordedAt: Instant, units: Double): OutboxItem =
        OutboxItem(
            id = id,
            kind = CreateNightscoutInsulinOutboxKind(
                recordedAt = recordedAt,
                insulinUnits = units,
                idempotencyKey = "key-$id",
            ),
            state = OutboxState.Queued,
            createdAt = recordedAt,
            lastAttemptAt = null,
            nextAttemptAt = null,
            attempts = 0,
            serverIdOnSuccess = null,
            errorMessage = null,
            enteredCurrentStateAt = recordedAt,
        )
}
