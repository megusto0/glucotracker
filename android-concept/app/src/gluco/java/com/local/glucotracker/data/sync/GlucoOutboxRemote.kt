package com.local.glucotracker.data.sync

import com.local.glucotracker.domain.model.CreateFingerstickOutboxKind
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.generated.api.GlucoseApi
import com.local.glucotracker.generated.model.FingerstickReadingCreate
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class GlucoOutboxRemote @Inject constructor(
    private val base: KtorOutboxRemote,
    private val glucoseApi: GlucoseApi,
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
            else -> base.processFlavorKind(kind)
        }
}
