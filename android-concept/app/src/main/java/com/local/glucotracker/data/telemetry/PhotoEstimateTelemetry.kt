package com.local.glucotracker.data.telemetry

import android.os.Build
import androidx.room.withTransaction
import com.local.glucotracker.BuildConfig
import com.local.glucotracker.data.api.MealApi
import com.local.glucotracker.data.api.OpenApiJson
import com.local.glucotracker.data.local.CachedMealDao
import com.local.glucotracker.data.local.GlucotrackerDatabase
import com.local.glucotracker.data.local.PhotoEstimateLogDao
import com.local.glucotracker.data.local.PhotoEstimateLogEntity
import com.local.glucotracker.data.mapper.toCachedEntity
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.generated.model.MealResponse
import com.local.glucotracker.generated.model.MealStatus
import io.ktor.client.HttpClient
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.contentType
import java.io.IOException
import java.util.UUID
import javax.inject.Inject
import javax.inject.Named
import javax.inject.Singleton
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import kotlin.time.Duration.Companion.days
import kotlin.time.Duration.Companion.seconds

@Singleton
class PhotoEstimateTelemetryLogger @Inject constructor(
    private val dao: PhotoEstimateLogDao,
) {
    suspend fun captureQueued(outboxId: String, kind: OutboxKind.CapturedMeal) {
        record(
            item = null,
            kind = kind,
            outboxId = outboxId,
            eventType = "capture_queued",
            detail = buildJsonObject {
                put("has_context", !kind.optimisticName.isNullOrBlank())
                put("has_weight_hint", kind.optimisticWeightG != null)
            },
        )
    }

    suspend fun uploadStarted(item: OutboxItem, kind: OutboxKind.CapturedMeal, attempt: Int) {
        val now = Clock.System.now()
        record(
            item = item,
            kind = kind,
            eventType = "upload_started",
            eventAt = now,
            attempt = attempt,
            queuedDelayMs = elapsedMs(item.createdAt, now),
            detail = buildJsonObject {
                put("queued_state", item.state.name)
            },
        )
    }

    suspend fun uploadAccepted(
        item: OutboxItem,
        kind: OutboxKind.CapturedMeal,
        serverMealId: String,
        estimateStatus: String,
        attempt: Int,
        uploadStartedAt: Instant,
    ) {
        val now = Clock.System.now()
        record(
            item = item,
            kind = kind,
            eventType = "upload_accepted",
            eventAt = now,
            serverMealId = serverMealId,
            estimateStatus = estimateStatus,
            attempt = attempt,
            uploadDurationMs = elapsedMs(uploadStartedAt, now),
            detail = buildJsonObject {
                put("server_status", estimateStatus)
            },
        )
    }

    suspend fun estimateDelayed(
        item: OutboxItem,
        kind: OutboxKind.CapturedMeal,
        serverMealId: String,
        estimateStatus: String?,
        pollCount: Int,
    ) {
        record(
            item = item,
            kind = kind,
            eventType = "estimate_delayed",
            serverMealId = serverMealId,
            estimateStatus = estimateStatus,
            detail = buildJsonObject {
                put("poll_count", pollCount)
            },
        )
    }

    suspend fun estimateVisible(
        item: OutboxItem,
        kind: OutboxKind.CapturedMeal,
        result: PhotoEstimateVisibilityResult.Visible,
    ) {
        record(
            item = item,
            kind = kind,
            eventType = "estimate_visible",
            eventAt = result.visibleAt,
            serverMealId = result.serverMealId,
            estimateStatus = result.estimateStatus,
            detail = buildJsonObject {
                put("poll_count", result.pollCount)
                put("item_count", result.itemCount)
                put("total_kcal", result.totalKcal)
                put("total_carbs_g", result.totalCarbsG)
                put("total_protein_g", result.totalProteinG)
                put("total_fat_g", result.totalFatG)
            },
        )
    }

    suspend fun estimateFailed(
        item: OutboxItem,
        kind: OutboxKind.CapturedMeal,
        serverMealId: String?,
        estimateStatus: String?,
        errorCode: String,
        errorMessage: String?,
    ) {
        record(
            item = item,
            kind = kind,
            eventType = "estimate_failed",
            serverMealId = serverMealId,
            estimateStatus = estimateStatus,
            errorCode = errorCode,
            errorMessage = errorMessage,
        )
    }

    suspend fun retryScheduled(
        item: OutboxItem,
        errorCode: String,
        errorMessage: String?,
        nextAttemptAt: Instant?,
    ) {
        val kind = item.kind as? OutboxKind.CapturedMeal ?: return
        val now = Clock.System.now()
        record(
            item = item,
            kind = kind,
            eventType = "retry_scheduled",
            eventAt = now,
            attempt = item.attempts + 1,
            retryDelayMs = nextAttemptAt?.let { elapsedMs(now, it) },
            errorCode = errorCode,
            errorMessage = errorMessage,
        )
    }

    suspend fun stuck(item: OutboxItem, errorCode: String, errorMessage: String?) {
        val kind = item.kind as? OutboxKind.CapturedMeal ?: return
        record(
            item = item,
            kind = kind,
            eventType = "pipeline_stuck",
            attempt = item.attempts + 1,
            errorCode = errorCode,
            errorMessage = errorMessage,
        )
    }

    suspend fun workerError(item: OutboxItem, throwable: Throwable) {
        val kind = item.kind as? OutboxKind.CapturedMeal ?: return
        record(
            item = item,
            kind = kind,
            eventType = "pipeline_error",
            attempt = item.attempts + 1,
            errorCode = throwable::class.simpleName ?: "error",
            errorMessage = throwable.message,
        )
    }

    private suspend fun record(
        item: OutboxItem?,
        kind: OutboxKind.CapturedMeal,
        eventType: String,
        eventAt: Instant = Clock.System.now(),
        outboxId: String? = item?.id,
        serverMealId: String? = null,
        estimateStatus: String? = null,
        attempt: Int? = null,
        queuedDelayMs: Long? = null,
        uploadDurationMs: Long? = null,
        retryDelayMs: Long? = null,
        httpStatus: Int? = null,
        errorCode: String? = null,
        errorMessage: String? = null,
        detail: JsonObject = JsonObject(emptyMap()),
    ) {
        runCatching {
            dao.insert(
                PhotoEstimateLogEntity(
                    id = UUID.randomUUID().toString(),
                    traceId = kind.traceId(outboxId),
                    outboxId = outboxId,
                    idempotencyKey = kind.idempotencyKey,
                    source = kind.source,
                    eventType = eventType,
                    eventAt = eventAt,
                    capturedAt = kind.capturedAt,
                    serverMealId = serverMealId,
                    estimateStatus = estimateStatus,
                    attempt = attempt,
                    totalElapsedMs = elapsedMs(kind.capturedAt, eventAt),
                    queuedDelayMs = queuedDelayMs,
                    uploadDurationMs = uploadDurationMs,
                    retryDelayMs = retryDelayMs,
                    httpStatus = httpStatus,
                    errorCode = errorCode,
                    errorMessage = errorMessage?.sanitizeForTelemetry(),
                    detailJson = OpenApiJson.json.encodeToString(detail),
                    sentAt = null,
                ),
            )
        }
    }
}

class PhotoEstimateFailedException(
    val serverMealId: String,
    val estimateStatus: String?,
    message: String?,
) : IOException(message ?: "Photo estimate failed")

class PhotoEstimateVisibilityTimeoutException(serverMealId: String) :
    IOException("Photo estimate was not visible before timeout for meal $serverMealId")

sealed interface PhotoEstimateVisibilityResult {
    data class Visible(
        val serverMealId: String,
        val estimateStatus: String?,
        val visibleAt: Instant,
        val pollCount: Int,
        val itemCount: Int,
        val totalKcal: Double,
        val totalCarbsG: Double,
        val totalProteinG: Double,
        val totalFatG: Double,
    ) : PhotoEstimateVisibilityResult
}

@Singleton
class PhotoEstimateVisibilityTracker @Inject constructor(
    private val database: GlucotrackerDatabase,
    private val mealDao: CachedMealDao,
    private val mealApi: MealApi,
    private val telemetryLogger: PhotoEstimateTelemetryLogger,
    @Named("apiBaseUrl") private val baseUrl: String,
) {
    suspend fun waitUntilVisible(
        item: OutboxItem,
        kind: OutboxKind.CapturedMeal,
        serverMealId: String,
    ): PhotoEstimateVisibilityResult.Visible {
        val deadline = Clock.System.now() + EstimateVisibleDeadline
        var pollCount = 0
        var delayLogged = false
        var lastStatus: String? = null

        while (Clock.System.now() < deadline) {
            pollCount += 1
            val meal = mealApi.getMeal(UUID.fromString(serverMealId))
            lastStatus = meal.estimateStatus
            if (meal.isVisibleEstimate()) {
                val visibleAt = Clock.System.now()
                database.withTransaction {
                    mealDao.upsertAll(
                        listOf(meal.toCachedEntity(fetchedAt = visibleAt, baseUrl = baseUrl)),
                    )
                }
                return meal.toVisibleResult(serverMealId, visibleAt, pollCount)
            }
            if (meal.isTerminalEstimateFailure()) {
                throw PhotoEstimateFailedException(
                    serverMealId = serverMealId,
                    estimateStatus = meal.estimateStatus,
                    message = meal.estimateError,
                )
            }
            if (!delayLogged && elapsedMs(kind.capturedAt, Clock.System.now()) >= EstimateDelayLogAfterMs) {
                telemetryLogger.estimateDelayed(
                    item = item,
                    kind = kind,
                    serverMealId = serverMealId,
                    estimateStatus = meal.estimateStatus,
                    pollCount = pollCount,
                )
                delayLogged = true
            }
            delay(EstimatePollInterval)
        }

        throw PhotoEstimateVisibilityTimeoutException(serverMealId).also {
            telemetryLogger.estimateFailed(
                item = item,
                kind = kind,
                serverMealId = serverMealId,
                estimateStatus = lastStatus,
                errorCode = "estimate_timeout",
                errorMessage = it.message,
            )
        }
    }
}

@Serializable
private data class MobilePhotoEstimateLogRequest(
    val events: List<MobilePhotoEstimateLogEvent>,
    @SerialName("client_sent_at")
    val clientSentAt: Instant,
)

@Serializable
private data class MobilePhotoEstimateLogEvent(
    @SerialName("event_id")
    val eventId: String,
    @SerialName("trace_id")
    val traceId: String,
    @SerialName("outbox_id")
    val outboxId: String?,
    @SerialName("idempotency_key")
    val idempotencyKey: String?,
    val source: String?,
    @SerialName("event_type")
    val eventType: String,
    @SerialName("event_at")
    val eventAt: Instant,
    @SerialName("captured_at")
    val capturedAt: Instant?,
    @SerialName("server_meal_id")
    val serverMealId: String?,
    @SerialName("estimate_status")
    val estimateStatus: String?,
    val attempt: Int?,
    @SerialName("total_elapsed_ms")
    val totalElapsedMs: Long?,
    @SerialName("queued_delay_ms")
    val queuedDelayMs: Long?,
    @SerialName("upload_duration_ms")
    val uploadDurationMs: Long?,
    @SerialName("retry_delay_ms")
    val retryDelayMs: Long?,
    @SerialName("http_status")
    val httpStatus: Int?,
    @SerialName("error_code")
    val errorCode: String?,
    @SerialName("error_message")
    val errorMessage: String?,
    @SerialName("app_flavor")
    val appFlavor: String,
    @SerialName("app_version")
    val appVersion: String,
    @SerialName("android_sdk")
    val androidSdk: Int,
    @SerialName("device_model")
    val deviceModel: String,
    val detail: JsonObject,
)

@Singleton
class PhotoEstimateTelemetryClient @Inject constructor(
    @Named("apiBaseUrl") private val baseUrl: String,
    private val client: HttpClient,
) {
    suspend fun submit(events: List<PhotoEstimateLogEntity>) {
        val response = client.post("$baseUrl/mobile/photo-estimate-logs") {
            contentType(ContentType.Application.Json)
            setBody(
                MobilePhotoEstimateLogRequest(
                    events = events.map { it.toRequestEvent() },
                    clientSentAt = Clock.System.now(),
                ),
            )
        }
        if (response.status.value !in 200..299) {
            throw IOException("Photo telemetry upload failed: HTTP ${response.status.value}")
        }
    }
}

data class PhotoEstimateTelemetryFlushResult(
    val attemptedCount: Int,
    val shouldRetry: Boolean,
)

@Singleton
class PhotoEstimateTelemetryFlusher @Inject constructor(
    private val dao: PhotoEstimateLogDao,
    private val client: PhotoEstimateTelemetryClient,
) {
    suspend fun flushOnce(): PhotoEstimateTelemetryFlushResult {
        val events = dao.pending(TelemetryBatchLimit)
        if (events.isEmpty()) return PhotoEstimateTelemetryFlushResult(0, shouldRetry = false)
        return try {
            client.submit(events)
            val now = Clock.System.now()
            dao.markSent(events.map { it.id }, now)
            dao.deleteSentBefore(now - SentRetention)
            PhotoEstimateTelemetryFlushResult(events.size, shouldRetry = false)
        } catch (cancellation: CancellationException) {
            throw cancellation
        } catch (_: Throwable) {
            PhotoEstimateTelemetryFlushResult(events.size, shouldRetry = true)
        }
    }
}

private fun PhotoEstimateLogEntity.toRequestEvent(): MobilePhotoEstimateLogEvent =
    MobilePhotoEstimateLogEvent(
        eventId = id,
        traceId = traceId,
        outboxId = outboxId,
        idempotencyKey = idempotencyKey,
        source = source,
        eventType = eventType,
        eventAt = eventAt,
        capturedAt = capturedAt,
        serverMealId = serverMealId,
        estimateStatus = estimateStatus,
        attempt = attempt,
        totalElapsedMs = totalElapsedMs,
        queuedDelayMs = queuedDelayMs,
        uploadDurationMs = uploadDurationMs,
        retryDelayMs = retryDelayMs,
        httpStatus = httpStatus,
        errorCode = errorCode,
        errorMessage = errorMessage,
        appFlavor = BuildConfig.FLAVOR,
        appVersion = BuildConfig.VERSION_NAME,
        androidSdk = Build.VERSION.SDK_INT,
        deviceModel = "${Build.MANUFACTURER} ${Build.MODEL}".take(120),
        detail = detailJson.toJsonObject(),
    )

private fun String?.toJsonObject(): JsonObject =
    if (isNullOrBlank()) {
        JsonObject(emptyMap())
    } else {
        runCatching { OpenApiJson.json.parseToJsonElement(this).jsonObject }.getOrNull()
            ?: JsonObject(emptyMap())
    }

private fun MealResponse.isVisibleEstimate(): Boolean =
    status == MealStatus.ACCEPTED && items?.isNotEmpty() == true

private fun MealResponse.isTerminalEstimateFailure(): Boolean =
    estimateStatus?.lowercase() in setOf("failed", "timeout", "error")

private fun MealResponse.toVisibleResult(
    serverMealId: String,
    visibleAt: Instant,
    pollCount: Int,
): PhotoEstimateVisibilityResult.Visible =
    PhotoEstimateVisibilityResult.Visible(
        serverMealId = serverMealId,
        estimateStatus = estimateStatus,
        visibleAt = visibleAt,
        pollCount = pollCount,
        itemCount = items?.size ?: 0,
        totalKcal = totalKcal.asDouble(),
        totalCarbsG = totalCarbsG.asDouble(),
        totalProteinG = totalProteinG.asDouble(),
        totalFatG = totalFatG.asDouble(),
    )

private fun OutboxKind.CapturedMeal.traceId(outboxId: String?): String =
    idempotencyKey ?: outboxId ?: UUID.nameUUIDFromBytes(
        "$capturedAt|$source|${optimisticName.orEmpty()}".toByteArray(),
    ).toString()

private fun elapsedMs(from: Instant, to: Instant): Long =
    (to - from).inWholeMilliseconds.coerceAtLeast(0)

private fun String.sanitizeForTelemetry(): String =
    replace(WindowsPathRegex, "[path]")
        .replace(UnixPathRegex, "[path]")
        .lineSequence()
        .joinToString(" ")
        .take(1000)

private fun Number?.asDouble(): Double =
    when (this) {
        null -> 0.0
        else -> toDouble()
    }

private val EstimatePollInterval = 2.seconds
private val EstimateVisibleDeadline = 90.seconds
private const val EstimateDelayLogAfterMs = 15_000L
private const val TelemetryBatchLimit = 50
private val SentRetention = 7.days
private val WindowsPathRegex = Regex("""[A-Za-z]:\\[^\s]+""")
private val UnixPathRegex = Regex("""/(?:[^/\s]+/)+[^/\s]+""")
