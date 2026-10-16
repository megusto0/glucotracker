package com.local.glucotracker.ui.feature.glucose

import app.cash.turbine.test
import com.local.glucotracker.domain.model.ActiveGlucoseContext
import com.local.glucotracker.domain.model.BodySpan
import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.CreateFingerstickOutboxKind
import com.local.glucotracker.domain.model.FingerstickReading
import com.local.glucotracker.domain.model.GlucoseEpisodeMark
import com.local.glucotracker.domain.model.GlucoseRange
import com.local.glucotracker.domain.model.GlucoseReading
import com.local.glucotracker.domain.model.GlucoseTirDay
import com.local.glucotracker.domain.model.HistoryPage
import com.local.glucotracker.domain.model.HistoryQuery
import com.local.glucotracker.domain.model.InsulinEvent
import com.local.glucotracker.domain.model.Meal
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.domain.model.SensorCode
import com.local.glucotracker.domain.model.SensorQuality
import com.local.glucotracker.domain.model.SensorSession
import com.local.glucotracker.domain.model.Source
import com.local.glucotracker.domain.repository.GlucoseContextRepository
import com.local.glucotracker.domain.repository.GlucoseRepository
import com.local.glucotracker.domain.repository.HistoryRepository
import com.local.glucotracker.domain.repository.OutboxRepository
import com.local.glucotracker.domain.repository.SensorRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class GlucoseViewModelTest {
    private val dispatcher = UnconfinedTestDispatcher()

    @Before
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun opensLiveOnThreeHoursOverAWholeDayOfData() = runTest {
        val now = Clock.System.now()
        val readings = (287 downTo 0).map { step -> reading(now.minusMinutes(step * 5), 6.0) }
        val viewModel = viewModel(glucose = FakeGlucoseRepository(readings))

        viewModel.state.test {
            val loaded = awaitUntil { it.readings.isNotEmpty() }
            assertEquals(FocusWindow.ThreeHours, loaded.focusWindow)
            assertTrue(loaded.isLive)
            assertEquals(288, loaded.readings.size)
            assertEquals(3L * 60L, (loaded.focusEnd - loaded.focusFrom).inWholeMinutes)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun deltaIsTheChangeOverFifteenMinutes() = runTest {
        val now = Clock.System.now()
        val readings = listOf(
            reading(now.minusMinutes(20), 8.0),
            reading(now.minusMinutes(15), 7.6),
            reading(now.minusMinutes(5), 7.2),
            reading(now, 7.0),
        )
        val viewModel = viewModel(glucose = FakeGlucoseRepository(readings))

        viewModel.state.test {
            val loaded = awaitUntil { it.readings.isNotEmpty() }
            assertEquals(-0.6, loaded.delta15Mmol!!, 1e-9)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun tirIobAndCobComeFromTheServerNotTheReadings() = runTest {
        val now = Clock.System.now()
        // Every reading is low; a client-side TIR would say 0 % in range.
        val readings = (12 downTo 0).map { step -> reading(now.minusMinutes(step * 5), 3.2) }
        val context = FakeContextRepository(
            tir = GlucoseTirDay(now.localDate(), 0.0, 3.0, 92.0, 5.0, 0.0),
            active = ActiveGlucoseContext(iobUnits = 1.8, iobMinutesRemaining = 130, cobGrams = 24.0, cobMinutesRemaining = 90),
        )
        val viewModel = viewModel(glucose = FakeGlucoseRepository(readings), context = context)

        viewModel.refresh()
        advanceUntilIdle()
        viewModel.state.test {
            val loaded = awaitUntil { it.tirToday != null && it.active != null }
            assertEquals(92.0, loaded.tirToday!!.inRangePercent!!, 0.0)
            assertEquals(1.8, loaded.active!!.iobUnits, 0.0)
            assertEquals(24.0, loaded.active!!.cobGrams, 0.0)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun chartShowsAcceptedMealsOnlyWithServerCarbs() = runTest {
        val now = Clock.System.now()
        val breakfast = meal("breakfast", now.minusMinutes(300), carbs = 45.0)
        val draft = meal("draft", now.minusMinutes(200), carbs = 30.0, status = "draft")
        val lunch = meal("lunch", now.minusMinutes(60), carbs = 60.0)
        val viewModel = viewModel(history = FakeHistoryRepository(listOf(breakfast, draft, lunch)))

        viewModel.state.test {
            val loaded = awaitUntil { it.meals.isNotEmpty() }
            assertEquals(listOf("breakfast", "lunch"), loaded.meals.map { it.id })
            assertEquals(listOf(45.0, 60.0), loaded.meals.map { it.carbsG })
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun movingTheFocusStaysInsideTheDayAndSnapsBackToLive() = runTest {
        val viewModel = viewModel()
        viewModel.state.test {
            val now = awaitItem().now
            viewModel.selectFocusWindow(FocusWindow.SixHours)

            viewModel.moveFocusTo(now.minusMinutes(30 * 60))
            var current = awaitUntil { !it.isLive }
            assertEquals(now.minusMinutes(18 * 60), current.focusEnd)

            viewModel.moveFocusTo(now.minusMinutes(8 * 60))
            current = awaitUntil { it.focusEnd == now.minusMinutes(8 * 60) }
            assertFalse(current.isLive)

            viewModel.moveFocusTo(now.minusMinutes(2))
            assertTrue(awaitUntil { it.isLive }.isLive)

            viewModel.moveFocusTo(now.minusMinutes(8 * 60))
            awaitUntil { !it.isLive }
            viewModel.followLive()
            assertTrue(awaitUntil { it.isLive }.isLive)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun bodySpansOutsideTheDayAreDropped() = runTest {
        val now = Clock.System.now()
        val old = span(BodySpan.Kind.Sleep, now.minusMinutes(40 * 60), now.minusMinutes(30 * 60))
        val ride = span(BodySpan.Kind.Activity, now.minusMinutes(90), now.minusMinutes(30), label = "Велосипед")
        val viewModel = viewModel(context = FakeContextRepository(spans = listOf(old, ride)))

        viewModel.refresh()
        advanceUntilIdle()
        viewModel.state.test {
            val loaded = awaitUntil { it.bodySpans.isNotEmpty() }
            assertEquals(listOf("Велосипед"), loaded.bodySpans.map { it.label })
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun refreshAsksForADayOfInsulin() = runTest {
        val context = FakeContextRepository()
        val viewModel = viewModel(context = context)

        viewModel.refresh()
        advanceUntilIdle()

        val (from, to) = context.insulinRefreshes.single()
        assertEquals(24L * 60L, (to.toEpochMilliseconds() - from.toEpochMilliseconds()) / 60_000L)
    }

    @Test
    fun withoutNetworkServerContextIsAbsentNotGuessed() = runTest {
        val now = Clock.System.now()
        val viewModel = viewModel(
            glucose = FakeGlucoseRepository(listOf(reading(now, 6.5))),
            context = FakeContextRepository(offline = true),
        )

        viewModel.refresh()
        advanceUntilIdle()
        viewModel.state.test {
            val loaded = awaitUntil { it.readings.isNotEmpty() }
            assertNull(loaded.tirToday)
            assertNull(loaded.active)
            assertTrue(loaded.bodySpans.isEmpty())
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun fingerstickEntryIsQueuedInOutbox() = runTest {
        val outbox = FakeOutboxRepository()
        val viewModel = viewModel(outbox = outbox)

        viewModel.enqueueFingerstick(5.8)
        advanceUntilIdle()

        val kind = outbox.items.single().kind as CreateFingerstickOutboxKind
        assertEquals(5.8, kind.glucoseMmolL, 0.0)
    }

    @Test
    fun exposesNewestActiveSensorAndRefreshesIt() = runTest {
        val older = sensor("older", Instant.parse("2026-07-20T10:00:00Z"))
        val active = sensor("active", Instant.parse("2026-07-29T16:10:00Z"))
        val finished = sensor(
            "finished",
            Instant.parse("2026-07-29T17:00:00Z"),
            endedAt = Instant.parse("2026-07-29T18:00:00Z"),
        )
        val sensors = FakeSensorRepository(listOf(older, active, finished))
        val viewModel = viewModel(sensors = sensors)

        viewModel.state.test {
            val loaded = awaitUntil { it.activeSensor != null }
            assertEquals("active", loaded.activeSensor?.id)
            viewModel.refresh()
            advanceUntilIdle()
            assertEquals(1, sensors.refreshCalls)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun aSittingIsOneCarbsAndOneInsulinMarkWithServerTotals() = runTest {
        val now = Clock.System.now()
        val first = meal("basket-1", now.minusMinutes(60), carbs = 28.6)
        val second = meal("basket-2", now.minusMinutes(58), carbs = 28.6)
        val snack = meal("snack", now.minusMinutes(20), carbs = 12.0)
        val sitting = GlucoseEpisodeMark(
            key = "e1",
            startAt = now.minusMinutes(61),
            mealIds = setOf("basket-1", "basket-2"),
            insulinIds = setOf("dose-1", "dose-2"),
            // The server's totals; deliberately not the sum of the parts.
            totalCarbsG = 57.0,
            totalInsulinUnits = 6.5,
            firstInsulinAt = now.minusMinutes(65),
            correctionOnly = false,
        )
        val viewModel = viewModel(
            history = FakeHistoryRepository(listOf(first, second, snack)),
            context = FakeContextRepository(episodes = listOf(sitting)),
        )

        viewModel.refresh()
        advanceUntilIdle()
        viewModel.state.test {
            val loaded = awaitUntil { it.insulinMarks.isNotEmpty() }
            assertEquals(listOf(57.0, 12.0), loaded.carbMarks.map { it.grams })
            assertEquals(first.eatenAt, loaded.carbMarks.first().at)
            assertEquals(listOf(6.5), loaded.insulinMarks.map { it.units })
            assertEquals(InsulinTint.Food, loaded.insulinMarks.single().tint)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun neighbouringMarkersArePushedApartAndKeptInside() {
        val placed = spreadMarkers(listOf(100f, 105f, 300f, 395f, 398f), minGap = 22f, left = 0f, right = 400f)
        assertEquals(100f, placed[0], 0.01f)
        assertEquals(122f, placed[1], 0.01f)
        assertEquals(300f, placed[2], 0.01f)
        assertEquals(367f, placed[3], 0.01f)
        assertEquals(389f, placed[4], 0.01f)
        placed.sorted().zipWithNext().forEach { (a, b) -> assertTrue(b - a >= 22f - 0.01f) }
    }

    private fun viewModel(
        glucose: GlucoseRepository = FakeGlucoseRepository(emptyList()),
        history: HistoryRepository = FakeHistoryRepository(),
        context: GlucoseContextRepository = FakeContextRepository(),
        outbox: OutboxRepository = FakeOutboxRepository(),
        sensors: SensorRepository = FakeSensorRepository(),
    ) = GlucoseViewModel(
        glucoseRepository = glucose,
        historyRepository = history,
        contextRepository = context,
        outboxRepository = outbox,
        sensorRepository = sensors,
    )
}

private suspend fun app.cash.turbine.ReceiveTurbine<GlucoseScreenState>.awaitUntil(
    predicate: (GlucoseScreenState) -> Boolean,
): GlucoseScreenState {
    var item = awaitItem()
    while (!predicate(item)) item = awaitItem()
    return item
}

private class FakeGlucoseRepository(
    private val readings: List<GlucoseReading>,
) : GlucoseRepository {
    override fun observeRange(from: Instant, to: Instant): Flow<CachedView<GlucoseRange>> =
        flowOf(view(from, to))

    override fun observeCachedRange(from: Instant, to: Instant): Flow<CachedView<GlucoseRange>> =
        flowOf(view(from, to))

    private fun view(from: Instant, to: Instant): CachedView<GlucoseRange> {
        val visible = readings.filter { it.readingAt >= from && it.readingAt <= to }
        return CachedView(
            value = GlucoseRange(from = from, to = to, readings = visible),
            fetchedAt = visible.maxOfOrNull { it.readingAt },
            isRefreshing = false,
            source = if (visible.isEmpty()) Source.Empty else Source.Network,
        )
    }
}

private class FakeHistoryRepository(
    private val meals: List<Meal> = emptyList(),
) : HistoryRepository {
    override fun observeMeals(from: Instant, to: Instant): Flow<CachedView<List<Meal>>> =
        flowOf(CachedView(meals, Clock.System.now(), false, Source.Network))

    override fun observeCachedMeals(from: Instant, to: Instant): Flow<List<Meal>> = flowOf(meals)

    override fun observeHistory(query: HistoryQuery): Flow<CachedView<HistoryPage>> =
        error("Glucose screen should not observe history.")
}

private class FakeContextRepository(
    private val insulin: List<InsulinEvent> = emptyList(),
    private val spans: List<BodySpan> = emptyList(),
    private val active: ActiveGlucoseContext? = null,
    private val tir: GlucoseTirDay? = null,
    private val episodes: List<GlucoseEpisodeMark> = emptyList(),
    private val offline: Boolean = false,
) : GlucoseContextRepository {
    val insulinRefreshes = mutableListOf<Pair<Instant, Instant>>()

    override fun observeInsulin(from: Instant, to: Instant): Flow<List<InsulinEvent>> =
        flowOf(insulin.filter { it.timestamp >= from && it.timestamp <= to })

    override suspend fun refreshInsulin(from: Instant, to: Instant) {
        insulinRefreshes += from to to
    }

    override suspend fun bodySpans(from: Instant, to: Instant): List<BodySpan> =
        if (offline) error("offline") else spans

    override suspend fun episodes(from: Instant, to: Instant): List<GlucoseEpisodeMark> =
        if (offline) error("offline") else episodes

    override suspend fun activeContext(now: Instant): ActiveGlucoseContext? =
        if (offline) error("offline") else active

    override suspend fun tirForDay(date: LocalDate): GlucoseTirDay? =
        if (offline) error("offline") else tir
}

private class FakeOutboxRepository : OutboxRepository {
    val items: MutableList<OutboxItem> = mutableListOf()

    override fun observe(): Flow<List<OutboxItem>> = flowOf(items)

    override fun observeActiveCount(): Flow<Int> = flowOf(0)

    override suspend fun enqueue(kind: OutboxKind): OutboxItem {
        val item = OutboxItem(
            id = "outbox-${items.size + 1}",
            kind = kind,
            state = OutboxState.Queued,
            createdAt = Clock.System.now(),
            lastAttemptAt = null,
            nextAttemptAt = null,
            attempts = 0,
            serverIdOnSuccess = null,
            errorMessage = null,
            enteredCurrentStateAt = Clock.System.now(),
        )
        items += item
        return item
    }

    override suspend fun enqueue(item: OutboxItem) {
        items += item
    }

    override suspend fun remove(id: String) {
        items.removeAll { it.id == id }
    }

    override suspend fun markUploading(id: String) = Unit
    override suspend fun markPhotoEstimating(id: String, serverMealId: String) = Unit
    override suspend fun markConfirmed(id: String, serverIdOnSuccess: String?) = Unit
    override suspend fun markStuck(id: String, errorCode: String, errorMessage: String?) = Unit
    override suspend fun requeue(id: String, nextAttemptAt: Instant?, errorCode: String?, errorMessage: String?) = Unit
    override suspend fun retry(id: String) = Unit
    override suspend fun revertNetworkStuckItems(): Int = 0

    override suspend fun forgetMeal(serverId: String) = Unit
}

private class FakeSensorRepository(
    sensors: List<SensorSession> = emptyList(),
) : SensorRepository {
    private val cached = flowOf(CachedView(sensors, Clock.System.now(), false, Source.Cache))
    var refreshCalls = 0

    override fun observeSensors(): Flow<CachedView<List<SensorSession>>> = cached

    override fun observeSensorCodes(): Flow<CachedView<List<SensorCode>>> =
        flowOf(CachedView<List<SensorCode>>(null, null, false, Source.Empty))

    override fun observeFingersticks(from: Instant, to: Instant): Flow<CachedView<List<FingerstickReading>>> =
        flowOf(CachedView<List<FingerstickReading>>(null, null, false, Source.Empty))

    override suspend fun refreshSensors() {
        refreshCalls += 1
    }

    override suspend fun refreshSensorCodes() = Unit

    override suspend fun refreshFingersticks(from: Instant, to: Instant) = Unit

    override suspend fun sensorQuality(sensorId: String): SensorQuality =
        error("Glucose screen should not load sensor quality.")
}

private fun Instant.localDate(): LocalDate = toLocalDateTime(TimeZone.currentSystemDefault()).date

private fun reading(at: Instant, value: Double): GlucoseReading =
    GlucoseReading(
        readingAt = at,
        rawValueMmolL = value,
        displayValueMmolL = value,
        normalizedValueMmolL = null,
        smoothedValueMmolL = null,
        flags = emptyList(),
    )

private fun meal(id: String, at: Instant, carbs: Double, status: String = "accepted"): Meal =
    Meal(
        id = id,
        eatenAt = at,
        eatenAtDay = at.localDate(),
        title = id,
        status = status,
        source = "manual",
        note = null,
        thumbnailUrl = null,
        totalKcal = carbs * 4,
        totalCarbsG = carbs,
        totalProteinG = 0.0,
        totalFatG = 0.0,
        totalFiberG = 0.0,
        updatedAt = at,
    )

private fun span(kind: BodySpan.Kind, start: Instant, end: Instant, label: String? = null): BodySpan =
    BodySpan(
        kind = kind,
        startAt = start,
        endAt = end,
        totalMinutes = ((end.toEpochMilliseconds() - start.toEpochMilliseconds()) / 60_000L).toInt(),
        label = label,
        inferred = false,
        meanBpm = null,
    )

private fun sensor(id: String, startedAt: Instant, endedAt: Instant? = null): SensorSession =
    SensorSession(
        id = id,
        startedAt = startedAt,
        endedAt = endedAt,
        expectedLifeDays = 15.0,
        label = "Сенсор · $id",
        vendor = null,
        model = null,
        excludedFromAnalytics = false,
        exclusionReason = null,
    )
