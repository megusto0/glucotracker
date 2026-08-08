package com.local.glucotracker.ui.feature.today

import app.cash.turbine.test
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.test.runTest
import kotlinx.datetime.LocalDate

class TodayDateSwitchTest {
    @Test
    fun newDateWaitsForItsOwnSnapshotInsteadOfReusingPreviousDay() = runTest {
        val dates = MutableSharedFlow<LocalDate>(extraBufferCapacity = 1)
        val firstDay = LocalDate(2026, 8, 7)
        val secondDay = LocalDate(2026, 8, 8)
        val snapshots = mapOf(
            firstDay to MutableSharedFlow<String>(extraBufferCapacity = 1),
            secondDay to MutableSharedFlow<String>(extraBufferCapacity = 1),
        )

        dates.switchDated { snapshots.getValue(it) }.test {
            dates.emit(firstDay)
            snapshots.getValue(firstDay).emit("first")
            assertEquals(DatedValue(firstDay, "first"), awaitItem())

            dates.emit(secondDay)
            expectNoEvents()

            snapshots.getValue(secondDay).emit("second")
            assertEquals(DatedValue(secondDay, "second"), awaitItem())
            cancelAndIgnoreRemainingEvents()
        }
    }
}
