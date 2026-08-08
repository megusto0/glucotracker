package com.local.glucotracker.data.repository

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.datetime.LocalDate

data class HistoryMealMarkers(
    val firstAfterSleepMealIds: Set<String> = emptySet(),
)

interface HistoryMealMarkerProvider {
    fun observe(fromDay: LocalDate, toDay: LocalDate): Flow<HistoryMealMarkers>

    suspend fun refresh(fromDay: LocalDate, toDay: LocalDate)
}

object NoopHistoryMealMarkerProvider : HistoryMealMarkerProvider {
    override fun observe(fromDay: LocalDate, toDay: LocalDate): Flow<HistoryMealMarkers> =
        flowOf(HistoryMealMarkers())

    override suspend fun refresh(fromDay: LocalDate, toDay: LocalDate) = Unit
}
