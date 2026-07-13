package com.local.glucotracker.ui.feature.sensor

import app.cash.turbine.test
import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.CreateFingerstickOutboxKind
import com.local.glucotracker.domain.model.CreateSensorOutboxKind
import com.local.glucotracker.domain.model.FingerstickReading
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.domain.model.PatchSensorOutboxKind
import com.local.glucotracker.domain.model.SensorPhase
import com.local.glucotracker.domain.model.SensorQuality
import com.local.glucotracker.domain.model.SensorQualityConfidence
import com.local.glucotracker.domain.model.SensorSession
import com.local.glucotracker.domain.model.Source
import com.local.glucotracker.domain.repository.OutboxRepository
import com.local.glucotracker.domain.repository.SensorRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
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
class SensorManagementViewModelTest {
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
    fun loadsActiveSensorAndBackendQuality() = runTest {
        val sensor = sensor(id = "00000000-0000-0000-0000-000000000001")
        val repository = FakeSensorRepository(listOf(sensor))
        val viewModel = SensorManagementViewModel(repository, FakeSensorOutboxRepository())

        viewModel.state.test {
            var loaded = awaitItem()
            while (loaded.quality == null) loaded = awaitItem()

            assertEquals(sensor.id, loaded.selectedSensorId)
            assertEquals(84, loaded.quality?.qualityScore)
            assertFalse(loaded.loadFailed)
            assertTrue(repository.refreshCalls > 0)
            assertEquals(listOf(sensor.id), repository.qualityCalls)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun queuesFingerstickStartFinishAndExclusion() = runTest {
        val sensor = sensor(id = "00000000-0000-0000-0000-000000000002")
        val outbox = FakeSensorOutboxRepository()
        val viewModel = SensorManagementViewModel(FakeSensorRepository(listOf(sensor)), outbox)

        viewModel.enqueueFingerstick(5.8)
        viewModel.startSensor("Ottai #5", "Ottai", "One", 15.0)
        viewModel.finishSensor(sensor.id)
        viewModel.setExcluded(sensor.id, true, "Исключено пользователем")
        advanceUntilIdle()

        assertEquals(4, outbox.items.value.size)
        assertEquals(5.8, (outbox.items.value[0].kind as CreateFingerstickOutboxKind).glucoseMmolL, 0.0)
        assertEquals("Ottai #5", (outbox.items.value[1].kind as CreateSensorOutboxKind).label)
        assertTrue((outbox.items.value[2].kind as PatchSensorOutboxKind).endedAt != null)
        assertEquals(true, (outbox.items.value[3].kind as PatchSensorOutboxKind).excludedFromAnalytics)
    }

    @Test
    fun mergesAcceptedAndPendingFingerstickHistoryNewestFirst() = runTest {
        val now = Clock.System.now()
        val accepted = FingerstickReading(
            id = "accepted",
            measuredAt = Instant.fromEpochMilliseconds(now.toEpochMilliseconds() - 60_000L),
            glucoseMmolL = 5.4,
            meterName = "Contour",
            notes = null,
            createdAt = now,
        )
        val repository = FakeSensorRepository(emptyList(), listOf(accepted))
        val outbox = FakeSensorOutboxRepository()
        val viewModel = SensorManagementViewModel(repository, outbox)

        viewModel.state.test {
            awaitItem()
            viewModel.enqueueFingerstick(6.2)
            var updated = awaitItem()
            while (updated.fingersticks.size < 2) updated = awaitItem()

            assertEquals(listOf(6.2, 5.4), updated.fingersticks.map { it.glucoseMmolL })
            assertEquals(OutboxState.Queued, updated.fingersticks.first().syncState)
            assertEquals(null, updated.fingersticks.last().syncState)
            cancelAndIgnoreRemainingEvents()
        }
    }
}

private class FakeSensorRepository(
    sensors: List<SensorSession>,
    fingersticks: List<FingerstickReading> = emptyList(),
) : SensorRepository {
    private val cached = MutableStateFlow(
        CachedView(
            value = sensors,
            fetchedAt = Clock.System.now(),
            isRefreshing = false,
            source = Source.Cache,
        ),
    )
    private val cachedFingersticks = MutableStateFlow(
        CachedView(
            value = fingersticks,
            fetchedAt = Clock.System.now(),
            isRefreshing = false,
            source = Source.Cache,
        ),
    )
    var refreshCalls = 0
    var fingerstickRefreshCalls = 0
    val qualityCalls = mutableListOf<String>()

    override fun observeSensors(): Flow<CachedView<List<SensorSession>>> = cached

    override fun observeFingersticks(
        from: Instant,
        to: Instant,
    ): Flow<CachedView<List<FingerstickReading>>> = cachedFingersticks

    override suspend fun refreshSensors() {
        refreshCalls += 1
        cached.value = cached.value.copy(source = Source.Network)
    }

    override suspend fun refreshFingersticks(from: Instant, to: Instant) {
        fingerstickRefreshCalls += 1
        cachedFingersticks.value = cachedFingersticks.value.copy(source = Source.Network)
    }

    override suspend fun sensorQuality(sensorId: String): SensorQuality {
        qualityCalls += sensorId
        return SensorQuality(
            qualityScore = 84,
            confidence = SensorQualityConfidence.High,
            sensorAgeDays = 4.0,
            sensorPhase = SensorPhase.Stable,
            fingerstickCount = 5,
            validCalibrationPoints = 4,
            missingDataPercent = 2.0,
            noiseScore = 0.1,
            mardPercent = 8.0,
            suspectedCompressionCount = 0,
        )
    }
}

private class FakeSensorOutboxRepository : OutboxRepository {
    val items = MutableStateFlow<List<OutboxItem>>(emptyList())

    override fun observe(): Flow<List<OutboxItem>> = items
    override fun observeActiveCount(): Flow<Int> = MutableStateFlow(0)

    override suspend fun enqueue(kind: OutboxKind): OutboxItem {
        val item = OutboxItem(
            id = "outbox-${items.value.size + 1}",
            kind = kind,
            state = OutboxState.Queued,
            createdAt = Clock.System.now(),
            lastAttemptAt = null,
            attempts = 0,
            serverIdOnSuccess = null,
            errorMessage = null,
        )
        items.value = items.value + item
        return item
    }

    override suspend fun enqueue(item: OutboxItem) {
        items.value = items.value + item
    }

    override suspend fun remove(id: String) {
        items.value = items.value.filterNot { it.id == id }
    }

    override suspend fun markUploading(id: String) = Unit
    override suspend fun markPhotoEstimating(id: String, serverMealId: String) = Unit
    override suspend fun markConfirmed(id: String, serverIdOnSuccess: String?) = Unit
    override suspend fun markStuck(id: String, errorCode: String, errorMessage: String?) = Unit
    override suspend fun requeue(id: String, nextAttemptAt: Instant?, errorCode: String?, errorMessage: String?) = Unit
    override suspend fun retry(id: String) = Unit
    override suspend fun revertNetworkStuckItems(): Int = 0
}

private fun sensor(id: String): SensorSession = SensorSession(
    id = id,
    startedAt = Clock.System.now(),
    endedAt = null,
    expectedLifeDays = 15.0,
    label = "Ottai #4",
    vendor = "Ottai",
    model = "One",
    excludedFromAnalytics = false,
    exclusionReason = null,
)
