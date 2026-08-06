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

/** Sleep or hard effort, as the day's background rather than as a record. */
data class BodyState(
    val kind: Kind,
    val startAt: Instant,
    val endAt: Instant,
    /** Minutes the state lasted, which a night crossing midnight keeps whole. */
    val totalMinutes: Int,
    /** Inferred states are the app's reading of heart rate, not the watch's. */
    val inferred: Boolean,
    val label: String?,
    /** Mean heart rate over the span — the evidence an inferred state rests on. */
    val meanBpm: Int?,
) {
    enum class Kind { Sleep, Activity }
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
        viewModelScope.launch {
            runCatching {
                glucoseApi.bodyStates(
                    from = date.atStartOfDayIn(zone),
                    to = date.plus(DatePeriod(days = 1)).atStartOfDayIn(zone),
                ).states.map { it.toDomain() }
            }.onSuccess { states ->
                byDate.value = byDate.value + (date to states)
            }.onFailure {
                synchronized(requested) { requested.remove(date) }
            }
        }
    }
}

private fun BodyStateIntervalResponse.toDomain(): BodyState = BodyState(
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
)
