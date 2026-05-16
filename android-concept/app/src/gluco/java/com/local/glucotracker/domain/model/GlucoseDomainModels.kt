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
    val tirSegments: List<TirSegment>,
)

data class TirSegment(
    val label: String,
    val percent: Int,
)

@Serializable
@SerialName("create_fingerstick")
data class CreateFingerstickOutboxKind(
    val measuredAt: Instant,
    val glucoseMmolL: Double,
    val meterName: String? = null,
    val notes: String? = null,
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
