package com.local.glucotracker.ui.glucose

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.data.api.GlucoseApi
import com.local.glucotracker.generated.model.BodyStateIntervalResponse
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.datetime.DatePeriod
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.atStartOfDayIn
import kotlinx.datetime.plus
import kotlin.time.Duration.Companion.minutes

/** Sleep or hard effort, as the day's background rather than as a record. */
data class BodyState(
    val kind: Kind,
    /** Start inside the requested day: a night from yesterday starts at 00:00. */
    val startAt: Instant,
    /** End inside the requested day: a night into tomorrow ends at 24:00. */
    val endAt: Instant,
    /** Minutes the state lasted, which a night crossing midnight keeps whole. */
    val totalMinutes: Int,
    /** Inferred states are the app's reading of heart rate, not the watch's. */
    val inferred: Boolean,
    val label: String?,
    /** Mean heart rate over the span — the evidence an inferred state rests on. */
    val meanBpm: Int?,
    /** When it really began, before the day's start for a night from yesterday. */
    val wholeStartAt: Instant = startAt,
    /** When it really ended, after the day's end for a night into tomorrow. */
    val wholeEndAt: Instant = endAt,
    /** It runs past the end of the requested day, so it belongs to the next one. */
    val continuesAfterDay: Boolean = false,
) {
    enum class Kind { Sleep, Activity }
}

/**
 * Restores the whole span of a state the server clipped to the requested day.
 *
 * The server trims start and end to the day but keeps the full length, so
 * "23:25—00:00" came with 11 h 26 min attached, and the row printed exactly
 * that. Whichever end was cut is rebuilt from the length.
 */
internal fun wholeSpan(
    startAt: Instant,
    endAt: Instant,
    visibleMinutes: Int,
    totalMinutes: Int,
    dayStart: Instant,
    dayEnd: Instant,
): Triple<Instant, Instant, Boolean> {
    if (totalMinutes <= visibleMinutes) return Triple(startAt, endAt, false)
    val missing = (totalMinutes - visibleMinutes).minutes
    val cutAtEnd = endAt >= dayEnd
    val cutAtStart = startAt <= dayStart
    return when {
        cutAtEnd && !cutAtStart -> Triple(startAt, endAt + missing, true)
        cutAtStart && !cutAtEnd -> Triple(startAt - missing, endAt, false)
        // Longer than the whole day: where the rest falls is unknown, but it
        // still runs on past the end.
        cutAtEnd -> Triple(startAt, endAt, true)
        else -> Triple(startAt, endAt, false)
    }
}

/**
 * Minutes slept and minutes of hard effort that belong to one day.
 *
 * A state belongs to the day it ends on, with its whole length. Summing every
 * state the day touched counted a night crossing midnight on both days: on
 * 2026-10-02 the night that ended that morning (7:30) plus the next night,
 * begun at 23:25 (11:26), came to "18:56 сон".
 */
internal fun dayBodyStateTotals(states: List<BodyState>): Pair<Int, Int> {
    val owned = states.filterNot { it.continuesAfterDay }
    return owned.filter { it.kind == BodyState.Kind.Sleep }.sumOf { it.totalMinutes } to
        owned.filter { it.kind == BodyState.Kind.Activity }.sumOf { it.totalMinutes }
}

@HiltViewModel
class BodyStatesViewModel @Inject constructor(
    private val glucoseApi: GlucoseApi,
) : ViewModel() {
    private val byDate = MutableStateFlow<Map<LocalDate, List<BodyState>>>(emptyMap())
    val state: StateFlow<Map<LocalDate, List<BodyState>>> = byDate
    private val requested = mutableSetOf<LocalDate>()

    /**
     * Load once per day and keep it. These are read-only and change only when
     * the watch syncs, so re-fetching on every recomposition would cost a
     * request per scroll for a band that has not moved.
     */
    fun load(date: LocalDate) {
        synchronized(requested) {
            if (!requested.add(date)) return
        }
        val zone = TimeZone.currentSystemDefault()
        val dayStart = date.atStartOfDayIn(zone)
        val dayEnd = date.plus(DatePeriod(days = 1)).atStartOfDayIn(zone)
        viewModelScope.launch {
            runCatching {
                glucoseApi.bodyStates(from = dayStart, to = dayEnd)
                    .states.map { it.toDomain(dayStart, dayEnd) }
            }.onSuccess { states ->
                byDate.value = byDate.value + (date to states)
            }.onFailure {
                synchronized(requested) { requested.remove(date) }
            }
        }
    }
}

private fun BodyStateIntervalResponse.toDomain(dayStart: Instant, dayEnd: Instant): BodyState {
    val (wholeStart, wholeEnd, continues) =
        wholeSpan(startAt, endAt, minutes, totalMinutes, dayStart, dayEnd)
    return BodyState(
        kind = when (kind) {
            BodyStateIntervalResponse.Kind.SLEEP -> BodyState.Kind.Sleep
            BodyStateIntervalResponse.Kind.ACTIVITY -> BodyState.Kind.Activity
        },
        startAt = startAt,
        endAt = endAt,
        totalMinutes = totalMinutes,
        inferred = source == BodyStateIntervalResponse.Source.HEART_RATE,
        label = label,
        meanBpm = meanBpm?.toInt(),
        wholeStartAt = wholeStart,
        wholeEndAt = wholeEnd,
        continuesAfterDay = continues,
    )
}
