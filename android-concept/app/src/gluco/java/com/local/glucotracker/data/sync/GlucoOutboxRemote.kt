package com.local.glucotracker.data.sync

import com.local.glucotracker.domain.model.CreateFingerstickOutboxKind
import com.local.glucotracker.domain.model.CreateNightscoutInsulinOutboxKind
import com.local.glucotracker.domain.model.CreateSensorOutboxKind
import com.local.glucotracker.domain.model.PatchSensorOutboxKind
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.generated.api.GlucoseApi
import com.local.glucotracker.generated.api.NightscoutApi
import com.local.glucotracker.generated.model.FingerstickReadingCreate
import com.local.glucotracker.generated.model.NightscoutInsulinEntryCreate
import com.local.glucotracker.generated.model.SensorSessionCreate
import com.local.glucotracker.generated.model.SensorSessionPatch
import java.math.BigDecimal
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class GlucoOutboxRemote @Inject constructor(
    private val base: KtorOutboxRemote,
    private val glucoseApi: GlucoseApi,
    private val nightscoutApi: NightscoutApi,
) : OutboxRemote by base {
    override suspend fun processFlavorKind(kind: OutboxKind): String =
        when (kind) {
            is CreateFingerstickOutboxKind -> {
                val reading = glucoseApi.createFingerstick(
                    FingerstickReadingCreate(
                        glucoseMmolL = kind.glucoseMmolL.toBigDecimal(),
                        measuredAt = kind.measuredAt,
                        meterName = kind.meterName,
                        notes = kind.notes,
                    ),
                ).bodyOrThrow()
                reading.id.toString()
            }
            is CreateNightscoutInsulinOutboxKind -> {
                val event = nightscoutApi.createNightscoutInsulin(
                    NightscoutInsulinEntryCreate(
                        insulinUnits = kind.insulinUnits.toBigDecimal(),
                        recordedAt = kind.recordedAt,
                        idempotencyKey = kind.idempotencyKey,
                    ),
                ).bodyOrThrow()
                event.nightscoutId ?: kind.idempotencyKey
            }
            is CreateSensorOutboxKind -> {
                val sensor = glucoseApi.createSensor(
                    SensorSessionCreate(
                        startedAt = kind.startedAt,
                        expectedLifeDays = BigDecimal.valueOf(kind.expectedLifeDays),
                        label = kind.label,
                        vendor = kind.vendor,
                        model = kind.model,
                    ),
                ).bodyOrThrow()
                sensor.id.toString()
            }
            is PatchSensorOutboxKind -> {
                val sensor = glucoseApi.patchSensor(
                    sensorId = UUID.fromString(kind.sensorId),
                    sensorSessionPatch = SensorSessionPatch(
                        endedAt = kind.endedAt,
                        excludedFromAnalytics = kind.excludedFromAnalytics,
                        exclusionReason = kind.exclusionReason,
                    ),
                ).bodyOrThrow()
                sensor.id.toString()
            }
            else -> base.processFlavorKind(kind)
        }
}
