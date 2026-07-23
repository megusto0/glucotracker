package com.local.glucotracker.data.local

import androidx.room.Room
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.local.glucotracker.data.api.OpenApiJson
import com.local.glucotracker.data.api.ProductsApi
import com.local.glucotracker.data.cache.CacheBudget
import com.local.glucotracker.data.repository.ProductsRepositoryImpl
import com.local.glucotracker.data.sync.MealReconciler
import com.local.glucotracker.domain.model.MealDraft
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.generated.api.DatabaseApi
import com.local.glucotracker.generated.api.PatternsApi
import com.local.glucotracker.generated.api.ProductsApi as GeneratedProductsApi
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.flow.first
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import kotlinx.serialization.encodeToString

@RunWith(AndroidJUnit4::class)
class OfflineDataInstrumentedTest {
    private lateinit var database: GlucotrackerDatabase

    @Before
    fun setUp() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        database = Room.inMemoryDatabaseBuilder(context, GlucotrackerDatabase::class.java)
            .allowMainThreadQueries()
            .build()
    }

    @After
    fun tearDown() {
        database.close()
    }

    @Test
    fun productSearchLocalUsesPreseededFtsWithoutNetwork() = runTest {
        database.cachedProductDao().upsertAll(
            listOf(
                CachedProductEntity(
                    id = "product-1",
                    name = "воппер",
                    kind = "product",
                    subtitle = "бургер",
                    brand = "test",
                    aliasesCsv = "воппе",
                    imageUrl = null,
                    kcal = 250.0,
                    carbsG = 30.0,
                    proteinG = 12.0,
                    fatG = 11.0,
                    fiberG = 2.0,
                    defaultGrams = 100.0,
                    usageCount = 3,
                    lastUsedAt = null,
                    fetchedAt = Instant.parse("2026-05-05T10:00:00Z"),
                ),
            ),
        )
        val repository = ProductsRepositoryImpl(
            productDao = database.cachedProductDao(),
            templateDao = database.cachedTemplateDao(),
            productsApi = ProductsApi(
                GeneratedProductsApi(),
                PatternsApi(),
                DatabaseApi(),
            ),
        )

        val results = repository.searchLocal("воппе")

        assertEquals(1, results.size)
        assertEquals("воппер", results.single().name)
    }

    @Test
    fun pruneRemovesOldMealsAndKeepsOutboxItems() = runTest {
        val oldInstant = Instant.parse("2026-04-20T12:00:00Z")
        database.cachedMealDao().upsertAll(
            listOf(
                CachedMealEntity(
                    id = "meal-1",
                    eatenAt = oldInstant,
                    eatenAtDay = LocalDate.parse("2026-04-20"),
                    title = null,
                    status = "accepted",
                    source = "manual",
                    note = null,
                    thumbnailUrl = null,
                    totalKcal = 100.0,
                    totalCarbsG = 10.0,
                    totalProteinG = 4.0,
                    totalFatG = 3.0,
                    totalFiberG = 1.0,
                    updatedAt = oldInstant,
                    fetchedAt = oldInstant,
                ),
            ),
        )
        database.outboxDao().upsert(
            OutboxEntity(
                id = "outbox-1",
                kindType = "create_meal",
                kindJson = OpenApiJson.json.encodeToString<OutboxKind>(
                    OutboxKind.CreateMeal(
                        payload = MealDraft(
                            id = "local-draft-1",
                            eatenAt = oldInstant,
                            title = null,
                            note = null,
                            localPhotoPath = null,
                            totalKcal = 100.0,
                            totalCarbsG = 10.0,
                            totalProteinG = 4.0,
                            totalFatG = 3.0,
                            totalFiberG = 1.0,
                        ),
                        eatenAt = oldInstant,
                        source = "manual",
                    ),
                ),
                state = OutboxState.Queued,
                createdAt = oldInstant,
                lastAttemptAt = null,
                nextAttemptAt = null,
                attempts = 0,
                serverIdOnSuccess = null,
                errorMessage = null,
                enteredCurrentStateAt = oldInstant,
                lastErrorCode = null,
                lastErrorMessage = null,
                draftJson = null,
                localPhotoPath = null,
            ),
        )

        CacheBudget.prune(database, now = Instant.parse("2026-05-05T12:00:00Z"))

        assertEquals(0, database.cachedMealDao().countAll())
        assertEquals(1, database.outboxDao().countAll())
        assertTrue(database.outboxDao().countAll() > 0)
    }

    @Test
    fun reconciliationKeepsConfirmedHandoffRowUntilAcceptedMealIsCached() = runTest {
        val capturedAt = Instant.parse("2026-05-05T12:00:00Z")
        val idempotencyKey = "photo-key-1"
        database.outboxDao().upsert(
            OutboxEntity(
                id = "outbox-photo-1",
                kindType = "captured_meal",
                kindJson = OpenApiJson.json.encodeToString<OutboxKind>(
                    OutboxKind.CapturedMeal(
                        localPhotoPath = "/photos/photo-1.jpg",
                        capturedAt = capturedAt,
                        source = "photo",
                        idempotencyKey = idempotencyKey,
                    ),
                ),
                state = OutboxState.Queued,
                createdAt = capturedAt,
                lastAttemptAt = capturedAt,
                nextAttemptAt = null,
                attempts = 1,
                serverIdOnSuccess = null,
                errorMessage = null,
                enteredCurrentStateAt = capturedAt,
                lastErrorCode = null,
                lastErrorMessage = null,
                draftJson = null,
                localPhotoPath = "/photos/photo-1.jpg",
            ),
        )

        MealReconciler(database.outboxDao()).reconcileByKey(
            idempotencyKey = idempotencyKey,
            mealId = "meal-1",
        )

        val reconciled = database.outboxDao()
            .findInStates(listOf(OutboxState.Confirmed))
            .single()
        assertEquals("outbox-photo-1", reconciled.id)
        assertEquals("meal-1", reconciled.serverIdOnSuccess)
        assertEquals("meal-1", reconciled.linkedMealId)
    }

    @Test
    fun mealHistoryFiltersAndFtsUseLocalCache() = runTest {
        val first = Instant.parse("2026-05-05T08:00:00Z")
        val second = Instant.parse("2026-05-05T12:00:00Z")
        database.cachedMealDao().upsertAll(
            listOf(
                CachedMealEntity(
                    id = "meal-cgm",
                    eatenAt = first,
                    eatenAtDay = LocalDate.parse("2026-05-05"),
                    title = "oats",
                    status = "accepted",
                    source = "photo",
                    note = "breakfast",
                    thumbnailUrl = "photo.jpg",
                    totalKcal = 300.0,
                    totalCarbsG = 42.0,
                    totalProteinG = 12.0,
                    totalFatG = 8.0,
                    totalFiberG = 5.0,
                    updatedAt = first,
                    fetchedAt = first,
                    confidence = 0.62,
                    hasCgm = true,
                    hasInsulin = true,
                ),
                CachedMealEntity(
                    id = "meal-manual",
                    eatenAt = second,
                    eatenAtDay = LocalDate.parse("2026-05-05"),
                    title = "soup",
                    status = "accepted",
                    source = "manual",
                    note = null,
                    thumbnailUrl = null,
                    totalKcal = 250.0,
                    totalCarbsG = 18.0,
                    totalProteinG = 10.0,
                    totalFatG = 9.0,
                    totalFiberG = 3.0,
                    updatedAt = second,
                    fetchedAt = second,
                    confidence = 0.95,
                    hasCgm = false,
                    hasInsulin = false,
                ),
            ),
        )

        val from = Instant.parse("2026-05-05T00:00:00Z")
        val to = Instant.parse("2026-05-06T00:00:00Z")
        val filtered = database.cachedMealDao().observeHistorySearch(
            from = from,
            to = to,
            query = "oat*",
            withCgm = true,
            withInsulin = true,
            lowConfidence = true,
            photoOnly = true,
            status = "accepted",
            lowConfidenceThreshold = 0.8,
        ).first()

        assertEquals(1, filtered.size)
        assertEquals("meal-cgm", filtered.single().id)
    }
}
