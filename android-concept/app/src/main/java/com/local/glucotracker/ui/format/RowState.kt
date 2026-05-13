package com.local.glucotracker.ui.format

import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.domain.model.OutboxKind
import kotlin.time.Duration
import kotlin.time.Duration.Companion.minutes
import kotlin.time.Duration.Companion.seconds
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant

sealed class RowState {
    data object JustQueued : RowState()
    data object TryingNow : RowState()
    data class RetryInSeconds(val seconds: Int) : RowState()
    data class RetryInMinutes(val minutes: Int) : RowState()
    data object Estimating : RowState()
    data object EstimatingSlow : RowState()
    data class Stuck(val errorMessage: String?) : RowState()
    data object WaitingNetwork : RowState()
}

private val NetworkErrorCodes = setOf("server_unreachable", "no_network", "connect_timeout")

fun computeRowState(
    item: OutboxItem,
    isOnline: Boolean,
    now: Instant = Clock.System.now(),
): RowState = computeRowStateInternal(
    isPhotoDraft = item.kind is OutboxKind.CapturedMeal && item.draft == null,
    state = item.state,
    lastAttemptAt = item.lastAttemptAt,
    nextAttemptAt = item.nextAttemptAt,
    enteredCurrentStateAt = item.enteredCurrentStateAt,
    lastErrorCode = item.lastErrorCode,
    lastErrorMessage = item.lastErrorMessage ?: item.errorMessage,
    isOnline = isOnline,
    now = now,
)

fun computeRowState(
    state: OutboxState,
    lastAttemptAt: Instant?,
    nextAttemptAt: Instant?,
    enteredCurrentStateAt: Instant,
    lastErrorCode: String?,
    lastErrorMessage: String?,
    isPhotoDraft: Boolean,
    isOnline: Boolean,
    now: Instant = Clock.System.now(),
): RowState = computeRowStateInternal(
    isPhotoDraft = isPhotoDraft,
    state = state,
    lastAttemptAt = lastAttemptAt,
    nextAttemptAt = nextAttemptAt,
    enteredCurrentStateAt = enteredCurrentStateAt,
    lastErrorCode = lastErrorCode,
    lastErrorMessage = lastErrorMessage,
    isOnline = isOnline,
    now = now,
)

private fun computeRowStateInternal(
    isPhotoDraft: Boolean,
    state: OutboxState,
    lastAttemptAt: Instant?,
    nextAttemptAt: Instant?,
    enteredCurrentStateAt: Instant,
    lastErrorCode: String?,
    lastErrorMessage: String?,
    isOnline: Boolean,
    now: Instant,
): RowState {
    val timeInState = now - enteredCurrentStateAt

    return when (state) {
        OutboxState.Queued -> {
            if (isPhotoDraft) {
                return if (timeInState > 2.minutes) RowState.EstimatingSlow else RowState.Estimating
            }
            if (!isOnline) return RowState.WaitingNetwork
            if (lastErrorCode in NetworkErrorCodes && nextAttemptAt == null) {
                return RowState.WaitingNetwork
            }
            if (lastAttemptAt == null && nextAttemptAt == null) {
                RowState.JustQueued
            } else {
                val next = nextAttemptAt
                if (next != null && next > now) {
                    val remaining: Duration = next - now
                    if (remaining < 1.minutes) {
                        RowState.RetryInSeconds(remaining.inWholeSeconds.toInt().coerceAtLeast(1))
                    } else {
                        RowState.RetryInMinutes(remaining.inWholeMinutes.toInt())
                    }
                } else {
                    RowState.JustQueued
                }
            }
        }

        OutboxState.Uploading -> RowState.TryingNow

        OutboxState.Stuck -> RowState.Stuck(lastErrorMessage)

        OutboxState.Confirmed -> RowState.JustQueued
    }
}

fun pluralizeRecord(count: Int): String {
    val absCount = kotlin.math.abs(count)
    val mod10 = absCount % 10
    val mod100 = absCount % 100
    return when {
        mod100 in 11..19 -> "$count записей"
        mod10 == 1 -> "$count запись"
        mod10 in 2..4 -> "$count записи"
        else -> "$count записей"
    }
}
