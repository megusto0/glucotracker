package com.local.glucotracker.data.repository

import com.local.glucotracker.data.api.GlucoseApi
import com.local.glucotracker.data.local.CachedInsulinEventDao
import com.local.glucotracker.data.local.CachedInsulinEventEntity
import com.local.glucotracker.domain.model.InsulinDayContext
import com.local.glucotracker.domain.model.InsulinEvent
import com.local.glucotracker.domain.model.InsulinEventType
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.datetime.Clock
import kotlinx.datetime.DatePeriod
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.atStartOfDayIn
import kotlinx.datetime.plus

private const val CorrectionKind = "correction"

@Singleton
class InsulinRepository @Inject constructor(
    private val glucoseApi: GlucoseApi,
    private val insulinEventDao: CachedInsulinEventDao,
) {
    /**
     * Local-first day attribution: emits the Room cache immediately (so
     * records the user has already seen survive offline and restarts) and
     * keeps emitting as [refreshDay] lands fresh server data.
     */
    fun observeContextForDay(date: LocalDate): Flow<InsulinDayContext> =
        insulinEventDao.observeDay(date).map { entities ->
            val byMealId = mutableMapOf<String, MutableList<InsulinEvent>>()
            val orphans = mutableListOf<InsulinEvent>()
            entities.forEach { entity ->
                val event = entity.toDomain()
                val anchorMealId = entity.anchorMealId
                if (anchorMealId != null) {
                    byMealId.getOrPut(anchorMealId) { mutableListOf() }.add(event)
                } else {
                    orphans.add(event)
                }
            }
            InsulinDayContext(
                byMealId = byMealId,
                orphans = orphans,
            )
        }

    /**
     * Pull the backend episodes attribution for the day into the cache.
     * Failures (offline) leave the cached rows untouched.
     */
    suspend fun refreshDay(date: LocalDate) {
        val zone = TimeZone.currentSystemDefault()
        val from = date.atStartOfDayIn(zone)
        val to = date.plus(DatePeriod(days = 1)).atStartOfDayIn(zone)
        val fetchedAt = Clock.System.now()
        val entities = glucoseApi.episodes(from, to).episodes.flatMap { episode ->
            episode.insulin.mapNotNull { event ->
                val dose = event.insulinUnits?.toDouble() ?: return@mapNotNull null
                if (dose <= 0.0) return@mapNotNull null
                CachedInsulinEventEntity(
                    id = event.id.toString(),
                    day = date,
                    timestamp = event.timestamp,
                    doseUnits = dose,
                    kind = event.kind.value,
                    anchorMealId = event.anchorMealId?.toString(),
                    fetchedAt = fetchedAt,
                )
            }
        }
        insulinEventDao.replaceDay(date, entities)
    }
}

private fun CachedInsulinEventEntity.toDomain(): InsulinEvent =
    InsulinEvent(
        id = id,
        timestamp = timestamp,
        doseUnits = doseUnits,
        source = "Nightscout",
        sourceEventId = id,
        eventType = if (kind == CorrectionKind) {
            InsulinEventType.Correction
        } else {
            InsulinEventType.Bolus
        },
        isReadOnly = true,
    )
