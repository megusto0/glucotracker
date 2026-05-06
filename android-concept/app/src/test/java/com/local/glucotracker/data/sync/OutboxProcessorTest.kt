package com.local.glucotracker.data.sync

import com.local.glucotracker.data.api.OpenApiJson
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
import org.junit.Test

class OutboxProcessorTest {
    @Test
    fun drainsQueuedMutationsInOrder() = runTest {
        val items = listOf(
            outboxItem("1", OutboxKind.CreateMeal(draft("local-1"), TestTime, "manual")),
            outboxItem("2", OutboxKind.EditMeal("00000000-0000-0000-0000-000000000002", MealPatchPayload(title = "edit"))),
            outboxItem("3", OutboxKind.DeleteMeal("00000000-0000-0000-0000-000000000003")),
            outboxItem("4", OutboxKind.CreateFingerstick(TestTime, glucoseMmolL = 6.2)),
        )
        val repository = FakeOutboxRepository(items)
        val remote = FakeOutboxRemote()
        val processor = OutboxProcessorImpl(FakeQueueStore(repository), repository, remote, FakeSyncNotifier)

        processor.processOnce()

        assertEquals(
            listOf(
                "1:Sending",
                "1:Sent",
                "2:Sending",
                "2:Sent",
                "3:Sending",
                "3:Sent",
                "4:Sending",
                "4:Sent",
            ),
            repository.transitions,
        )
        assertEquals(
            listOf(
                "create:local-1",
                "edit:00000000-0000-0000-0000-000000000002",
                "delete:00000000-0000-0000-0000-000000000003",
                "fingerstick:6.2",
            ),
            remote.calls,
        )
    }

    @Test
    fun movesConflictToConflictStateAndExposesStrategies() = runTest {
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
        )

        processor.processOnce()

        assertEquals(OutboxState.Conflict, repository.items.getValue("conflict").state)

        val resolver = ConflictResolver()
        assertTrue(resolver.resolve(repository.items.getValue("conflict"), ConflictStrategy.KeepLocal) is ConflictResolution.RetryLocal)
        assertTrue(resolver.resolve(repository.items.getValue("conflict"), ConflictStrategy.KeepServer) is ConflictResolution.UseServer)
        assertTrue(resolver.resolve(repository.items.getValue("conflict"), ConflictStrategy.KeepBoth) is ConflictResolution.CreateBoth)
    }

    @Test
    fun photoEstimateKeepsCapturedAtThroughSerializationAndAccept() = runTest {
        val capturedAt = Instant.parse("2026-05-05T08:42:13.123Z")
        val photoKind = OutboxKind.PhotoEstimateRequest(
            localPhotoPath = "C:\\app\\photos\\photo-1.jpg",
            capturedAt = capturedAt,
            source = "photo",
        )
        val decoded = OpenApiJson.json.decodeFromString<OutboxKind>(
            OpenApiJson.json.encodeToString<OutboxKind>(photoKind),
        ) as OutboxKind.PhotoEstimateRequest
        assertEquals(capturedAt, decoded.capturedAt)

        val estimateItem = outboxItem("photo", decoded)
        val repository = FakeOutboxRepository(listOf(estimateItem))
        val remote = FakeOutboxRemote()
        val processor = OutboxProcessorImpl(FakeQueueStore(repository), repository, remote, FakeSyncNotifier)

        processor.processOnce()

        assertEquals(capturedAt, remote.photoCapturedAt)
        assertEquals(OutboxState.EstimateReady, repository.items.getValue("photo").state)

        val acceptItem = outboxItem(
            "accept",
            OutboxKind.AcceptDraft(estimateId = "draft-from-photo", eatenAt = capturedAt),
        )
        repository.items.clear()
        repository.items[acceptItem.id] = acceptItem
        repository.transitions.clear()

        processor.processOnce()

        assertEquals(0L, kotlin.math.abs(remote.acceptedEatenAt!!.toEpochMilliseconds() - capturedAt.toEpochMilliseconds()))
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
                attempts = 0,
                serverIdOnSuccess = null,
                errorMessage = null,
            )
    }
}

private class FakeQueueStore(
    private val repository: FakeOutboxRepository,
) : OutboxQueueStore {
    override suspend fun queued(): List<OutboxItem> =
        repository.items.values.filter { it.state == OutboxState.Queued }.sortedBy { it.createdAt }

    override suspend fun requeue(id: String, errorMessage: String?) {
        repository.update(id, OutboxState.Queued, errorMessage = errorMessage)
    }
}

private class FakeOutboxRepository(
    initialItems: List<OutboxItem>,
) : OutboxRepository {
    val items: MutableMap<String, OutboxItem> = initialItems.associateBy { it.id }.toMutableMap()
    val transitions: MutableList<String> = mutableListOf()

    override fun observe(): Flow<List<OutboxItem>> = flowOf(items.values.toList())

    override suspend fun enqueue(kind: OutboxKind): OutboxItem {
        val item = OutboxItem(
            id = "generated-${items.size + 1}",
            kind = kind,
            state = OutboxState.Queued,
            createdAt = OutboxProcessorTest.TestTime,
            lastAttemptAt = null,
            attempts = 0,
            serverIdOnSuccess = null,
            errorMessage = null,
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

    override suspend fun markSending(id: String) {
        transitions += "$id:Sending"
        update(id, OutboxState.Sending)
    }

    override suspend fun markSent(id: String, serverIdOnSuccess: String?) {
        transitions += "$id:Sent"
        update(id, OutboxState.Sent, serverIdOnSuccess = serverIdOnSuccess)
    }

    override suspend fun markConflict(id: String, errorMessage: String?) {
        transitions += "$id:Conflict"
        update(id, OutboxState.Conflict, errorMessage = errorMessage)
    }

    override suspend fun markEstimating(id: String) {
        transitions += "$id:Estimating"
        update(id, OutboxState.Estimating)
    }

    override suspend fun markEstimateReady(id: String, draft: MealDraft) {
        transitions += "$id:EstimateReady"
        update(id, OutboxState.EstimateReady, serverIdOnSuccess = draft.id, draft = draft)
    }

    fun update(
        id: String,
        state: OutboxState,
        serverIdOnSuccess: String? = items[id]?.serverIdOnSuccess,
        errorMessage: String? = items[id]?.errorMessage,
        draft: MealDraft? = items[id]?.draft,
    ) {
        items[id] = items.getValue(id).copy(
            state = state,
            serverIdOnSuccess = serverIdOnSuccess,
            errorMessage = errorMessage,
            draft = draft,
        )
    }
}

private class FakeOutboxRemote(
    private val conflictOnEdit: Boolean = false,
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

    override suspend fun createFingerstick(kind: OutboxKind.CreateFingerstick): String {
        calls += "fingerstick:${kind.glucoseMmolL}"
        return "fingerstick-${calls.size}"
    }

    override suspend fun requestPhotoEstimate(kind: OutboxKind.PhotoEstimateRequest): MealDraft {
        photoCapturedAt = kind.capturedAt
        return MealDraft(
            id = "draft-from-photo",
            eatenAt = kind.capturedAt,
            title = null,
            note = null,
            localPhotoPath = kind.localPhotoPath,
            totalKcal = 0.0,
            totalCarbsG = 0.0,
            totalProteinG = 0.0,
            totalFatG = 0.0,
            totalFiberG = 0.0,
        )
    }

    override suspend fun acceptDraft(kind: OutboxKind.AcceptDraft): String {
        acceptedEatenAt = kind.eatenAt
        calls += "accept:${kind.estimateId}"
        return kind.estimateId
    }
}

private object FakeSyncNotifier : SyncNotifier {
    override fun ensureChannel() = Unit
    override fun notifyEstimateReady() = Unit
    override fun photoUploadForegroundInfo(): androidx.work.ForegroundInfo =
        error("Foreground notifications are Android-only in this test.")
}
