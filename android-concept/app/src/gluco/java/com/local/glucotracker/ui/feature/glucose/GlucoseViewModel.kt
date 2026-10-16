package com.local.glucotracker.ui.feature.glucose

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.domain.model.ActiveGlucoseContext
import com.local.glucotracker.domain.model.BodySpan
import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.CreateFingerstickOutboxKind
import com.local.glucotracker.domain.model.GlucoseRange
import com.local.glucotracker.domain.model.GlucoseEpisodeMark
import com.local.glucotracker.domain.model.GlucoseReading
import com.local.glucotracker.domain.model.GlucoseTirDay
import com.local.glucotracker.domain.model.InsulinEvent
import com.local.glucotracker.domain.model.InsulinEventType
import com.local.glucotracker.domain.model.Meal
import com.local.glucotracker.domain.model.SensorSession
import com.local.glucotracker.domain.repository.GlucoseContextRepository
import com.local.glucotracker.domain.repository.GlucoseRepository
import com.local.glucotracker.domain.repository.HistoryRepository
import com.local.glucotracker.domain.repository.OutboxRepository
import com.local.glucotracker.domain.repository.SensorRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

/**
 * The focus chart's span, as on Nightscout's main chart. The day itself is
 * the overview strip under it, not a third button.
 */
enum class FocusWindow(val hours: Int) {
    ThreeHours(hours = 3),
    SixHours(hours = 6),
}

/** An accepted meal; carbs are the server's total for it. */
data class GlucoseMealMarker(
    val id: String,
    val at: Instant,
    val title: String?,
    val carbsG: Double,
)

/** One carbs mark on the chart: a whole sitting, or a meal not yet grouped. */
data class CarbMark(
    val at: Instant,
    /** The server's total for the sitting, or the meal's own server carbs. */
    val grams: Double,
)

enum class InsulinTint { Food, Correction, Basal }

/** One insulin mark: a sitting's total dose, or a dose not yet grouped. */
data class InsulinMark(
    val at: Instant,
    val units: Double,
    val tint: InsulinTint,
    val pending: Boolean = false,
)

data class GlucoseScreenState(
    /** The overview day: the last 24 hours. */
    val dayFrom: Instant,
    val now: Instant,
    val focusWindow: FocusWindow,
    /** End of the focus window; equals [now] while following live. */
    val focusEnd: Instant,
    val isLive: Boolean,
    val readings: List<GlucoseReading>,
    val latest: GlucoseReading?,
    val latestAgeMinutes: Int?,
    val delta15Mmol: Double?,
    val meals: List<GlucoseMealMarker>,
    val insulin: List<InsulinEvent>,
    val bodySpans: List<BodySpan>,
    /** What the chart draws: one carbs and one insulin mark per sitting. */
    val carbMarks: List<CarbMark>,
    val insulinMarks: List<InsulinMark>,
    /** Server IOB/COB; null offline or before the first refresh. */
    val active: ActiveGlucoseContext?,
    /** Server TIR for today; null offline or when today has no CGM yet. */
    val tirToday: GlucoseTirDay?,
    val activeSensor: SensorSession?,
) {
    val focusFrom: Instant get() = focusEnd.minusHours(focusWindow.hours)
    val isStale: Boolean get() = latestAgeMinutes != null && latestAgeMinutes > StaleAfterMinutes

    companion object {
        fun empty(now: Instant) = GlucoseScreenState(
            dayFrom = now.minusHours(OverviewHours),
            now = now,
            focusWindow = FocusWindow.ThreeHours,
            focusEnd = now,
            isLive = true,
            readings = emptyList(),
            latest = null,
            latestAgeMinutes = null,
            delta15Mmol = null,
            meals = emptyList(),
            insulin = emptyList(),
            bodySpans = emptyList(),
            carbMarks = emptyList(),
            insulinMarks = emptyList(),
            active = null,
            tirToday = null,
            activeSensor = null,
        )
    }
}

internal const val StaleAfterMinutes = 15
internal const val OverviewHours = 24

/** Server-only context: absent offline, refreshed with the screen. */
private data class ServerContext(
    val bodySpans: List<BodySpan> = emptyList(),
    val episodes: List<GlucoseEpisodeMark> = emptyList(),
    val active: ActiveGlucoseContext? = null,
    val tirToday: GlucoseTirDay? = null,
)

private data class Focus(
    val window: FocusWindow = FocusWindow.ThreeHours,
    /** Null while following live; otherwise where the user scrolled to. */
    val end: Instant? = null,
)

private data class DayData(
    val from: Instant,
    val now: Instant,
    val glucose: CachedView<GlucoseRange>,
    val meals: List<Meal>,
    val insulin: List<InsulinEvent>,
)

@HiltViewModel
@OptIn(ExperimentalCoroutinesApi::class)
class GlucoseViewModel @Inject constructor(
    glucoseRepository: GlucoseRepository,
    historyRepository: HistoryRepository,
    private val contextRepository: GlucoseContextRepository,
    private val outboxRepository: OutboxRepository,
    private val sensorRepository: SensorRepository,
) : ViewModel() {
    private val anchor = MutableStateFlow(Clock.System.now())
    private val focus = MutableStateFlow(Focus())
    private val server = MutableStateFlow(ServerContext())

    /** One load for the whole day; the focus window is a slice of it. */
    private val dayData = anchor.flatMapLatest { now ->
        val from = now.minusHours(OverviewHours)
        combine(
            glucoseRepository.observeRange(from = from, to = now),
            historyRepository.observeMeals(from = from, to = now),
            contextRepository.observeInsulin(from = from, to = now),
        ) { glucose, meals, insulin -> DayData(from, now, glucose, meals.value.orEmpty(), insulin) }
    }

    val state = combine(
        dayData,
        focus,
        server,
        sensorRepository.observeSensors(),
    ) { data, currentFocus, context, sensors ->
        buildState(data, currentFocus, context, sensors.value.orEmpty())
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = GlucoseScreenState.empty(anchor.value),
    )

    fun selectFocusWindow(window: FocusWindow) {
        focus.update { it.copy(window = window) }
    }

    /** Move the focus window so it ends at [end]; at or past now it follows live again. */
    fun moveFocusTo(end: Instant) {
        val now = anchor.value
        focus.update { current ->
            val earliest = now.minusHours(OverviewHours - current.window.hours)
            val clamped = when {
                end >= now.minusMinutes(LiveSnapMinutes) -> null
                end < earliest -> earliest
                else -> end
            }
            current.copy(end = clamped)
        }
    }

    fun followLive() {
        focus.update { it.copy(end = null) }
    }

    fun refresh() {
        val now = Clock.System.now()
        anchor.value = now
        val from = now.minusHours(OverviewHours)
        viewModelScope.launch { runCatching { sensorRepository.refreshSensors() } }
        viewModelScope.launch { contextRepository.refreshInsulin(from = from, to = now) }
        viewModelScope.launch {
            runCatching { contextRepository.bodySpans(from = from, to = now) }
                .onSuccess { spans -> server.update { it.copy(bodySpans = spans) } }
        }
        viewModelScope.launch {
            runCatching { contextRepository.episodes(from = from, to = now) }
                .onSuccess { episodes -> server.update { it.copy(episodes = episodes) } }
        }
        viewModelScope.launch {
            runCatching { contextRepository.activeContext(now) }
                .onSuccess { active -> server.update { it.copy(active = active) } }
        }
        viewModelScope.launch {
            runCatching { contextRepository.tirForDay(now.localDate()) }
                .onSuccess { tir -> server.update { it.copy(tirToday = tir) } }
        }
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

/** Within this many minutes of now, a scrolled window snaps back to live. */
private const val LiveSnapMinutes = 5

private fun buildState(
    data: DayData,
    focus: Focus,
    context: ServerContext,
    sensors: List<SensorSession>,
): GlucoseScreenState {
    val readings = data.glucose.value?.readings.orEmpty()
    val latest = readings.lastOrNull()
    val meals = data.meals.toMealMarkers(data.from, data.now)
    val (carbMarks, insulinMarks) = buildMarks(meals, data.insulin, context.episodes)
    val ageMinutes = latest?.readingAt?.minutesUntil(Clock.System.now())
    val stale = ageMinutes != null && ageMinutes > StaleAfterMinutes
    return GlucoseScreenState(
        dayFrom = data.from,
        now = data.now,
        focusWindow = focus.window,
        focusEnd = focus.end ?: data.now,
        isLive = focus.end == null,
        readings = readings,
        latest = latest,
        latestAgeMinutes = ageMinutes,
        delta15Mmol = if (stale) null else latest?.delta15(readings),
        meals = meals,
        insulin = data.insulin,
        bodySpans = context.bodySpans.filter { it.endAt > data.from && it.startAt < data.now },
        carbMarks = carbMarks.filter { it.at >= data.from && it.at <= data.now },
        insulinMarks = insulinMarks.filter { it.at >= data.from && it.at <= data.now },
        active = context.active,
        tirToday = context.tirToday?.takeIf { it.date == data.now.localDate() },
        activeSensor = sensors.filter { it.endedAt == null }.maxByOrNull { it.startedAt },
    )
}

/**
 * One carbs mark and one insulin mark per sitting the server grouped, with
 * the server's totals — never summed here. A meal or dose the server has not
 * grouped yet (just added, or offline) keeps a mark of its own.
 */
internal fun buildMarks(
    meals: List<GlucoseMealMarker>,
    insulin: List<InsulinEvent>,
    episodes: List<GlucoseEpisodeMark>,
): Pair<List<CarbMark>, List<InsulinMark>> {
    val mealsById = meals.associateBy { it.id }
    val groupedMeals = episodes.flatMapTo(mutableSetOf()) { it.mealIds }
    val groupedInsulin = episodes.flatMapTo(mutableSetOf()) { it.insulinIds }

    val carbs = episodes
        .filter { it.mealIds.isNotEmpty() && it.totalCarbsG > 0.0 }
        .map { episode ->
            val firstMeal = episode.mealIds.mapNotNull { mealsById[it]?.at }.minOrNull()
            CarbMark(at = firstMeal ?: episode.startAt, grams = episode.totalCarbsG)
        } + meals.filter { it.id !in groupedMeals }.map { CarbMark(at = it.at, grams = it.carbsG) }

    val doses = episodes
        .filter { it.totalInsulinUnits > 0.0 && it.firstInsulinAt != null }
        .map { episode ->
            InsulinMark(
                at = episode.firstInsulinAt!!,
                units = episode.totalInsulinUnits,
                tint = if (episode.correctionOnly) InsulinTint.Correction else InsulinTint.Food,
            )
        } + insulin.filter { it.id !in groupedInsulin }.map { event ->
            InsulinMark(
                at = event.timestamp,
                units = event.doseUnits,
                tint = when (event.eventType) {
                    InsulinEventType.Correction, InsulinEventType.CatchUp -> InsulinTint.Correction
                    InsulinEventType.Basal -> InsulinTint.Basal
                    else -> InsulinTint.Food
                },
                pending = event.isPending,
            )
        }
    return carbs.sortedBy { it.at } to doses.sortedBy { it.at }
}

/** Accepted meals only: a draft has no confirmed carbs to draw. */
internal fun List<Meal>.toMealMarkers(from: Instant, to: Instant): List<GlucoseMealMarker> =
    filter { it.status.equals("accepted", ignoreCase = true) && it.eatenAt >= from && it.eatenAt <= to }
        .sortedBy { it.eatenAt }
        .map { GlucoseMealMarker(id = it.id, at = it.eatenAt, title = it.title, carbsG = it.totalCarbsG) }

/** Display-only change over 15 minutes; no stored value is altered. */
internal fun GlucoseReading.delta15(readings: List<GlucoseReading>): Double? {
    val target = readingAt.toEpochMilliseconds() - 15 * 60 * 1_000L
    val baseline = readings.lastOrNull { reading -> reading.readingAt.toEpochMilliseconds() <= target }
    return baseline?.let { displayValueMmolL - it.displayValueMmolL }
}

internal fun Instant.minusHours(hours: Int): Instant =
    Instant.fromEpochMilliseconds(toEpochMilliseconds() - hours * 60L * 60L * 1_000L)

internal fun Instant.minusMinutes(minutes: Int): Instant =
    Instant.fromEpochMilliseconds(toEpochMilliseconds() - minutes * 60L * 1_000L)

private fun Instant.minutesUntil(other: Instant): Int =
    ((other.toEpochMilliseconds() - toEpochMilliseconds()) / 60_000L)
        .coerceAtLeast(0L)
        .toInt()

private fun Instant.localDate(): LocalDate = toLocalDateTime(TimeZone.currentSystemDefault()).date
