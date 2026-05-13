package com.local.glucotracker.ui.format

import com.local.glucotracker.domain.model.Meal
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant
import kotlin.math.roundToInt
import kotlin.time.Duration.Companion.seconds

enum class PhotoProcessingStage {
    Captured,
    WaitingUpload,
    Uploading,
    Estimating,
    Done,
    Stuck,
}

enum class PhotoProcessingFailureStep {
    Upload,
    Estimate,
}

data class PhotoProcessingUiState(
    val stage: PhotoProcessingStage,
    val title: String,
    val statusText: String,
    val helperText: String?,
    val queuePositionText: String?,
    val uploadProgress: Float?,
    val estimateElapsedSeconds: Int?,
    val estimateDeadlineSeconds: Int?,
    val canRetry: Boolean,
    val failureStep: PhotoProcessingFailureStep? = null,
)

const val PhotoEstimateDeadlineSeconds: Int = 90

fun mapOutboxAndMealToPhotoProcessingUiState(
    outboxItem: OutboxItem,
    queuePosition: Int? = null,
    queueSize: Int? = null,
    uploadProgress: Float? = null,
): PhotoProcessingUiState? {
    if (outboxItem.kind !is OutboxKind.CapturedMeal) return null
    val queueText = queuePositionText(queuePosition, queueSize)
    return when (outboxItem.state) {
        OutboxState.Queued -> PhotoProcessingUiState(
            stage = PhotoProcessingStage.WaitingUpload,
            title = "Фото",
            statusText = listOfNotNull("ждёт отправки", queueText).joinToString(" · "),
            helperText = "начнём после предыдущих фото",
            queuePositionText = queueText,
            uploadProgress = null,
            estimateElapsedSeconds = null,
            estimateDeadlineSeconds = null,
            canRetry = false,
        )
        OutboxState.Uploading -> {
            val safeProgress = uploadProgress?.coerceIn(0f, 1f)
            PhotoProcessingUiState(
                stage = PhotoProcessingStage.Uploading,
                title = "Фото",
                statusText = safeProgress?.let { "отправляем фото · ${(it * 100).roundToInt()}%" }
                    ?: "отправляем фото",
                helperText = null,
                queuePositionText = queueText,
                uploadProgress = safeProgress,
                estimateElapsedSeconds = null,
                estimateDeadlineSeconds = null,
                canRetry = false,
            )
        }
        OutboxState.Confirmed -> PhotoProcessingUiState(
            stage = PhotoProcessingStage.Done,
            title = "Фото",
            statusText = "оценка готова",
            helperText = null,
            queuePositionText = queueText,
            uploadProgress = null,
            estimateElapsedSeconds = null,
            estimateDeadlineSeconds = null,
            canRetry = false,
        )
        OutboxState.Stuck -> PhotoProcessingUiState(
            stage = PhotoProcessingStage.Stuck,
            title = "Фото",
            statusText = "не отправилось · повторить",
            helperText = "проверьте сеть или повторите отправку",
            queuePositionText = queueText,
            uploadProgress = null,
            estimateElapsedSeconds = null,
            estimateDeadlineSeconds = null,
            canRetry = true,
            failureStep = PhotoProcessingFailureStep.Upload,
        )
    }
}

fun mapOutboxAndMealToPhotoProcessingUiState(
    meal: Meal,
    estimateStartedAt: Instant? = null,
    now: Instant = Clock.System.now(),
): PhotoProcessingUiState? {
    if (!meal.isPhotoSource()) return null
    if (meal.status.equals("accepted", ignoreCase = true)) return null
    val status = meal.estimateStatus?.lowercase()
    return when (status) {
        "estimating" -> estimatingState(
            estimateStartedAt = estimateStartedAt,
            now = now,
        )
        "failed",
        "timeout",
        "error",
        -> estimateStuckState()
        else -> PhotoProcessingUiState(
            stage = PhotoProcessingStage.Captured,
            title = "Фото",
            statusText = "фото сохранено",
            helperText = "оценка ещё не началась",
            queuePositionText = null,
            uploadProgress = null,
            estimateElapsedSeconds = null,
            estimateDeadlineSeconds = null,
            canRetry = false,
        )
    }
}

fun estimatingState(
    estimateStartedAt: Instant?,
    now: Instant = Clock.System.now(),
): PhotoProcessingUiState {
    val elapsed = estimateStartedAt?.let { (now - it).inWholeSeconds.coerceAtLeast(0).toInt() }
    val remaining = elapsed?.let { (PhotoEstimateDeadlineSeconds.seconds - it.seconds).inWholeSeconds.toInt() }
        ?.coerceAtLeast(0)
    if (remaining == 0) return estimateStuckState()
    val statusText = remaining?.let { "модель оценивает · осталось до $it сек" }
        ?: "модель оценивает · обычно до 90 сек"
    return PhotoProcessingUiState(
        stage = PhotoProcessingStage.Estimating,
        title = "Фото",
        statusText = statusText,
        helperText = null,
        queuePositionText = null,
        uploadProgress = null,
        estimateElapsedSeconds = elapsed,
        estimateDeadlineSeconds = PhotoEstimateDeadlineSeconds,
        canRetry = false,
    )
}

fun estimateStuckState(): PhotoProcessingUiState =
    PhotoProcessingUiState(
        stage = PhotoProcessingStage.Stuck,
        title = "Фото",
        statusText = "оценка не пришла · можно повторить",
        helperText = "откройте очередь, чтобы повторить",
        queuePositionText = null,
        uploadProgress = null,
        estimateElapsedSeconds = null,
        estimateDeadlineSeconds = PhotoEstimateDeadlineSeconds,
        canRetry = true,
        failureStep = PhotoProcessingFailureStep.Estimate,
    )

private fun queuePositionText(position: Int?, size: Int?): String? =
    if (position != null && size != null && position > 0 && size > 0) {
        "очередь $position из $size"
    } else {
        null
    }

private fun Meal.isPhotoSource(): Boolean =
    source.lowercase() in setOf("photo", "photo_estimate", "gallery")
