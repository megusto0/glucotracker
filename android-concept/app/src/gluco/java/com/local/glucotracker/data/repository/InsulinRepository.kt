package com.local.glucotracker.data.repository

import com.local.glucotracker.data.api.NightscoutApi
import com.local.glucotracker.domain.model.InsulinEvent
import com.local.glucotracker.domain.model.InsulinEventType
import com.local.glucotracker.generated.model.NightscoutInsulinEventResponse
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.datetime.DatePeriod
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.atStartOfDayIn
import kotlinx.datetime.plus

@Singleton
class InsulinRepository @Inject constructor(
    private val nightscoutApi: NightscoutApi,
) {
    suspend fun eventsForDay(date: LocalDate): List<InsulinEvent> {
        val from = date.atStartOfDayIn(TimeZone.currentSystemDefault())
        val to = date.plus(DatePeriod(days = 1)).atStartOfDayIn(TimeZone.currentSystemDefault())
        return nightscoutApi.insulin(from, to).mapNotNull { row -> row.toDomain() }
    }
}

private fun NightscoutInsulinEventResponse.toDomain(): InsulinEvent? {
    val dose = insulinUnits?.toDouble() ?: return null
    if (dose <= 0.0) return null
    val sourceId = nightscoutId?.takeIf { it.isNotBlank() }
    return InsulinEvent(
        id = sourceId ?: stableGeneratedId(timestamp, dose, eventType, insulinType),
        timestamp = timestamp,
        doseUnits = dose,
        source = "Nightscout",
        sourceEventId = sourceId,
        eventType = classifyInsulinEvent(eventType = eventType, insulinType = insulinType),
        isReadOnly = true,
    )
}

private fun classifyInsulinEvent(eventType: String?, insulinType: String?): InsulinEventType {
    val text = listOfNotNull(eventType, insulinType).joinToString(" ").lowercase()
    return when {
        "basal" in text -> InsulinEventType.Basal
        "correction" in text -> InsulinEventType.Correction
        "bolus" in text || "insulin" in text -> InsulinEventType.Bolus
        else -> InsulinEventType.Unknown
    }
}

private fun stableGeneratedId(
    timestamp: Instant,
    dose: Double,
    eventType: String?,
    insulinType: String?,
): String =
    UUID.nameUUIDFromBytes(
        "${timestamp.toEpochMilliseconds()}:$dose:${eventType.orEmpty()}:${insulinType.orEmpty()}".toByteArray(),
    ).toString()
