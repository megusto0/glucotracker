package com.local.glucotracker.data.mapper

import com.local.glucotracker.data.local.CachedMealEntity
import com.local.glucotracker.data.local.OutboxEntity
import com.local.glucotracker.domain.model.OutboxState
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class MappersTest {
    @Test
    fun postprandialResponseAcceptsNullAnchors() {
        val meal = cachedMeal(
            """{"delta_max":null,"coverage_180min":null,"glycemic_response":null,"anchors":null}""",
        ).toDomain()

        assertNotNull(meal.postprandialResponse)
        val response = meal.postprandialResponse!!
        assertNull(response.deltaMaxMmolL)
        assertNull(response.coverage180)
        assertNull(response.glycemicResponse)
        assertEquals(0, response.points.size)
    }

    @Test
    fun postprandialResponseSkipsNullAnchorEntries() {
        val meal = cachedMeal(
            """{"anchors":{"0":null,"30":{"value":null},"60":{"value":5.7}}}""",
        ).toDomain()

        assertNotNull(meal.postprandialResponse)
        val response = meal.postprandialResponse!!
        assertEquals(1, response.points.size)
        assertEquals(60, response.points.single().offsetMinutes)
        assertEquals(5.7, response.points.single().valueMmolL, 0.0)
    }

    @Test
    fun postprandialResponseTreatsJsonNullRootAsAbsent() {
        assertNull(cachedMeal("null").toDomain().postprandialResponse)
    }

    private fun cachedMeal(postprandialJson: String?): CachedMealEntity {
        val timestamp = Instant.parse("2026-07-13T12:00:00Z")
        return CachedMealEntity(
            id = "meal-1",
            eatenAt = timestamp,
            eatenAtDay = LocalDate(2026, 7, 13),
            title = "Meal",
            status = "accepted",
            source = "manual",
            note = null,
            thumbnailUrl = null,
            totalKcal = 0.0,
            totalCarbsG = 0.0,
            totalProteinG = 0.0,
            totalFatG = 0.0,
            totalFiberG = 0.0,
            updatedAt = timestamp,
            fetchedAt = timestamp,
            postprandialJson = postprandialJson,
        )
    }
}

/**
 * A queue row nobody can read must cost one entry, not the queue.
 *
 * `toDomain` decodes the stored kind and throws when it cannot, and the queue
 * read maps every row through it — so a single entry written by an older build
 * stopped every deletion and every upload, with nothing recording an attempt
 * and therefore nothing ever being marked stuck either.
 */
class OutboxRowDecodingTest {
    @Test
    fun anUnreadableKindYieldsNullRatherThanThrowing() {
        assertNull(outboxRow(kindJson = """{"type":"kind_that_no_longer_exists"}""").toDomainOrNull())
        assertNull(outboxRow(kindJson = "not json at all").toDomainOrNull())
    }

    @Test
    fun areadableRowStillMaps() {
        val row = outboxRow(
            kindJson = """{"type":"delete_meal","serverId":"11111111-1111-1111-1111-111111111111"}""",
        )
        assertNotNull(row.toDomainOrNull())
    }

    private fun outboxRow(kindJson: String) = OutboxEntity(
        id = "row",
        kindType = "delete_meal",
        kindJson = kindJson,
        state = OutboxState.Queued,
        createdAt = Instant.parse("2026-08-18T18:00:00Z"),
        lastAttemptAt = null,
        nextAttemptAt = null,
        attempts = 0,
        serverIdOnSuccess = null,
        errorMessage = null,
        localPhotoPath = null,
        enteredCurrentStateAt = Instant.parse("2026-08-18T18:00:00Z"),
        lastErrorCode = null,
        lastErrorMessage = null,
        draftJson = null,
        linkedMealId = null,
        reconciledAt = null,
    )
}
