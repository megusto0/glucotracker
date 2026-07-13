package com.local.glucotracker.data.mapper

import com.local.glucotracker.data.local.CachedGlucoseEntity
import com.local.glucotracker.data.local.CachedFingerstickEntity
import com.local.glucotracker.domain.model.FingerstickReading
import com.local.glucotracker.domain.model.GlucoseRange
import com.local.glucotracker.domain.model.GlucoseReading
import com.local.glucotracker.generated.model.GlucoseDashboardPoint
import com.local.glucotracker.generated.model.GlucoseDashboardResponse
import com.local.glucotracker.generated.model.FingerstickReadingResponse
import java.math.BigDecimal
import kotlinx.datetime.Instant

private const val PackedListSeparator = "\u001F"

private fun BigDecimal?.asDouble(): Double? = this?.toDouble()
private fun BigDecimal.asDouble(): Double = toDouble()
private fun List<String>?.pack(): String = orEmpty().joinToString(PackedListSeparator)
private fun String.unpack(): List<String> = if (isBlank()) emptyList() else split(PackedListSeparator)

fun GlucoseDashboardResponse.toCachedEntities(fetchedAt: Instant): List<CachedGlucoseEntity> =
    points.map { it.toCachedEntity(fetchedAt) }

fun GlucoseDashboardPoint.toCachedEntity(fetchedAt: Instant): CachedGlucoseEntity =
    CachedGlucoseEntity(
        readingAt = timestamp,
        rawValueMmolL = rawValue.asDouble(),
        displayValueMmolL = displayValue.asDouble(),
        normalizedValueMmolL = normalizedValue.asDouble(),
        smoothedValueMmolL = smoothedValue.asDouble(),
        flagsCsv = flags.pack(),
        fetchedAt = fetchedAt,
    )

fun CachedGlucoseEntity.toDomain(): GlucoseReading =
    GlucoseReading(
        readingAt = readingAt,
        rawValueMmolL = rawValueMmolL,
        displayValueMmolL = displayValueMmolL,
        normalizedValueMmolL = normalizedValueMmolL,
        smoothedValueMmolL = smoothedValueMmolL,
        flags = flagsCsv.unpack(),
    )

fun List<CachedGlucoseEntity>.toRange(): GlucoseRange? {
    if (isEmpty()) return null
    return GlucoseRange(
        from = first().readingAt,
        to = last().readingAt,
        readings = map { it.toDomain() },
    )
}

fun GlucoseRange.withNormalizedDisplay(enabled: Boolean): GlucoseRange =
    copy(
        readings = readings.map { reading ->
            reading.copy(
                displayValueMmolL = if (enabled) {
                    reading.normalizedValueMmolL ?: reading.rawValueMmolL
                } else {
                    reading.rawValueMmolL
                },
            )
        },
    )

fun List<FingerstickReadingResponse>.toCachedFingersticks(
    fetchedAt: Instant,
): List<CachedFingerstickEntity> =
    map { response ->
        CachedFingerstickEntity(
            id = response.id.toString(),
            measuredAt = response.measuredAt,
            glucoseMmolL = response.glucoseMmolL.toDouble(),
            meterName = response.meterName,
            notes = response.notes,
            createdAt = response.createdAt,
            fetchedAt = fetchedAt,
        )
    }

fun List<CachedFingerstickEntity>.toFingersticks(): List<FingerstickReading> =
    map { entity ->
        FingerstickReading(
            id = entity.id,
            measuredAt = entity.measuredAt,
            glucoseMmolL = entity.glucoseMmolL,
            meterName = entity.meterName,
            notes = entity.notes,
            createdAt = entity.createdAt,
        )
    }
