package com.local.glucotracker.data.repository

import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import kotlinx.datetime.DatePeriod
import kotlinx.datetime.LocalDate
import kotlinx.datetime.plus

@Singleton
class EpisodeHistoryMealMarkerProvider @Inject constructor(
    private val insulinRepository: InsulinRepository,
) : HistoryMealMarkerProvider {
    override fun observe(fromDay: LocalDate, toDay: LocalDate): Flow<HistoryMealMarkers> {
        val days = daysBetween(fromDay, toDay)
        return combine(days.map(insulinRepository::observeContextForDay)) { contexts ->
            HistoryMealMarkers(
                firstAfterSleepMealIds = contexts
                    .flatMapTo(mutableSetOf()) { context -> context.firstAfterSleepMealIds },
            )
        }
    }

    override suspend fun refresh(fromDay: LocalDate, toDay: LocalDate) {
        daysBetween(fromDay, toDay).asReversed().forEach { day ->
            runCatching { insulinRepository.refreshDay(day) }
        }
    }
}

private fun daysBetween(fromDay: LocalDate, toDay: LocalDate): List<LocalDate> =
    generateSequence(fromDay) { day ->
        day.plus(DatePeriod(days = 1)).takeIf { next -> next <= toDay }
    }.toList()
