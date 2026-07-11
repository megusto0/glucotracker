package com.local.glucotracker.ui.feature.sensor

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.domain.model.CreateFingerstickOutboxKind
import com.local.glucotracker.domain.model.CreateSensorOutboxKind
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.domain.model.PatchSensorOutboxKind
import com.local.glucotracker.domain.model.SensorQuality
import com.local.glucotracker.domain.model.SensorSession
import com.local.glucotracker.domain.repository.OutboxRepository
import com.local.glucotracker.domain.repository.SensorRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import java.util.UUID
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.datetime.Clock

data class SensorManagementState(
    val sensors: List<SensorSession> = emptyList(),
    val selectedSensorId: String? = null,
    val quality: SensorQuality? = null,
    val isRefreshing: Boolean = false,
    val qualityLoading: Boolean = false,
    val loadFailed: Boolean = false,
    val pendingSensorIds: Set<String> = emptySet(),
    val pendingCreateCount: Int = 0,
)

private data class QualityState(
    val sensorId: String? = null,
    val value: SensorQuality? = null,
    val loading: Boolean = false,
    val failed: Boolean = false,
)

@HiltViewModel
class SensorManagementViewModel @Inject constructor(
    private val sensorRepository: SensorRepository,
    private val outboxRepository: OutboxRepository,
) : ViewModel() {
    private val selectedSensorId = MutableStateFlow<String?>(null)
    private val quality = MutableStateFlow(QualityState())

    val state = combine(
        sensorRepository.observeSensors(),
        selectedSensorId,
        quality,
        outboxRepository.observe(),
    ) { cached, selectedId, qualityState, outbox ->
        val activeOutbox = outbox.filter { it.state != OutboxState.Confirmed }
        val sensors = cached.value.orEmpty()
        val resolvedSelection = selectedId?.takeIf { id -> sensors.any { it.id == id } }
            ?: sensors.firstOrNull { it.endedAt == null }?.id
            ?: sensors.firstOrNull()?.id
        SensorManagementState(
            sensors = sensors,
            selectedSensorId = resolvedSelection,
            quality = qualityState.value.takeIf { qualityState.sensorId == resolvedSelection },
            isRefreshing = cached.isRefreshing,
            qualityLoading = qualityState.loading && qualityState.sensorId == resolvedSelection,
            loadFailed = cached.value == null && !cached.isRefreshing || qualityState.failed,
            pendingSensorIds = activeOutbox.mapNotNull { item ->
                (item.kind as? PatchSensorOutboxKind)?.sensorId
            }.toSet(),
            pendingCreateCount = activeOutbox.count { it.kind is CreateSensorOutboxKind },
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = SensorManagementState(isRefreshing = true),
    )

    init {
        viewModelScope.launch {
            sensorRepository.observeSensors()
                .map { cached ->
                    cached.value.orEmpty().let { sensors ->
                        sensors.firstOrNull { it.endedAt == null }?.id ?: sensors.firstOrNull()?.id
                    }
                }
                .distinctUntilChanged()
                .collect { firstSensorId ->
                    if (selectedSensorId.value == null && firstSensorId != null) {
                        selectSensor(firstSensorId)
                    }
                }
        }
        viewModelScope.launch {
            outboxRepository.observe()
                .map { items ->
                    items.count { item ->
                        item.state == OutboxState.Confirmed &&
                            (item.kind is CreateSensorOutboxKind || item.kind is PatchSensorOutboxKind)
                    }
                }
                .distinctUntilChanged()
                .drop(1)
                .collect { sensorRepository.refreshSensors() }
        }
        viewModelScope.launch { sensorRepository.refreshSensors() }
    }

    fun refresh() {
        viewModelScope.launch {
            sensorRepository.refreshSensors()
            val selected = selectedSensorId.value
            if (selected != null) selectSensor(selected)
        }
    }

    fun selectSensor(sensorId: String) {
        selectedSensorId.value = sensorId
        viewModelScope.launch {
            quality.value = QualityState(sensorId = sensorId, loading = true)
            quality.value = runCatching { sensorRepository.sensorQuality(sensorId) }
                .fold(
                    onSuccess = { QualityState(sensorId = sensorId, value = it) },
                    onFailure = { QualityState(sensorId = sensorId, failed = true) },
                )
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

    fun startSensor(
        label: String?,
        vendor: String?,
        model: String?,
        expectedLifeDays: Double,
    ) {
        viewModelScope.launch {
            outboxRepository.enqueue(
                CreateSensorOutboxKind(
                    localId = UUID.randomUUID().toString(),
                    startedAt = Clock.System.now(),
                    expectedLifeDays = expectedLifeDays,
                    label = label.cleanOrNull(),
                    vendor = vendor.cleanOrNull(),
                    model = model.cleanOrNull(),
                ),
            )
        }
    }

    fun finishSensor(sensorId: String) {
        viewModelScope.launch {
            outboxRepository.enqueue(
                PatchSensorOutboxKind(
                    sensorId = sensorId,
                    endedAt = Clock.System.now(),
                ),
            )
        }
    }

    fun setExcluded(sensorId: String, excluded: Boolean, reason: String?) {
        viewModelScope.launch {
            outboxRepository.enqueue(
                PatchSensorOutboxKind(
                    sensorId = sensorId,
                    excludedFromAnalytics = excluded,
                    exclusionReason = reason.takeIf { excluded }?.cleanOrNull(),
                ),
            )
        }
    }
}

private fun String?.cleanOrNull(): String? = this?.trim()?.takeIf { it.isNotEmpty() }
