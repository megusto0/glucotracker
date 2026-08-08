package com.local.glucotracker.ui.feature.history

import com.local.glucotracker.domain.model.HistoryFilter
import kotlinx.datetime.Instant
import org.junit.Assert.assertEquals
import org.junit.Test

class HistoryQuickFilterTest {
    @Test
    fun firstMealUsesEpisodeMarkerInsteadOfEarliestClockTime() {
        val earlier = row(id = "earlier", eatenAt = "2026-08-08T07:00:00Z")
        val afterSleep = row(id = "after-sleep", eatenAt = "2026-08-08T10:55:00Z")

        val result = filterHistoryRows(
            rows = listOf(earlier, afterSleep),
            filters = setOf(HistoryFilter.FirstAfterSleep),
            firstAfterSleepMealIds = setOf(afterSleep.id),
        )

        assertEquals(listOf(afterSleep.id), result.map { it.id })
    }

    @Test
    fun peakThresholdsUseStrictAbsolutePeak() {
        val ten = row(id = "ten", peakMmolL = 10.0)
        val aboveTen = row(id = "above-ten", peakMmolL = 10.1)
        val thirteen = row(id = "thirteen", peakMmolL = 13.0)
        val aboveThirteen = row(id = "above-thirteen", peakMmolL = 13.1)
        val unknown = row(id = "unknown", peakMmolL = null)
        val rows = listOf(ten, aboveTen, thirteen, aboveThirteen, unknown)

        assertEquals(
            listOf(aboveTen.id, thirteen.id, aboveThirteen.id),
            filterHistoryRows(rows, setOf(HistoryFilter.PeakAbove10)).map { it.id },
        )
        assertEquals(
            listOf(aboveThirteen.id),
            filterHistoryRows(rows, setOf(HistoryFilter.PeakAbove13)).map { it.id },
        )
    }

    @Test
    fun episodeAndPeakFiltersCanBeCombined() {
        val markedLow = row(id = "marked-low", peakMmolL = 9.9)
        val markedHigh = row(id = "marked-high", peakMmolL = 13.5)
        val unmarkedHigh = row(id = "unmarked-high", peakMmolL = 14.0)

        val result = filterHistoryRows(
            rows = listOf(markedLow, markedHigh, unmarkedHigh),
            filters = setOf(HistoryFilter.FirstAfterSleep, HistoryFilter.PeakAbove13),
            firstAfterSleepMealIds = setOf(markedLow.id, markedHigh.id),
        )

        assertEquals(listOf(markedHigh.id), result.map { it.id })
    }

    private fun row(
        id: String,
        eatenAt: String = "2026-08-08T10:00:00Z",
        peakMmolL: Double? = null,
    ) = HistoryMealRowUi(
        id = id,
        recordId = id,
        outboxId = null,
        kind = HistoryMealRowKind.Accepted,
        eatenAt = Instant.parse(eatenAt),
        title = id,
        source = HistoryMealSource.Manual,
        status = HistoryMealStatus.Accepted,
        photo = null,
        totalKcal = 100.0,
        totalCarbsG = 10.0,
        totalProteinG = 5.0,
        totalFatG = 2.0,
        isSweet = false,
        mealRole = null,
        errorMessage = null,
        peakMmolL = peakMmolL,
    )
}
