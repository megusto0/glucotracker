package com.local.glucotracker.data.sync

import androidx.room.withTransaction
import com.local.glucotracker.data.local.GlucotrackerDatabase
import com.local.glucotracker.data.local.OutboxDao
import com.local.glucotracker.data.mapper.toDomain
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.repository.OutboxRepository
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.CancellationException

interface OutboxProcessor {
    suspend fun processOnce()
}

@Singleton
class OutboxProcessorImpl @Inject constructor(
    private val queueStore: OutboxQueueStore,
    private val outboxRepository: OutboxRepository,
    private val remote: OutboxRemote,
    private val notifier: SyncNotifier,
) : OutboxProcessor {
    override suspend fun processOnce() {
        queueStore.queued().forEach { item ->
            processItem(item)
        }
    }

    private suspend fun processItem(item: OutboxItem) {
        try {
            when (val kind = item.kind) {
                is OutboxKind.PhotoEstimateRequest -> processPhotoEstimate(item, kind)
                is OutboxKind.AcceptDraft -> sendMutation(item) { remote.acceptDraft(kind) }
                is OutboxKind.CopyMealItemWeight -> sendMutation(item) { remote.copyMealItemWeight(kind) }
                is OutboxKind.CreateMeal -> sendMutation(item) { remote.createMeal(kind) }
                is OutboxKind.EditMeal -> sendMutation(item) { remote.editMeal(kind) }
                is OutboxKind.DeleteMeal -> sendMutation(item) { remote.deleteMeal(kind) }
                is OutboxKind.PatchMealItem -> sendMutation(item) { remote.patchMealItem(kind) }
                is OutboxKind.CreateFingerstick -> sendMutation(item) { remote.createFingerstick(kind) }
            }
        } catch (cancellation: CancellationException) {
            throw cancellation
        } catch (alreadySynced: OutboxAlreadySyncedException) {
            outboxRepository.markSent(item.id, alreadySynced.serverId)
        } catch (conflict: OutboxConflictException) {
            outboxRepository.markConflict(item.id, conflict.message)
        } catch (throwable: Throwable) {
            queueStore.requeue(item.id, throwable.message)
        }
    }

    private suspend fun processPhotoEstimate(
        item: OutboxItem,
        kind: OutboxKind.PhotoEstimateRequest,
    ) {
        outboxRepository.markEstimating(item.id)
        val serverId = remote.requestPhotoEstimate(kind)
        outboxRepository.markSent(item.id, serverId)
    }

    private suspend fun sendMutation(
        item: OutboxItem,
        send: suspend () -> String,
    ) {
        outboxRepository.markSending(item.id)
        val serverId = send()
        outboxRepository.markSent(item.id, serverId)
    }
}

interface OutboxQueueStore {
    suspend fun queued(): List<OutboxItem>
    suspend fun requeue(id: String, errorMessage: String?)
}

@Singleton
class RoomOutboxQueueStore @Inject constructor(
    private val database: GlucotrackerDatabase,
    private val outboxDao: OutboxDao,
) : OutboxQueueStore {
    override suspend fun queued(): List<OutboxItem> =
        outboxDao.queuedItems()
            .map { it.toDomain() }
            .sortedWith(compareBy<OutboxItem> { it.kind.queuePriority() }.thenBy { it.createdAt })

    override suspend fun requeue(id: String, errorMessage: String?) {
        database.withTransaction {
            outboxDao.markQueuedForRetry(id, errorMessage)
        }
    }
}

private fun OutboxKind.queuePriority(): Int =
    when (this) {
        is OutboxKind.AcceptDraft -> 0
        is OutboxKind.CreateMeal,
        is OutboxKind.EditMeal,
        is OutboxKind.DeleteMeal,
        is OutboxKind.PatchMealItem,
        is OutboxKind.CopyMealItemWeight,
        is OutboxKind.CreateFingerstick,
        -> 1
        is OutboxKind.PhotoEstimateRequest -> 2
    }
