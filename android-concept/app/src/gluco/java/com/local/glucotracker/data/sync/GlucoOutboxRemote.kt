package com.local.glucotracker.data.sync

import com.local.glucotracker.domain.model.CreateFingerstickOutboxKind
import com.local.glucotracker.domain.model.CreateNightscoutInsulinOutboxKind
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.generated.api.GlucoseApi
import com.local.glucotracker.generated.api.NightscoutApi
import com.local.glucotracker.generated.model.FingerstickReadingCreate
import com.local.glucotracker.generated.model.NightscoutInsulinEntryCreate
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
            else -> base.processFlavorKind(kind)
        }
}
