package com.local.glucotracker.ui.feature.glucose

import app.cash.turbine.test
import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.CreateFingerstickOutboxKind
import com.local.glucotracker.domain.model.FingerstickReading
import com.local.glucotracker.domain.model.GlucoseRange
import com.local.glucotracker.domain.model.GlucoseReading
import com.local.glucotracker.domain.model.HistoryPage
import com.local.glucotracker.domain.model.HistoryQuery
import com.local.glucotracker.domain.model.Meal
import com.local.glucotracker.domain.model.MealDraft
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.domain.model.SensorCode
import com.local.glucotracker.domain.model.SensorQuality
import com.local.glucotracker.domain.model.SensorSession
import com.local.glucotracker.domain.model.Source
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
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
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
    fun refreshesGlucoseForWindowsAndMarksDayGap() = runTest {
        val now = Clock.System.now()
        val readings = (24 downTo 0).map { step ->
            reading(
                at = Instant.fromEpochMilliseconds(now.toEpochMilliseconds() - step * 15L * 60_000L),
                value = 6.0 + (step % 3) * 0.2,
            )
        }
        val glucoseRepository = FakeGlucoseRepository(readings)
        val viewModel = GlucoseViewModel(
            glucoseRepository = glucoseRepository,
            historyRepository = FakeHistoryRepository(),
            outboxRepository = FakeOutboxRepository(),
            sensorRepository = FakeSensorRepository(),
        )

        viewModel.state.test {
            var loaded = awaitItem()
            while (loaded.windows.all { it.readings.isEmpty() }) {
                loaded = awaitItem()
            }

            assertEquals(4, glucoseRepository.networkCalls)
            assertEquals(0, glucoseRepository.cachedCalls)
            assertEquals(GlucoseWindow.ThreeHours, loaded.selectedWindow)
            assertFalse(loaded.windows.first { it.window == GlucoseWindow.ThreeHours }.hasGap)
            assertFalse(loaded.windows.first { it.window == GlucoseWindow.SixHours }.hasGap)
            assertTrue(loaded.windows.first { it.window == GlucoseWindow.Day }.hasGap)
            assertTrue(loaded.windows.first { it.window == GlucoseWindow.Week }.hasGap)
            val daySegments = loaded.windows.first { it.window == GlucoseWindow.Day }.tirSegments
            assertEquals(
                100,
                daySegments.first { it.bucket == GlucoseTirBucket.InRange }.percent,
            )
            assertTrue(
                daySegments
                    .filter { it.bucket != GlucoseTirBucket.InRange }
                    .all { it.percent == 0 },
            )
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun computesFiveTirBucketsFromReadings() = runTest {
        val now = Clock.System.now()
        val values = listOf(2.5, 3.5, 6.0, 11.0, 14.0)
        val readings = values.mapIndexed { index, value ->
            reading(
                at = Instant.fromEpochMilliseconds(now.toEpochMilliseconds() - index * 5L * 60_000L),
                value = value,
            )
        }
        val viewModel = GlucoseViewModel(
            glucoseRepository = FakeGlucoseRepository(readings),
            historyRepository = FakeHistoryRepository(),
            outboxRepository = FakeOutboxRepository(),
            sensorRepository = FakeSensorRepository(),
        )

        viewModel.state.test {
            var loaded = awaitItem()
            while (loaded.windows.all { it.readings.isEmpty() }) {
                loaded = awaitItem()
            }

            val segments = loaded.windows.first { it.window == GlucoseWindow.ThreeHours }.tirSegments
            assertEquals(
                GlucoseTirBucket.entries.toList(),
                segments.map { it.bucket },
            )
            assertTrue(segments.all { it.percent == 20 })
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun fingerstickEntryIsQueuedInOutbox() = runTest {
        val outboxRepository = FakeOutboxRepository()
        val viewModel = GlucoseViewModel(
            glucoseRepository = FakeGlucoseRepository(emptyList()),
            historyRepository = FakeHistoryRepository(),
            outboxRepository = outboxRepository,
            sensorRepository = FakeSensorRepository(),
        )

        viewModel.enqueueFingerstick(5.8)
        advanceUntilIdle()

        val kind = outboxRepository.items.single().kind as CreateFingerstickOutboxKind
        assertEquals(5.8, kind.glucoseMmolL, 0.0)
    }

    @Test
    fun exposesNewestActiveSensorAndRefreshesIt() = runTest {
        val older = sensor(
            id = "older",
            startedAt = Instant.parse("2026-07-20T10:00:00Z"),
        )
        val active = sensor(
            id = "active",
            startedAt = Instant.parse("2026-07-29T16:10:00Z"),
        )
        val finished = sensor(
            id = "finished",
            startedAt = Instant.parse("2026-07-29T17:00:00Z"),
            endedAt = Instant.parse("2026-07-29T18:00:00Z"),
        )
        val sensors = FakeSensorRepository(listOf(older, active, finished))
        val viewModel = GlucoseViewModel(
            glucoseRepository = FakeGlucoseRepository(emptyList()),
            historyRepository = FakeHistoryRepository(),
            outboxRepository = FakeOutboxRepository(),
            sensorRepository = sensors,
        )

        viewModel.state.test {
            var loaded = awaitItem()
            while (loaded.activeSensor == null) {
                loaded = awaitItem()
            }
            assertEquals("active", loaded.activeSensor?.id)

            viewModel.refresh()
            advanceUntilIdle()
            assertEquals(1, sensors.refreshCalls)
            cancelAndIgnoreRemainingEvents()
        }
    }
}

private class FakeGlucoseRepository(
    private val readings: List<GlucoseReading>,
) : GlucoseRepository {
    var networkCalls = 0
    var cachedCalls = 0

    override fun observeRange(from: Instant, to: Instant): Flow<CachedView<GlucoseRange>> {
        networkCalls += 1
        return flowOf(view(from = from, to = to, source = Source.Network))
    }

    override fun observeCachedRange(from: Instant, to: Instant): Flow<CachedView<GlucoseRange>> {
        cachedCalls += 1
        return flowOf(view(from = from, to = to, source = Source.Cache))
    }

    private fun view(from: Instant, to: Instant, source: Source): CachedView<GlucoseRange> {
        val visible = readings.filter { reading ->
            reading.readingAt.toEpochMilliseconds() >= from.toEpochMilliseconds() &&
                reading.readingAt.toEpochMilliseconds() <= to.toEpochMilliseconds()
        }
        return CachedView(
            value = GlucoseRange(
                from = from,
                to = to,
                readings = visible,
            ),
            fetchedAt = visible.maxOfOrNull { it.readingAt },
            isRefreshing = false,
            source = if (visible.isEmpty()) Source.Empty else source,
        )
    }
}

private class FakeHistoryRepository : HistoryRepository {
    override fun observeMeals(from: Instant, to: Instant): Flow<CachedView<List<Meal>>> =
        error("Glucose screen should not refresh meals while rendering cached windows.")

    override fun observeCachedMeals(from: Instant, to: Instant): Flow<List<Meal>> =
        flowOf(emptyList())

    override fun observeHistory(query: HistoryQuery): Flow<CachedView<HistoryPage>> =
        error("Glucose screen should not observe history.")
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
    private val cached = flowOf(
        CachedView(
            value = sensors,
            fetchedAt = Clock.System.now(),
            isRefreshing = false,
            source = Source.Cache,
        ),
    )
    var refreshCalls = 0

    override fun observeSensors(): Flow<CachedView<List<SensorSession>>> = cached

    override fun observeSensorCodes(): Flow<CachedView<List<SensorCode>>> =
        flowOf(CachedView<List<SensorCode>>(null, null, false, Source.Empty))

    override fun observeFingersticks(
        from: Instant,
        to: Instant,
    ): Flow<CachedView<List<FingerstickReading>>> =
        flowOf(CachedView<List<FingerstickReading>>(null, null, false, Source.Empty))

    override suspend fun refreshSensors() {
        refreshCalls += 1
    }

    override suspend fun refreshSensorCodes() = Unit

    override suspend fun refreshFingersticks(from: Instant, to: Instant) = Unit

    override suspend fun sensorQuality(sensorId: String): SensorQuality =
        error("Glucose screen should not load sensor quality.")
}

private fun reading(at: Instant, value: Double): GlucoseReading =
    GlucoseReading(
        readingAt = at,
        rawValueMmolL = value,
        displayValueMmolL = value,
        normalizedValueMmolL = null,
        smoothedValueMmolL = null,
        flags = emptyList(),
    )

private fun sensor(
    id: String,
    startedAt: Instant,
    endedAt: Instant? = null,
): SensorSession =
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
