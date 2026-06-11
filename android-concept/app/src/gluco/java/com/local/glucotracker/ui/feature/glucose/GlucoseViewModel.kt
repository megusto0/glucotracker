package com.local.glucotracker.ui.feature.glucose

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.CreateFingerstickOutboxKind
import com.local.glucotracker.domain.model.GlucoseRange
import com.local.glucotracker.domain.model.GlucoseReading
import com.local.glucotracker.domain.model.Meal
import com.local.glucotracker.domain.repository.GlucoseRepository
import com.local.glucotracker.domain.repository.HistoryRepository
import com.local.glucotracker.domain.repository.OutboxRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlin.math.roundToInt
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

enum class GlucoseWindow(val hours: Int) {
    ThreeHours(hours = 3),
    SixHours(hours = 6),
    Day(hours = 24),
    Week(hours = 24 * 7),
}

data class GlucoseScreenState(
    val selectedWindow: GlucoseWindow,
    val windows: List<GlucoseWindowState>,
    val dayparts: List<GlucoseDaypartUi>,
)

data class GlucoseWindowState(
    val window: GlucoseWindow,
    val from: Instant,
    val to: Instant,
    val readings: List<GlucoseReading>,
    val mealMarkers: List<Instant>,
    val tirSegments: List<GlucoseTirSegmentUi>,
    val tirFetchedAt: Instant?,
    val hasGap: Boolean,
    val latest: GlucoseReading?,
    val latestAgeMinutes: Int?,
    val delta15Mmol: Double?,
)

data class GlucoseTirSegmentUi(
    val bucket: GlucoseTirBucket,
    val percent: Int?,
)

enum class GlucoseTirBucket {
    VeryLow,
    Low,
    InRange,
    High,
    VeryHigh,
}

data class GlucoseDaypartUi(
    val label: String,
    val valueMmol: Double?,
    val belowRangePercent: Int?,
)

@HiltViewModel
@OptIn(ExperimentalCoroutinesApi::class)
class GlucoseViewModel @Inject constructor(
    glucoseRepository: GlucoseRepository,
    historyRepository: HistoryRepository,
    private val outboxRepository: OutboxRepository,
) : ViewModel() {
    private val selectedWindow = MutableStateFlow(GlucoseWindow.ThreeHours)
    private val anchor = MutableStateFlow(Clock.System.now())
    private val windows = GlucoseWindow.entries

    private val glucoseWindows = anchor.flatMapLatest { currentAnchor ->
        combine(
            windows.map { window ->
                val from = currentAnchor.minusHours(window.hours)
                glucoseRepository.observeRange(from = from, to = currentAnchor).map { cached ->
                    window to cached
                }
            },
        ) { entries -> entries.toList().toMap() }
    }

    private val mealWindows = anchor.flatMapLatest { currentAnchor ->
        combine(
            windows.map { window ->
                val from = currentAnchor.minusHours(window.hours)
                historyRepository.observeCachedMeals(from = from, to = currentAnchor).map { meals ->
                    window to meals
                }
            },
        ) { entries -> entries.toList().toMap() }
    }

    val state = combine(
        selectedWindow,
        glucoseWindows,
        mealWindows,
    ) { selected, glucoseByWindow, mealsByWindow ->
        val currentAnchor = anchor.value
        val windowStates = windows.map { window ->
            val from = currentAnchor.minusHours(window.hours)
            glucoseByWindow.getValue(window).toWindowState(
                window = window,
                from = from,
                to = currentAnchor,
                meals = mealsByWindow[window].orEmpty(),
            )
        }
        GlucoseScreenState(
            selectedWindow = selected,
            windows = windowStates,
            dayparts = windowStates
                .firstOrNull { it.window == GlucoseWindow.Day }
                ?.readings
                .orEmpty()
                .toDayparts(),
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = GlucoseScreenState(
            selectedWindow = GlucoseWindow.ThreeHours,
            windows = windows.map { window ->
                val currentAnchor = anchor.value
                GlucoseWindowState(
                    window = window,
                    from = currentAnchor.minusHours(window.hours),
                    to = currentAnchor,
                    readings = emptyList(),
                    mealMarkers = emptyList(),
                    tirSegments = emptyTirSegments(),
                    tirFetchedAt = null,
                    hasGap = false,
                    latest = null,
                    latestAgeMinutes = null,
                    delta15Mmol = null,
                )
            },
            dayparts = emptyDayparts(),
        ),
    )

    fun selectWindow(window: GlucoseWindow) {
        selectedWindow.value = window
    }

    fun refresh() {
        anchor.value = Clock.System.now()
    }

    fun enqueueFingerstick(valueMmol: Double) {
        viewModelScope.launch {
            outboxRepository.enqueue(
                CreateFingerstickOutboxKind(
                    measuredAt = Clock.System.now(),
                    glucoseMmolL = valueMmol,
                ),
            )
        }
    }
}

private fun CachedView<GlucoseRange>.toWindowState(
    window: GlucoseWindow,
    from: Instant,
    to: Instant,
    meals: List<Meal>,
): GlucoseWindowState {
    val readings = value?.readings.orEmpty()
    val latest = readings.lastOrNull()
    val latestAgeMinutes = latest?.readingAt?.minutesUntil(Clock.System.now())
    val stale = latestAgeMinutes != null && latestAgeMinutes > 15
    val delta15 = if (stale) null else latest?.delta15(readings)
    return GlucoseWindowState(
        window = window,
        from = from,
        to = to,
        readings = readings,
        mealMarkers = meals.map { it.eatenAt },
        tirSegments = readings.toTirSegments(),
        tirFetchedAt = fetchedAt,
        hasGap = window.requiresGapKicker() && readings.hasGap(from, to),
        latest = latest,
        latestAgeMinutes = latestAgeMinutes,
        delta15Mmol = delta15,
    )
}

// Display thresholds, same scale as the settings TIR strip (3.0 · 3.9 · 10.0 · 13.0).
private const val VeryLowThresholdMmol = 3.0
private const val LowThresholdMmol = 3.9
private const val HighThresholdMmol = 10.0
private const val VeryHighThresholdMmol = 13.0

private fun Double.toTirBucket(): GlucoseTirBucket =
    when {
        this < VeryLowThresholdMmol -> GlucoseTirBucket.VeryLow
        this < LowThresholdMmol -> GlucoseTirBucket.Low
        this <= HighThresholdMmol -> GlucoseTirBucket.InRange
        this <= VeryHighThresholdMmol -> GlucoseTirBucket.High
        else -> GlucoseTirBucket.VeryHigh
    }

private fun List<GlucoseReading>.toTirSegments(): List<GlucoseTirSegmentUi> {
    if (isEmpty()) return emptyTirSegments()
    val counts = groupingBy { it.displayValueMmolL.toTirBucket() }.eachCount()
    val percents = largestRemainderPercents(
        GlucoseTirBucket.entries.map { counts[it] ?: 0 },
        total = size,
    )
    return GlucoseTirBucket.entries.mapIndexed { index, bucket ->
        GlucoseTirSegmentUi(bucket, percents[index])
    }
}

/** Round counts to integer percents that always sum to 100. */
private fun largestRemainderPercents(counts: List<Int>, total: Int): List<Int> {
    val exact = counts.map { it * 100.0 / total }
    val floors = exact.map { it.toInt() }.toMutableList()
    val leftover = 100 - floors.sum()
    exact
        .mapIndexed { index, value -> index to value - floors[index] }
        .sortedByDescending { it.second }
        .take(leftover.coerceAtLeast(0))
        .forEach { (index, _) -> floors[index] += 1 }
    return floors
}

private fun emptyTirSegments(): List<GlucoseTirSegmentUi> =
    GlucoseTirBucket.entries.map { GlucoseTirSegmentUi(it, null) }

private fun List<GlucoseReading>.toDayparts(): List<GlucoseDaypartUi> {
    if (isEmpty()) return emptyDayparts()
    return DaypartRanges.map { range ->
        val values = filter { reading ->
            reading.readingAt.toLocalDateTime(TimeZone.currentSystemDefault()).time.hour in range.hourRange
        }
        val belowCount = values.count { it.displayValueMmolL < LowThresholdMmol }
        GlucoseDaypartUi(
            label = range.label,
            valueMmol = values.map { it.displayValueMmolL }.averageOrNull(),
            belowRangePercent = if (values.isEmpty()) {
                null
            } else {
                (belowCount * 100.0 / values.size).roundToInt()
            },
        )
    }
}

private fun emptyDayparts(): List<GlucoseDaypartUi> =
    DaypartRanges.map { GlucoseDaypartUi(label = it.label, valueMmol = null, belowRangePercent = null) }

private data class DaypartRange(
    val label: String,
    val hourRange: IntRange,
)

private val DaypartRanges = listOf(
    DaypartRange("00-04", 0..3),
    DaypartRange("04-08", 4..7),
    DaypartRange("08-12", 8..11),
    DaypartRange("12-16", 12..15),
    DaypartRange("16-20", 16..19),
    DaypartRange("20-24", 20..23),
)

private fun GlucoseWindow.requiresGapKicker(): Boolean =
    this == GlucoseWindow.Day || this == GlucoseWindow.Week

private fun List<GlucoseReading>.hasGap(from: Instant, to: Instant): Boolean {
    if (isEmpty()) return false
    val first = first().readingAt
    val last = last().readingAt
    return first.toEpochMilliseconds() - from.toEpochMilliseconds() > 20 * 60 * 1_000L ||
        to.toEpochMilliseconds() - last.toEpochMilliseconds() > 20 * 60 * 1_000L
}

private fun GlucoseReading.delta15(readings: List<GlucoseReading>): Double? {
    val target = readingAt.toEpochMilliseconds() - 15 * 60 * 1_000L
    val baseline = readings.lastOrNull { reading -> reading.readingAt.toEpochMilliseconds() <= target }
    return baseline?.let { displayValueMmolL - it.displayValueMmolL }
}

private fun Instant.minusHours(hours: Int): Instant =
    Instant.fromEpochMilliseconds(toEpochMilliseconds() - hours * 60L * 60L * 1_000L)

private fun Instant.minutesUntil(other: Instant): Int =
    ((other.toEpochMilliseconds() - toEpochMilliseconds()) / 60_000L)
        .coerceAtLeast(0L)
        .toInt()

private fun List<Double>.averageOrNull(): Double? =
    if (isEmpty()) null else average()
