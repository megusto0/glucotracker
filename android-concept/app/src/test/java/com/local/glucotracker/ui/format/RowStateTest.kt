package com.local.glucotracker.ui.format

import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.domain.model.MealDraft
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.minutes
import kotlin.time.Duration.Companion.seconds
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant
import org.junit.Assert.assertEquals
import org.junit.Test

class RowStateTest {

    private val now: Instant = Clock.System.now()
    private val photoKind = OutboxKind.CapturedMeal(
        localPhotoPath = "/tmp/photo.jpg",
        capturedAt = now,
        source = "photo",
    )

    private val createMealKind = OutboxKind.CreateMeal(
        payload = MealDraft(
            id = "draft-1",
            eatenAt = now,
            title = "test",
            note = null,
            localPhotoPath = null,
            totalKcal = 500.0,
            totalCarbsG = 50.0,
            totalProteinG = 25.0,
            totalFatG = 20.0,
            totalFiberG = 5.0,
        ),
        eatenAt = now,
        source = "text",
    )

    private fun item(
        state: OutboxState = OutboxState.Queued,
        kind: OutboxKind = createMealKind,
        lastAttemptAt: Instant? = null,
        nextAttemptAt: Instant? = null,
        enteredCurrentStateAt: Instant = now,
        lastErrorCode: String? = null,
        errorMessage: String? = null,
        draft: MealDraft? = null,
    ) = OutboxItem(
        id = "test-id",
        kind = kind,
        state = state,
        createdAt = now - 5.minutes,
        lastAttemptAt = lastAttemptAt,
        nextAttemptAt = nextAttemptAt,
        attempts = 0,
        serverIdOnSuccess = null,
        errorMessage = errorMessage,
        enteredCurrentStateAt = enteredCurrentStateAt,
        lastErrorCode = lastErrorCode,
        lastErrorMessage = errorMessage,
        draft = draft,
    )

    @Test
    fun justQueued_neverAttempted() {
        val result = computeRowState(item(), isOnline = true, now = now)
        assertEquals(RowState.JustQueued, result)
    }

    @Test
    fun tryingNow_uploadingState() {
        val result = computeRowState(
            item(state = OutboxState.Uploading),
            isOnline = true,
            now = now,
        )
        assertEquals(RowState.TryingNow, result)
    }

    @Test
    fun retryInSeconds_backoffLessThanMinute() {
        val result = computeRowState(
            item(
                lastAttemptAt = now - 30.seconds,
                nextAttemptAt = now + 45.seconds,
            ),
            isOnline = true,
            now = now,
        )
        assertEquals(RowState.RetryInSeconds(45), result)
    }

    @Test
    fun retryInMinutes_backoffOverMinute() {
        val result = computeRowState(
            item(
                lastAttemptAt = now - 1.minutes,
                nextAttemptAt = now + 3.minutes,
            ),
            isOnline = true,
            now = now,
        )
        assertEquals(RowState.RetryInMinutes(3), result)
    }

    @Test
    fun retryBackoffExpired_showsJustQueued() {
        val result = computeRowState(
            item(
                lastAttemptAt = now - 5.minutes,
                nextAttemptAt = now - 1.minutes,
            ),
            isOnline = true,
            now = now,
        )
        assertEquals(RowState.JustQueued, result)
    }

    @Test
    fun estimating_photoDraftNoResult() {
        val result = computeRowState(
            item(kind = photoKind, draft = null),
            isOnline = true,
            now = now,
        )
        assertEquals(RowState.Estimating, result)
    }

    @Test
    fun estimatingSlow_photoDraftOverTwoMinutes() {
        val result = computeRowState(
            item(
                kind = photoKind,
                draft = null,
                enteredCurrentStateAt = now - 3.minutes,
            ),
            isOnline = true,
            now = now,
        )
        assertEquals(RowState.EstimatingSlow, result)
    }

    @Test
    fun estimating_photoDraftWithResult_notEstimating() {
        val draft = MealDraft(
            id = "draft-1",
            eatenAt = now,
            title = "pizza",
            note = null,
            localPhotoPath = null,
            totalKcal = 600.0,
            totalCarbsG = 60.0,
            totalProteinG = 30.0,
            totalFatG = 25.0,
            totalFiberG = 5.0,
        )
        val result = computeRowState(
            item(kind = photoKind, draft = draft),
            isOnline = true,
            now = now,
        )
        assertEquals(RowState.JustQueued, result)
    }

    @Test
    fun stuck_withErrorMessage() {
        val result = computeRowState(
            item(state = OutboxState.Stuck, errorMessage = "server error"),
            isOnline = true,
            now = now,
        )
        assertEquals(RowState.Stuck("server error"), result)
    }

    @Test
    fun stuck_withoutErrorMessage() {
        val result = computeRowState(
            item(state = OutboxState.Stuck, errorMessage = null),
            isOnline = true,
            now = now,
        )
        assertEquals(RowState.Stuck(null), result)
    }

    @Test
    fun waitingNetwork_offline() {
        val result = computeRowState(
            item(lastAttemptAt = now - 1.minutes, nextAttemptAt = now + 2.minutes),
            isOnline = false,
            now = now,
        )
        assertEquals(RowState.WaitingNetwork, result)
    }

    @Test
    fun waitingNetwork_networkErrorCode_noNextAttempt() {
        val result = computeRowState(
            item(lastErrorCode = "no_network"),
            isOnline = true,
            now = now,
        )
        assertEquals(RowState.WaitingNetwork, result)
    }

    @Test
    fun waitingNetwork_serverUnreachableCode() {
        val result = computeRowState(
            item(lastErrorCode = "server_unreachable"),
            isOnline = true,
            now = now,
        )
        assertEquals(RowState.WaitingNetwork, result)
    }

    @Test
    fun waitingNetwork_connectTimeoutCode() {
        val result = computeRowState(
            item(lastErrorCode = "connect_timeout"),
            isOnline = true,
            now = now,
        )
        assertEquals(RowState.WaitingNetwork, result)
    }

    @Test
    fun notWaitingNetwork_nonNetworkErrorCode() {
        val result = computeRowState(
            item(lastErrorCode = "conflict"),
            isOnline = true,
            now = now,
        )
        assertEquals(RowState.JustQueued, result)
    }

    @Test
    fun confirmed_returnsJustQueued() {
        val result = computeRowState(
            item(state = OutboxState.Confirmed),
            isOnline = true,
            now = now,
        )
        assertEquals(RowState.JustQueued, result)
    }

    @Test
    fun retryInSeconds_minimumOneSecond() {
        val result = computeRowState(
            item(
                lastAttemptAt = now - 30.seconds,
                nextAttemptAt = now + 200.milliseconds,
            ),
            isOnline = true,
            now = now,
        )
        val sec = (result as RowState.RetryInSeconds).seconds
        assertEquals(1, sec)
    }
}

class PluralizeRecordTest {
    @Test
    fun singularOne() {
        assertEquals("1 запись", pluralizeRecord(1))
    }

    @Test
    fun twoToFour() {
        assertEquals("2 записи", pluralizeRecord(2))
        assertEquals("3 записи", pluralizeRecord(3))
        assertEquals("4 записи", pluralizeRecord(4))
    }

    @Test
    fun fiveToNine() {
        assertEquals("5 записей", pluralizeRecord(5))
        assertEquals("9 записей", pluralizeRecord(9))
    }

    @Test
    fun elevenToNineteen() {
        assertEquals("11 записей", pluralizeRecord(11))
        assertEquals("15 записей", pluralizeRecord(15))
        assertEquals("19 записей", pluralizeRecord(19))
    }

    @Test
    fun twentyOne() {
        assertEquals("21 запись", pluralizeRecord(21))
    }

    @Test
    fun twentyTwo() {
        assertEquals("22 записи", pluralizeRecord(22))
    }

    @Test
    fun twentyFive() {
        assertEquals("25 записей", pluralizeRecord(25))
    }

    @Test
    fun oneHundredEleven() {
        assertEquals("111 записей", pluralizeRecord(111))
    }

    @Test
    fun oneHundredTwentyOne() {
        assertEquals("121 запись", pluralizeRecord(121))
    }

    @Test
    fun zero() {
        assertEquals("0 записей", pluralizeRecord(0))
    }
}
