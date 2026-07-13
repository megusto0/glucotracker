package com.local.glucotracker.domain.model

import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

data class GlucoseReading(
    val readingAt: Instant,
    val rawValueMmolL: Double,
    val displayValueMmolL: Double,
    val normalizedValueMmolL: Double?,
    val smoothedValueMmolL: Double?,
    val flags: List<String>,
)

data class GlucoseRange(
    val from: Instant,
    val to: Instant,
    val readings: List<GlucoseReading>,
)

data class FingerstickReading(
    val id: String,
    val measuredAt: Instant,
    val glucoseMmolL: Double,
    val meterName: String?,
    val notes: String?,
    val createdAt: Instant,
)

data class SensorSession(
    val id: String,
    val startedAt: Instant,
    val endedAt: Instant?,
    val expectedLifeDays: Double,
    val label: String?,
    val vendor: String?,
    val model: String?,
    val excludedFromAnalytics: Boolean,
    val exclusionReason: String?,
)

data class SensorQuality(
    val qualityScore: Int,
    val confidence: SensorQualityConfidence,
    val sensorAgeDays: Double?,
    val sensorPhase: SensorPhase?,
    val fingerstickCount: Int,
    val validCalibrationPoints: Int,
    val missingDataPercent: Double?,
    val noiseScore: Double,
    val mardPercent: Double?,
    val suspectedCompressionCount: Int,
)

enum class SensorQualityConfidence {
    None,
    Low,
    Medium,
    High,
}

enum class SensorPhase {
    Warmup,
    Stable,
    EndOfLife,
}

@Serializable
@SerialName("create_fingerstick")
data class CreateFingerstickOutboxKind(
    val measuredAt: Instant,
    val glucoseMmolL: Double,
    val meterName: String? = null,
    val notes: String? = null,
) : OutboxKind

@Serializable
@SerialName("create_sensor")
data class CreateSensorOutboxKind(
    val localId: String,
    val startedAt: Instant,
    val expectedLifeDays: Double,
    val label: String? = null,
    val vendor: String? = null,
    val model: String? = null,
) : OutboxKind

@Serializable
@SerialName("patch_sensor")
data class PatchSensorOutboxKind(
    val sensorId: String,
    val endedAt: Instant? = null,
    val excludedFromAnalytics: Boolean? = null,
    val exclusionReason: String? = null,
) : OutboxKind

@Serializable
@SerialName("create_nightscout_insulin")
data class CreateNightscoutInsulinOutboxKind(
    val recordedAt: Instant,
    val insulinUnits: Double,
    val idempotencyKey: String,
) : OutboxKind

@Serializable
@SerialName("update_nightscout_insulin")
data class UpdateNightscoutInsulinOutboxKind(
    val eventId: String,
    val originalRecordedAt: Instant,
    val recordedAt: Instant,
    val insulinUnits: Double,
) : OutboxKind

@Serializable
@SerialName("delete_nightscout_insulin")
data class DeleteNightscoutInsulinOutboxKind(
    val eventId: String,
    val recordedAt: Instant,
) : OutboxKind

enum class NightscoutConnectionState {
    Unknown,
    Connected,
    Disconnected,
}

data class NightscoutStatus(
    val lastSyncAt: Instant?,
    val queueDepth: Int,
    val connectionState: NightscoutConnectionState,
)

data class NightscoutDayStatus(
    val date: LocalDate,
    val configured: Boolean,
    val connected: Boolean,
    val acceptedMealsCount: Int,
    val unsyncedMealsCount: Int,
    val syncedMealsCount: Int,
    val failedMealsCount: Int,
    val lastSyncAt: Instant?,
)
