package com.local.glucotracker.data.sync

import androidx.room.withTransaction
import com.local.glucotracker.data.api.MealApi
import com.local.glucotracker.data.error.ErrorTranslator
import com.local.glucotracker.data.local.GlucotrackerDatabase
import com.local.glucotracker.data.local.OutboxDao
import com.local.glucotracker.data.mapper.toDomain
import com.local.glucotracker.data.sync.MealReconciler
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.repository.OutboxRepository
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.CancellationException
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant
import kotlin.time.Duration.Companion.minutes

interface OutboxProcessor {
    suspend fun processOnce(): OutboxProcessResult
}

data class OutboxProcessResult(
    val processedCount: Int,
    val transientFailureCount: Int,
) {
    val shouldRetry: Boolean = transientFailureCount > 0
}

@Singleton
class OutboxProcessorImpl @Inject constructor(
    private val queueStore: OutboxQueueStore,
    private val outboxRepository: OutboxRepository,
    private val remote: OutboxRemote,
    private val notifier: SyncNotifier,
    private val reconciler: MealReconciler,
    private val mealApi: MealApi,
    private val errorTranslator: ErrorTranslator = ErrorTranslator(),
) : OutboxProcessor {
    override suspend fun processOnce(): OutboxProcessResult {
        var processedCount = 0
        var transientFailureCount = 0
        queueStore.queued().forEach { item ->
            processedCount += 1
            if (processItem(item) == ItemProcessResult.TransientFailure) {
                transientFailureCount += 1
            }
        }
        return OutboxProcessResult(processedCount, transientFailureCount)
    }

    private suspend fun processItem(item: OutboxItem): ItemProcessResult {
        try {
            when (val kind = item.kind) {
                is OutboxKind.CapturedMeal -> processCapturedMeal(item, kind)
                is OutboxKind.CopyMealItemWeight -> sendMutation(item) { remote.copyMealItemWeight(kind) }
                is OutboxKind.CreateMeal -> processCreateMeal(item, kind)
                is OutboxKind.EditMeal -> sendMutation(item) { remote.editMeal(kind) }
                is OutboxKind.DeleteMeal -> sendMutation(item) { remote.deleteMeal(kind) }
                is OutboxKind.PatchMealItem -> sendMutation(item) { remote.patchMealItem(kind) }
                else -> sendMutation(item) { remote.processFlavorKind(kind) }
            }
        } catch (cancellation: CancellationException) {
            throw cancellation
        } catch (alreadySynced: OutboxAlreadySyncedException) {
            outboxRepository.markConfirmed(item.id, alreadySynced.serverId)
        } catch (conflict: OutboxConflictException) {
            markStuck(item, errorTranslator.translate(OutboxHttpException(409, "Conflict")))
        } catch (http: OutboxHttpException) {
            val userError = errorTranslator.translate(http)
            if (http.status in 400..499) {
                markStuck(item, userError)
            } else {
                handleTransientFailure(item, userError)
                return ItemProcessResult.TransientFailure
            }
        } catch (throwable: Throwable) {
            handleTransientFailure(item, errorTranslator.translate(throwable))
            return ItemProcessResult.TransientFailure
        }
        return ItemProcessResult.Done
    }

    private suspend fun processCapturedMeal(
        item: OutboxItem,
        kind: OutboxKind.CapturedMeal,
    ) {
        val key = kind.idempotencyKey
        if (key != null) {
            val existing = runCatching { mealApi.getByIdempotencyKey(key) }.getOrNull()
            if (existing != null) {
                reconciler.reconcileByKey(key, existing.id.toString())
                outboxRepository.markConfirmed(item.id, existing.id.toString())
                return
            }
        }
        outboxRepository.markUploading(item.id)
        val serverId = remote.captureMeal(kind)
        outboxRepository.markConfirmed(item.id, serverId)
    }

    private suspend fun processCreateMeal(
        item: OutboxItem,
        kind: OutboxKind.CreateMeal,
    ) {
        val key = kind.idempotencyKey
        if (key != null) {
            val existing = runCatching { mealApi.getByIdempotencyKey(key) }.getOrNull()
            if (existing != null) {
                reconciler.reconcileByKey(key, existing.id.toString())
                outboxRepository.markConfirmed(item.id, existing.id.toString())
                return
            }
        }
        sendMutation(item) { remote.createMeal(kind) }
    }

    private suspend fun sendMutation(
        item: OutboxItem,
        send: suspend () -> String,
    ) {
        outboxRepository.markUploading(item.id)
        val serverId = send()
        outboxRepository.markConfirmed(item.id, serverId)
    }

    private suspend fun handleTransientFailure(item: OutboxItem, userError: com.local.glucotracker.domain.model.UserError) {
        val attemptsAfterThisRun = item.attempts + 1
        if (attemptsAfterThisRun >= MaxAttempts) {
            markStuck(item, userError)
            return
        }
        queueStore.requeue(
            id = item.id,
            nextAttemptAt = Clock.System.now() + backoffFor(attemptsAfterThisRun),
            errorCode = userError.code,
            errorMessage = userError.message,
        )
    }

    private suspend fun markStuck(
        item: OutboxItem,
        userError: com.local.glucotracker.domain.model.UserError,
    ) {
        outboxRepository.markStuck(item.id, userError.code, userError.message)
        notifier.notifyOutboxStuck()
    }
}

interface OutboxQueueStore {
    suspend fun queued(): List<OutboxItem>
    suspend fun requeue(id: String, nextAttemptAt: Instant?, errorCode: String?, errorMessage: String?)
}

@Singleton
class RoomOutboxQueueStore @Inject constructor(
    private val database: GlucotrackerDatabase,
    private val outboxDao: OutboxDao,
) : OutboxQueueStore {
    override suspend fun queued(): List<OutboxItem> =
        Clock.System.now().let { now ->
            outboxDao.markTimedOutActiveRows(
                staleBefore = now - ActiveRowWatchdogDelay,
                now = now,
                errorCode = WatchdogErrorCode,
            )
            outboxDao.retryableItems(
                now = now,
                staleBefore = now - InFlightRecoveryDelay,
            )
        }
            .map { it.toDomain() }
            .sortedWith(compareBy<OutboxItem> { it.kind.queuePriority() }.thenBy { it.createdAt })

    override suspend fun requeue(
        id: String,
        nextAttemptAt: Instant?,
        errorCode: String?,
        errorMessage: String?,
    ) {
        database.withTransaction {
            outboxDao.markQueuedForRetry(
                id = id,
                nextAttemptAt = nextAttemptAt,
                errorMessage = errorMessage,
                queuedAt = Clock.System.now(),
                lastErrorCode = errorCode,
                lastErrorMessage = errorMessage,
            )
        }
    }
}

private fun OutboxKind.queuePriority(): Int =
    when (this) {
        is OutboxKind.CreateMeal,
        is OutboxKind.EditMeal,
        is OutboxKind.DeleteMeal,
        is OutboxKind.PatchMealItem,
        is OutboxKind.CopyMealItemWeight,
        -> 1
        is OutboxKind.CapturedMeal -> 2
        else -> 1
    }

private enum class ItemProcessResult {
    Done,
    TransientFailure,
}

private val InFlightRecoveryDelay = 2.minutes
private val ActiveRowWatchdogDelay = 12.minutes
private const val WatchdogErrorCode = "sync_timeout"
private const val MaxAttempts = 5

private fun backoffFor(attempts: Int) =
    when (attempts.coerceAtLeast(1)) {
        1 -> 1.minutes
        2 -> 2.minutes
        3 -> 4.minutes
        4 -> 8.minutes
        else -> 16.minutes
    }
