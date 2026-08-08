package com.local.glucotracker.data.repository

import com.local.glucotracker.data.local.CachedEpisodeEntity
import com.local.glucotracker.data.local.CachedInsulinEventEntity
import com.local.glucotracker.domain.model.EpisodeOutcomeKind
import com.local.glucotracker.domain.model.EpisodeOutcomeStatus
import com.local.glucotracker.domain.model.EpisodeTherapyClass
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertSame
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate

class InsulinRepositoryCacheTest {
    @Test
    fun cachedSnapshotRestoresGroupingClassificationKeysAndBothFooterIndexes() {
        val fetchedAt = Instant.parse("2026-08-08T10:00:00Z")
        val day = LocalDate(2026, 8, 8)
        val firstMeal = "11111111-1111-1111-1111-111111111111"
        val secondMeal = "22222222-2222-2222-2222-222222222222"
        val insulinId = "33333333-3333-3333-3333-333333333333"
        val episode = CachedEpisodeEntity(
            userId = "user-a",
            key = "m:$firstMeal",
            day = day,
            startAt = Instant.parse("2026-08-08T08:00:00Z"),
            classification = "meal",
            mealIdsCsv = "$firstMeal,$secondMeal",
            insulinIdsCsv = insulinId,
            outcomeStatus = "complete",
            outcomeKind = "peak",
            outcomeStartValue = 5.6,
            outcomeResultValue = 8.2,
            outcomeDeltaMmolL = 2.6,
            outcomeIsLow = false,
            fetchedAt = fetchedAt,
        )
        val insulin = CachedInsulinEventEntity(
            id = insulinId,
            userId = "user-a",
            day = day,
            timestamp = Instant.parse("2026-08-08T07:55:00Z"),
            doseUnits = 4.0,
            kind = "food",
            anchorMealId = firstMeal,
            isEditable = false,
            fetchedAt = fetchedAt,
        )

        val context = cachedContext(listOf(insulin), listOf(episode))

        assertEquals(listOf(listOf(firstMeal, secondMeal)), context.mealEpisodeGroups)
        assertEquals(EpisodeTherapyClass.Meal, context.classificationByMealId[secondMeal])
        assertEquals("m:$firstMeal", context.episodeKeyByMealId[firstMeal])
        assertEquals(EpisodeOutcomeStatus.Complete, context.footerByMealId[firstMeal]?.outcome?.status)
        assertEquals(EpisodeOutcomeKind.Peak, context.footerByInsulinId[insulinId]?.outcome?.kind)
        assertSame(context.footerByMealId[firstMeal], context.footerByInsulinId[insulinId])
        assertEquals(insulinId, context.byMealId[firstMeal]?.single()?.id)
    }
}
