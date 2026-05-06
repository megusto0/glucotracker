package com.local.glucotracker.data.sync

import com.local.glucotracker.data.api.PhotoUploadClient
import com.local.glucotracker.domain.model.MealDraft
import com.local.glucotracker.domain.model.MealItemPayload
import com.local.glucotracker.domain.model.MealPatchPayload
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.generated.api.MealsApi
import com.local.glucotracker.generated.api.PhotosApi
import com.local.glucotracker.generated.infrastructure.HttpResponse
import com.local.glucotracker.generated.model.EstimateMealRequest
import com.local.glucotracker.generated.model.FingerstickReadingCreate
import com.local.glucotracker.generated.model.ItemSourceKind
import com.local.glucotracker.generated.model.MealAcceptRequest
import com.local.glucotracker.generated.model.MealCreate
import com.local.glucotracker.generated.model.MealItemCreate
import com.local.glucotracker.generated.model.MealItemPatch
import com.local.glucotracker.generated.model.MealItemResponse
import com.local.glucotracker.generated.model.MealItemWeightReuseRequest
import com.local.glucotracker.generated.model.MealPatch
import com.local.glucotracker.generated.model.MealResponse
import com.local.glucotracker.generated.model.MealSource
import com.local.glucotracker.generated.model.MealStatus
import java.io.IOException
import java.math.BigDecimal
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.math.abs
import kotlinx.datetime.Instant

class OutboxConflictException(message: String? = null) : IOException(message ?: "Conflict")
class OutboxAlreadySyncedException(val serverId: String) : IOException("Already synced")

interface OutboxRemote {
    suspend fun createMeal(kind: OutboxKind.CreateMeal): String
    suspend fun editMeal(kind: OutboxKind.EditMeal): String
    suspend fun deleteMeal(kind: OutboxKind.DeleteMeal): String
    suspend fun patchMealItem(kind: OutboxKind.PatchMealItem): String
    suspend fun copyMealItemWeight(kind: OutboxKind.CopyMealItemWeight): String
    suspend fun createFingerstick(kind: OutboxKind.CreateFingerstick): String
    suspend fun requestPhotoEstimate(kind: OutboxKind.PhotoEstimateRequest): String
    suspend fun acceptDraft(kind: OutboxKind.AcceptDraft): String
}

@Singleton
class KtorOutboxRemote @Inject constructor(
    private val mealsApi: MealsApi,
    private val glucoseApi: com.local.glucotracker.generated.api.GlucoseApi,
    private val photosApi: PhotosApi,
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
        mealsApi.deleteMeal(UUID.fromString(kind.serverId)).bodyOrThrow()
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

    override suspend fun createFingerstick(kind: OutboxKind.CreateFingerstick): String {
        val reading = glucoseApi.createFingerstick(
            FingerstickReadingCreate(
                glucoseMmolL = kind.glucoseMmolL.toBigDecimal(),
                measuredAt = kind.measuredAt,
                meterName = kind.meterName,
                notes = kind.notes,
            ),
        ).bodyOrThrow()
        return reading.id.toString()
    }

    override suspend fun requestPhotoEstimate(kind: OutboxKind.PhotoEstimateRequest): String {
        val existingMeal = findExistingPhotoMeal(kind)
        if (existingMeal?.status == MealStatus.ACCEPTED) {
            return existingMeal.id.toString()
        }
        if (existingMeal != null && !existingMeal.items.isNullOrEmpty()) {
            val accepted = mealsApi.acceptMealDraft(
                mealId = existingMeal.id,
                mealAcceptRequest = MealAcceptRequest(
                    items = existingMeal.items.map { it.toPayload().toGenerated() },
                ),
            ).bodyOrThrow()
            return accepted.id.toString()
        }

        val draftMeal = existingMeal ?: mealsApi.createMeal(
            MealCreate(
                source = MealSource.PHOTO,
                eatenAt = kind.capturedAt,
                status = MealStatus.DRAFT,
                title = null,
                note = null,
                items = null,
            ),
        ).bodyOrThrow()

        photoUploadClient.uploadMealPhoto(draftMeal.id, kind.localPhotoPath)
        val estimate = photosApi.estimateAndSaveMealDraft(
            mealId = draftMeal.id,
            estimateMealRequest = EstimateMealRequest(),
        ).bodyOrThrow()

        val createdDraft = estimate.createdDrafts?.firstOrNull()
        val mealId = createdDraft?.mealId ?: estimate.mealId
        val current = mealsApi.getMeal(mealId).bodyOrThrow()
        if (current.status == MealStatus.ACCEPTED) {
            return current.id.toString()
        }
        val finalItems = createdDraft?.item?.let { listOf(it) }
            ?: current.items.orEmpty().map { it.toPayload().toGenerated() }
                .ifEmpty { estimate.suggestedItems }
        if (finalItems.isEmpty()) {
            throw IOException("Photo estimate produced no items.")
        }
        val accepted = mealsApi.acceptMealDraft(
            mealId = mealId,
            mealAcceptRequest = MealAcceptRequest(items = finalItems),
        ).bodyOrThrow()
        return accepted.id.toString()
    }

    override suspend fun acceptDraft(kind: OutboxKind.AcceptDraft): String {
        val mealId = UUID.fromString(kind.estimateId)
        val current = mealsApi.getMeal(mealId).bodyOrThrow()
        if (current.status == MealStatus.ACCEPTED) {
            return current.id.toString()
        }
        val finalItems = kind.items.ifEmpty {
            current.items?.map { it.toPayload() }.orEmpty()
        }.map { it.toGenerated() }
        if (finalItems.isEmpty()) {
            throw IOException("Draft has no items to accept.")
        }
        mealsApi.patchMeal(
            mealId = mealId,
            mealPatch = MealPatch(eatenAt = kind.eatenAt),
        ).bodyOrThrow()
        val accepted = mealsApi.acceptMealDraft(
            mealId = mealId,
            mealAcceptRequest = MealAcceptRequest(items = finalItems),
        ).bodyOrThrow()
        return accepted.id.toString()
    }

    private suspend fun findExistingPhotoMeal(kind: OutboxKind.PhotoEstimateRequest): MealResponse? {
        val capturedAtMillis = kind.capturedAt.toEpochMilliseconds()
        val response = mealsApi.listMeals(
            from = kind.capturedAt.shiftMillis(-36 * 60 * 60 * 1_000L),
            to = kind.capturedAt.shiftMillis(36 * 60 * 60 * 1_000L),
            limit = 50,
            offset = 0,
            q = null,
            status = null,
        ).bodyOrThrow()
        return response.items
            .filter { meal -> meal.source == MealSource.PHOTO }
            .minByOrNull { meal -> abs(meal.eatenAt.toEpochMilliseconds() - capturedAtMillis) }
            ?.takeIf { meal -> abs(meal.eatenAt.toEpochMilliseconds() - capturedAtMillis) <= 30_000L }
    }
}

private suspend fun <T : Any> HttpResponse<T>.bodyOrThrow(): T {
    if (status == 409) throw OutboxConflictException()
    if (!success) throw IOException("HTTP $status")
    return body()
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

private fun MealItemCreate.toPayload(): MealItemPayload =
    MealItemPayload(
        name = name,
        brand = brand,
        grams = grams?.toDouble(),
        kcal = kcal?.toDouble(),
        carbsG = carbsG?.toDouble(),
        proteinG = proteinG?.toDouble(),
        fatG = fatG?.toDouble(),
        fiberG = fiberG?.toDouble(),
        sourceKind = sourceKind?.value,
        servingText = servingText,
        confidence = confidence?.toDouble(),
        confidenceReason = confidenceReason,
        calculationMethod = calculationMethod,
        patternId = patternId?.toString(),
        productId = productId?.toString(),
        photoId = photoId?.toString(),
        position = position,
    )

private fun MealItemResponse.toPayload(): MealItemPayload =
    MealItemPayload(
        name = name,
        brand = brand,
        grams = grams?.toDouble(),
        kcal = kcal?.toDouble(),
        carbsG = carbsG?.toDouble(),
        proteinG = proteinG?.toDouble(),
        fatG = fatG?.toDouble(),
        fiberG = fiberG?.toDouble(),
        sourceKind = sourceKind?.value,
        servingText = servingText,
        confidence = confidence?.toDouble(),
        confidenceReason = confidenceReason,
        calculationMethod = calculationMethod,
        patternId = patternId?.toString(),
        productId = productId?.toString(),
        photoId = photoId?.toString(),
        position = position,
    )

private fun MealResponse.toDraft(localPhotoPath: String?): MealDraft =
    MealDraft(
        id = id.toString(),
        eatenAt = eatenAt,
        title = title,
        note = note,
        localPhotoPath = localPhotoPath,
        totalKcal = totalKcal.toDouble(),
        totalCarbsG = totalCarbsG.toDouble(),
        totalProteinG = totalProteinG.toDouble(),
        totalFatG = totalFatG.toDouble(),
        totalFiberG = totalFiberG.toDouble(),
        items = items?.map { it.toPayload() }.orEmpty(),
    )

private fun String.toMealSource(): MealSource =
    MealSource.decode(this) ?: MealSource.MANUAL

private fun String.toItemSourceKind(): ItemSourceKind? =
    ItemSourceKind.decode(this)

private fun String.toUuidOrNull(): UUID? =
    runCatching { UUID.fromString(this) }.getOrNull()

private fun Double.toBigDecimal(): BigDecimal =
    BigDecimal.valueOf(this)

private fun Instant.shiftMillis(delta: Long): Instant =
    Instant.fromEpochMilliseconds(toEpochMilliseconds() + delta)
