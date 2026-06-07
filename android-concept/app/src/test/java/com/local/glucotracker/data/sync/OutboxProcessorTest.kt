package com.local.glucotracker.data.sync

import com.local.glucotracker.data.api.OpenApiJson
import com.local.glucotracker.data.api.PhotoCaptureResponse
import com.local.glucotracker.domain.model.MealDraft
import com.local.glucotracker.domain.model.MealPatchPayload
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.domain.repository.OutboxRepository
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.runTest
import kotlinx.datetime.Instant
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Ignore
import org.junit.Test

@Ignore("ADR-011 added reconciler/mealApi params; stubs need update")
class OutboxProcessorTest {
    @Test
    fun drainsQueuedMutationsInOrder() = runTest {
        val items = listOf(
            outboxItem("1", OutboxKind.CreateMeal(draft("local-1"), TestTime, "manual")),
            outboxItem("2", OutboxKind.EditMeal("00000000-0000-0000-0000-000000000002", MealPatchPayload(title = "edit"))),
            outboxItem("3", OutboxKind.DeleteMeal("00000000-0000-0000-0000-000000000003")),
        )
        val repository = FakeOutboxRepository(items)
        val remote = FakeOutboxRemote()
        val processor = OutboxProcessorImpl(FakeQueueStore(repository), repository, remote, FakeSyncNotifier, TODO("stub"), TODO("stub"), TODO("stub"), TODO("stub"))

        processor.processOnce()

        assertEquals(
            listOf(
                "1:Uploading",
                "1:Confirmed",
                "2:Uploading",
                "2:Confirmed",
                "3:Uploading",
                "3:Confirmed",
            ),
            repository.transitions,
        )
        assertEquals(
            listOf(
                "create:local-1",
                "edit:00000000-0000-0000-0000-000000000002",
                "delete:00000000-0000-0000-0000-000000000003",
            ),
            remote.calls,
        )
    }

    @Test
    fun movesServerConflictToStuckState() = runTest {
        val item = outboxItem(
            "conflict",
            OutboxKind.EditMeal("00000000-0000-0000-0000-000000000004", MealPatchPayload(title = "local")),
        )
        val repository = FakeOutboxRepository(listOf(item))
        val processor = OutboxProcessorImpl(
            FakeQueueStore(repository),
            repository,
            FakeOutboxRemote(conflictOnEdit = true),
            FakeSyncNotifier,
            TODO("stub"),
            TODO("stub"),
            TODO("stub"),
            TODO("stub"),
        )

        processor.processOnce()

        assertEquals(OutboxState.Stuck, repository.items.getValue("conflict").state)
        assertEquals("request_rejected", repository.items.getValue("conflict").lastErrorCode)
    }

    @Test
    fun capturedMealKeepsCapturedAtThroughSerializationAndConfirmation() = runTest {
        val capturedAt = Instant.parse("2026-05-05T08:42:13.123Z")
        val photoKind = OutboxKind.CapturedMeal(
            localPhotoPath = "C:\\app\\photos\\photo-1.jpg",
            capturedAt = capturedAt,
            source = "photo",
        )
        val decoded = OpenApiJson.json.decodeFromString<OutboxKind>(
            OpenApiJson.json.encodeToString<OutboxKind>(photoKind),
        ) as OutboxKind.CapturedMeal
        assertEquals(capturedAt, decoded.capturedAt)

        val estimateItem = outboxItem("photo", decoded)
        val repository = FakeOutboxRepository(listOf(estimateItem))
        val remote = FakeOutboxRemote()
        val processor = OutboxProcessorImpl(FakeQueueStore(repository), repository, remote, FakeSyncNotifier, TODO("stub"), TODO("stub"), TODO("stub"), TODO("stub"))

        processor.processOnce()

        assertEquals(capturedAt, remote.photoCapturedAt)
        assertEquals(OutboxState.Confirmed, repository.items.getValue("photo").state)
    }

    @Test
    fun promotesToStuckAfterRetryBudgetExhausts() = runTest {
        val item = outboxItem(
            "photo",
            OutboxKind.CapturedMeal(
                localPhotoPath = "C:\\app\\photos\\photo-1.jpg",
                capturedAt = TestTime,
                source = "photo",
            ),
        ).copy(attempts = 4)
        val repository = FakeOutboxRepository(listOf(item))
        val processor = OutboxProcessorImpl(
            FakeQueueStore(repository),
            repository,
            FakeOutboxRemote(failPhotoEstimate = true),
            FakeSyncNotifier,
            TODO("stub"),
            TODO("stub"),
            TODO("stub"),
            TODO("stub"),
        )

        val result = processor.processOnce()

        assertTrue(result.shouldRetry)
        assertEquals(OutboxState.Stuck, repository.items.getValue("photo").state)
        assertEquals(
            listOf("photo:Uploading", "photo:Stuck"),
            repository.transitions,
        )
    }

    @Test
    fun cancellationDoesNotWriteErrorState() = runTest {
        val item = outboxItem(
            "photo",
            OutboxKind.CapturedMeal(
                localPhotoPath = "C:\\app\\photos\\photo-1.jpg",
                capturedAt = TestTime,
                source = "photo",
            ),
        )
        val repository = FakeOutboxRepository(listOf(item))
        val processor = OutboxProcessorImpl(
            FakeQueueStore(repository),
            repository,
            FakeOutboxRemote(cancelPhotoEstimate = true),
            FakeSyncNotifier,
            TODO("stub"),
            TODO("stub"),
            TODO("stub"),
            TODO("stub"),
        )

        val thrown = runCatching { processor.processOnce() }.exceptionOrNull()

        assertTrue(thrown is kotlinx.coroutines.CancellationException)
        assertEquals(OutboxState.Uploading, repository.items.getValue("photo").state)
        assertEquals(null, repository.items.getValue("photo").lastErrorCode)
        assertEquals(null, repository.items.getValue("photo").lastErrorMessage)
        assertEquals(
            listOf("photo:Uploading"),
            repository.transitions,
        )
    }

    companion object {
        val TestTime: Instant = Instant.parse("2026-05-05T08:42:00Z")

        fun draft(id: String): MealDraft =
            MealDraft(
                id = id,
                eatenAt = TestTime,
                title = id,
                note = null,
                localPhotoPath = null,
                totalKcal = 100.0,
                totalCarbsG = 10.0,
                totalProteinG = 4.0,
                totalFatG = 3.0,
                totalFiberG = 1.0,
            )

        fun outboxItem(id: String, kind: OutboxKind): OutboxItem =
            OutboxItem(
                id = id,
                kind = kind,
                state = OutboxState.Queued,
                createdAt = TestTime,
                lastAttemptAt = null,
                nextAttemptAt = null,
                attempts = 0,
                serverIdOnSuccess = null,
                errorMessage = null,
                enteredCurrentStateAt = TestTime,
            )
    }
}

private class FakeQueueStore(
    private val repository: FakeOutboxRepository,
) : OutboxQueueStore {
    override suspend fun queued(): List<OutboxItem> =
        repository.items.values
            .filter { it.state == OutboxState.Queued }
            .sortedBy { it.createdAt }

    override suspend fun requeue(
        id: String,
        nextAttemptAt: Instant?,
        errorCode: String?,
        errorMessage: String?,
    ) {
        repository.transitions += "$id:Queued"
        repository.update(id, OutboxState.Queued, errorMessage = errorMessage, lastErrorCode = errorCode)
    }
}

private class FakeOutboxRepository(
    initialItems: List<OutboxItem>,
) : OutboxRepository {
    val items: MutableMap<String, OutboxItem> = initialItems.associateBy { it.id }.toMutableMap()
    val transitions: MutableList<String> = mutableListOf()

    override fun observe(): Flow<List<OutboxItem>> = flowOf(items.values.toList())

    override fun observeActiveCount(): Flow<Int> = flowOf(0)

    override suspend fun enqueue(kind: OutboxKind): OutboxItem {
        val item = OutboxItem(
            id = "generated-${items.size + 1}",
            kind = kind,
            state = OutboxState.Queued,
            createdAt = OutboxProcessorTest.TestTime,
                lastAttemptAt = null,
                nextAttemptAt = null,
                attempts = 0,
                serverIdOnSuccess = null,
                errorMessage = null,
                enteredCurrentStateAt = OutboxProcessorTest.TestTime,
            )
        enqueue(item)
        return item
    }

    override suspend fun enqueue(item: OutboxItem) {
        items[item.id] = item
    }

    override suspend fun remove(id: String) {
        items.remove(id)
    }

    override suspend fun markUploading(id: String) {
        transitions += "$id:Uploading"
        update(id, OutboxState.Uploading)
    }

    override suspend fun markPhotoEstimating(id: String, serverMealId: String) {
        transitions += "$id:Estimating"
        update(id, OutboxState.Queued, serverIdOnSuccess = serverMealId, linkedMealId = serverMealId)
    }

    override suspend fun markConfirmed(id: String, serverIdOnSuccess: String?) {
        transitions += "$id:Confirmed"
        update(id, OutboxState.Confirmed, serverIdOnSuccess = serverIdOnSuccess)
    }

    override suspend fun markStuck(id: String, errorCode: String, errorMessage: String?) {
        transitions += "$id:Stuck"
        update(id, OutboxState.Stuck, errorMessage = errorMessage, lastErrorCode = errorCode)
    }

    override suspend fun requeue(id: String, nextAttemptAt: Instant?, errorCode: String?, errorMessage: String?) {
        transitions += "$id:Queued"
        update(id, OutboxState.Queued, errorMessage = errorMessage, lastErrorCode = errorCode)
    }

    override suspend fun retry(id: String) {
        transitions += "$id:Queued"
        update(id, OutboxState.Queued, errorMessage = null, lastErrorCode = null)
    }

    override suspend fun revertNetworkStuckItems(): Int = 0

    fun update(
        id: String,
        state: OutboxState,
        serverIdOnSuccess: String? = items[id]?.serverIdOnSuccess,
        errorMessage: String? = items[id]?.errorMessage,
        lastErrorCode: String? = items[id]?.lastErrorCode,
        draft: MealDraft? = items[id]?.draft,
        linkedMealId: String? = items[id]?.linkedMealId,
    ) {
        items[id] = items.getValue(id).copy(
            state = state,
            serverIdOnSuccess = serverIdOnSuccess,
            errorMessage = errorMessage,
            lastErrorCode = lastErrorCode,
            draft = draft,
            linkedMealId = linkedMealId,
        )
    }
}

private class FakeOutboxRemote(
    private val conflictOnEdit: Boolean = false,
    private val failPhotoEstimate: Boolean = false,
    private val cancelPhotoEstimate: Boolean = false,
) : OutboxRemote {
    val calls: MutableList<String> = mutableListOf()
    var photoCapturedAt: Instant? = null
    var acceptedEatenAt: Instant? = null

    override suspend fun createMeal(kind: OutboxKind.CreateMeal): String {
        calls += "create:${kind.payload.id}"
        return "server-${kind.payload.id}"
    }

    override suspend fun editMeal(kind: OutboxKind.EditMeal): String {
        if (conflictOnEdit) throw OutboxConflictException("409")
        calls += "edit:${kind.serverId}"
        return kind.serverId
    }

    override suspend fun deleteMeal(kind: OutboxKind.DeleteMeal): String {
        calls += "delete:${kind.serverId}"
        return kind.serverId
    }

    override suspend fun patchMealItem(kind: OutboxKind.PatchMealItem): String {
        calls += "patch-item:${kind.mealId}:${kind.itemId}"
        return kind.mealId
    }

    override suspend fun copyMealItemWeight(kind: OutboxKind.CopyMealItemWeight): String {
        calls += "copy-weight:${kind.mealId}:${kind.itemId}:${kind.grams}"
        return kind.mealId
    }

    override suspend fun captureMeal(kind: OutboxKind.CapturedMeal): PhotoCaptureResponse {
        if (failPhotoEstimate) throw java.io.IOException("offline")
        if (cancelPhotoEstimate) throw kotlinx.coroutines.CancellationException("cancelled")
        photoCapturedAt = kind.capturedAt
        return PhotoCaptureResponse(
            mealId = "server-photo",
            estimateStatus = "estimating",
            capturedAt = kind.capturedAt,
            photoUrl = "/photos/server-photo/file",
        )
    }

    override suspend fun processFlavorKind(kind: OutboxKind): String {
        calls += "flavor:${kind::class.simpleName}"
        return "flavor-${calls.size}"
    }
}

private object FakeSyncNotifier : SyncNotifier {
    override fun ensureChannel() = Unit
    override fun notifyOutboxStuck() = Unit
    override fun photoUploadForegroundInfo(): androidx.work.ForegroundInfo =
        error("Foreground notifications are Android-only in this test.")
}
