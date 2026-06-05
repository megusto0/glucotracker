package com.local.glucotracker.data.sync

import com.local.glucotracker.data.api.PhotoUploadClient
import com.local.glucotracker.data.api.PhotoCaptureResponse
import com.local.glucotracker.domain.model.MealItemPayload
import com.local.glucotracker.domain.model.MealPatchPayload
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.generated.api.MealsApi
import com.local.glucotracker.generated.api.PhotosApi
import com.local.glucotracker.generated.infrastructure.HttpResponse
import com.local.glucotracker.generated.model.ItemSourceKind
import com.local.glucotracker.generated.model.MealCreate
import com.local.glucotracker.generated.model.MealItemCreate
import com.local.glucotracker.generated.model.MealItemPatch
import com.local.glucotracker.generated.model.MealItemWeightReuseRequest
import com.local.glucotracker.generated.model.MealPatch
import com.local.glucotracker.generated.model.MealSource
import com.local.glucotracker.generated.model.MealStatus
import java.io.IOException
import java.math.BigDecimal
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

class OutboxConflictException(message: String? = null) : IOException(message ?: "Conflict")
class OutboxAlreadySyncedException(val serverId: String) : IOException("Already synced")
class OutboxHttpException(
    val status: Int,
    message: String,
) : IOException(message)

interface OutboxRemote {
    suspend fun createMeal(kind: OutboxKind.CreateMeal): String
    suspend fun editMeal(kind: OutboxKind.EditMeal): String
    suspend fun deleteMeal(kind: OutboxKind.DeleteMeal): String
    suspend fun patchMealItem(kind: OutboxKind.PatchMealItem): String
    suspend fun copyMealItemWeight(kind: OutboxKind.CopyMealItemWeight): String
    suspend fun captureMeal(kind: OutboxKind.CapturedMeal): PhotoCaptureResponse
    suspend fun processFlavorKind(kind: OutboxKind): String
}

@Singleton
class KtorOutboxRemote @Inject constructor(
    private val mealsApi: MealsApi,
    @Suppress("unused") private val photosApi: PhotosApi,
    private val photoUploadClient: PhotoUploadClient,
) : OutboxRemote {
    override suspend fun createMeal(kind: OutboxKind.CreateMeal): String {
        val meal = mealsApi.createMeal(
            MealCreate(
                source = kind.source.toMealSource(),
                eatenAt = kind.eatenAt,
                status = MealStatus.ACCEPTED,
                title = kind.payload.title,
                note = kind.payload.note,
                items = kind.items.map { it.toGenerated() }.ifEmpty { null },
                idempotencyKey = kind.idempotencyKey,
            ),
        ).bodyOrThrow()
        return meal.id.toString()
    }

    override suspend fun editMeal(kind: OutboxKind.EditMeal): String {
        val meal = mealsApi.patchMeal(
            mealId = UUID.fromString(kind.serverId),
            mealPatch = kind.patch.toGenerated(),
        ).bodyOrThrow()
        return meal.id.toString()
    }

    override suspend fun deleteMeal(kind: OutboxKind.DeleteMeal): String {
        mealsApi.deleteMeal(UUID.fromString(kind.serverId)).ensureSuccess(404)
        return kind.serverId
    }

    override suspend fun patchMealItem(kind: OutboxKind.PatchMealItem): String {
        mealsApi.patchMealItem(
            itemId = UUID.fromString(kind.itemId),
            mealItemPatch = kind.patch.toGenerated(),
        ).bodyOrThrow()
        return kind.mealId
    }

    override suspend fun copyMealItemWeight(kind: OutboxKind.CopyMealItemWeight): String {
        val meal = mealsApi.createMealFromMealItemWeight(
            itemId = UUID.fromString(kind.itemId),
            mealItemWeightReuseRequest = MealItemWeightReuseRequest(
                grams = kind.grams.toBigDecimal(),
                eatenAt = kind.eatenAt,
            ),
        ).bodyOrThrow()
        return meal.id.toString()
    }

    override suspend fun captureMeal(kind: OutboxKind.CapturedMeal): PhotoCaptureResponse {
        val path = kind.localPhotoPath ?: throw IOException("Captured meal has no local photo")
        return photoUploadClient.createMealFromPhoto(
            localPhotoPath = path,
            capturedAt = kind.capturedAt,
            source = kind.source,
            idempotencyKey = kind.captureIdempotencyKey(),
            context = kind.optimisticName,
        )
    }

    override suspend fun processFlavorKind(kind: OutboxKind): String {
        throw IOException("Unsupported outbox kind: ${kind::class.simpleName}")
    }

    private fun OutboxKind.CapturedMeal.captureIdempotencyKey(): String =
        idempotencyKey ?: UUID.nameUUIDFromBytes(
            "${localPhotoPath.orEmpty()}|$capturedAt|$source".toByteArray(),
        ).toString()
}

internal suspend fun <T : Any> HttpResponse<T>.bodyOrThrow(): T {
    if (status == 409) throw OutboxConflictException()
    if (!success) throw OutboxHttpException(status, "HTTP $status")
    return body()
}

internal suspend fun <T : Any> HttpResponse<T>.ensureSuccess(vararg successStatuses: Int) {
    if (status == 409) throw OutboxConflictException()
    if (!success && status !in successStatuses) {
        throw OutboxHttpException(status, "HTTP $status")
    }
}

private fun MealPatchPayload.toGenerated(): MealPatch =
    MealPatch(
        eatenAt = eatenAt,
        note = note,
        title = title,
        status = null,
    )

private fun com.local.glucotracker.domain.model.MealItemPatchPayload.toGenerated(): MealItemPatch =
    MealItemPatch(
        name = name,
        grams = grams?.toBigDecimal(),
        kcal = kcal?.toBigDecimal(),
        carbsG = carbsG?.toBigDecimal(),
        proteinG = proteinG?.toBigDecimal(),
        fatG = fatG?.toBigDecimal(),
        fiberG = fiberG?.toBigDecimal(),
    )

private fun MealItemPayload.toGenerated(): MealItemCreate =
    MealItemCreate(
        name = name,
        brand = brand,
        grams = grams?.toBigDecimal(),
        kcal = kcal?.toBigDecimal(),
        carbsG = carbsG?.toBigDecimal(),
        proteinG = proteinG?.toBigDecimal(),
        fatG = fatG?.toBigDecimal(),
        fiberG = fiberG?.toBigDecimal(),
        sourceKind = sourceKind?.toItemSourceKind(),
        servingText = servingText,
        confidence = confidence?.toBigDecimal(),
        confidenceReason = confidenceReason,
        calculationMethod = calculationMethod,
        patternId = patternId?.toUuidOrNull(),
        productId = productId?.toUuidOrNull(),
        photoId = photoId?.toUuidOrNull(),
        position = position,
    )

private fun String.toMealSource(): MealSource =
    MealSource.decode(this) ?: MealSource.MANUAL

private fun String.toItemSourceKind(): ItemSourceKind? =
    ItemSourceKind.decode(this)

private fun String.toUuidOrNull(): UUID? =
    runCatching { UUID.fromString(this) }.getOrNull()

internal fun Double.toBigDecimal(): BigDecimal =
    BigDecimal.valueOf(this)
