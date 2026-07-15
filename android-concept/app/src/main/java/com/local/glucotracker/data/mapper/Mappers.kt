package com.local.glucotracker.data.mapper

import com.local.glucotracker.data.api.OpenApiJson
import com.local.glucotracker.data.api.ApiConnection
import com.local.glucotracker.data.local.CachedDayTotalsEntity
import com.local.glucotracker.data.local.CachedMealEntity
import com.local.glucotracker.data.local.CachedProductEntity
import com.local.glucotracker.data.local.CachedTemplateEntity
import com.local.glucotracker.data.local.OutboxEntity
import com.local.glucotracker.domain.model.DayState
import com.local.glucotracker.domain.model.DayTotals
import com.local.glucotracker.domain.model.KpiSnapshot
import com.local.glucotracker.domain.model.Meal
import com.local.glucotracker.domain.model.MealDraft
import com.local.glucotracker.domain.model.MealItem
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.PostprandialPoint
import com.local.glucotracker.domain.model.PostprandialResponse
import com.local.glucotracker.domain.model.Product
import com.local.glucotracker.domain.model.Template
import com.local.glucotracker.generated.model.DashboardDayResponse
import com.local.glucotracker.generated.model.DashboardTodayResponse
import com.local.glucotracker.generated.model.DatabaseItemResponse
import com.local.glucotracker.generated.model.KcalBalanceDay
import com.local.glucotracker.generated.model.KcalBalanceResponse
import com.local.glucotracker.generated.model.MealItemResponse
import com.local.glucotracker.generated.model.MealResponse
import com.local.glucotracker.generated.model.PatternResponse
import com.local.glucotracker.generated.model.ProductResponse
import java.math.BigDecimal
import kotlinx.datetime.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive

private const val PackedListSeparator = "\u001F"

private fun BigDecimal?.asDouble(): Double? = this?.toDouble()
private fun BigDecimal.asDouble(): Double = toDouble()
private fun List<String>?.pack(): String = orEmpty().joinToString(PackedListSeparator)
private fun String.unpack(): List<String> = if (isBlank()) emptyList() else split(PackedListSeparator)

fun DashboardTodayResponse.toTotalsEntity(
    fetchedAt: Instant,
    balance: KcalBalanceResponse? = null,
): CachedDayTotalsEntity =
    CachedDayTotalsEntity(
        date = date,
        kcal = kcal.asDouble(),
        carbsG = carbsG.asDouble(),
        proteinG = proteinG.asDouble(),
        fatG = fatG.asDouble(),
        fiberG = fiberG.asDouble(),
        mealCount = mealCount,
        weekAvgKcal = weekAvgKcal.asDouble(),
        prevWeekAvgKcal = prevWeekAvgKcal.asDouble(),
        weekAvgCarbsG = weekAvgCarbs.asDouble(),
        prevWeekAvgCarbsG = prevWeekAvgCarbs.asDouble(),
        hoursSinceLastMeal = hoursSinceLastMeal.asDouble(),
        fetchedAt = fetchedAt,
        netBalanceKcal = balance?.netBalance.asDouble(),
        tdeeKcal = balance?.tdee.asDouble(),
        activitySource = balance?.activitySource,
        photoCount = 0,
        dailyAverageKcalForPeriod = null,
    )

fun DashboardDayResponse.toTotalsEntity(
    fetchedAt: Instant,
    balance: KcalBalanceDay? = null,
    balanceResponse: KcalBalanceResponse? = null,
): CachedDayTotalsEntity =
    CachedDayTotalsEntity(
        date = date,
        kcal = kcal.asDouble(),
        carbsG = carbsG.asDouble(),
        proteinG = proteinG.asDouble(),
        fatG = fatG.asDouble(),
        fiberG = fiberG.asDouble(),
        mealCount = mealCount,
        weekAvgKcal = null,
        prevWeekAvgKcal = null,
        weekAvgCarbsG = null,
        prevWeekAvgCarbsG = null,
        hoursSinceLastMeal = null,
        fetchedAt = fetchedAt,
        netBalanceKcal = balance?.netBalance.asDouble() ?: balanceResponse?.netBalance.asDouble(),
        tdeeKcal = balance?.tdee.asDouble() ?: balanceResponse?.tdee.asDouble(),
        activitySource = balance?.activitySource ?: balanceResponse?.activitySource,
        photoCount = photoCount ?: 0,
        dailyAverageKcalForPeriod = dailyAverageKcalForPeriod.asDouble(),
    )

fun CachedDayTotalsEntity.toDayTotals(): DayTotals =
    DayTotals(
        date = date,
        kcal = kcal,
        carbsG = carbsG,
        proteinG = proteinG,
        fatG = fatG,
        fiberG = fiberG,
        mealCount = mealCount,
        fetchedAt = fetchedAt,
        netBalanceKcal = netBalanceKcal,
        tdeeKcal = tdeeKcal,
        activitySource = activitySource,
        photoCount = photoCount,
        dailyAverageKcalForPeriod = dailyAverageKcalForPeriod,
    )

fun CachedDayTotalsEntity.toKpiSnapshot(): KpiSnapshot =
    KpiSnapshot(
        kcal = kcal,
        weekAvgKcal = weekAvgKcal,
        prevWeekAvgKcal = prevWeekAvgKcal,
        carbsG = carbsG,
        weekAvgCarbsG = weekAvgCarbsG,
        prevWeekAvgCarbsG = prevWeekAvgCarbsG,
        mealCount = mealCount,
        hoursSinceLastMeal = hoursSinceLastMeal,
    )

fun buildDayState(
    total: CachedDayTotalsEntity,
    meals: List<CachedMealEntity>,
): DayState =
    DayState(
        date = total.date,
        totals = total.toDayTotals(),
        kpis = total.toKpiSnapshot(),
        meals = meals.map { it.toDomain() },
    )

fun MealResponse.toCachedEntity(
    fetchedAt: Instant,
    hasCgm: Boolean = false,
    hasInsulin: Boolean = false,
    baseUrl: String = "",
): CachedMealEntity =
    CachedMealEntity(
        id = id.toString(),
        eatenAt = eatenAt,
        eatenAtDay = eatenAt.toLocalDateTime(TimeZone.currentSystemDefault()).date,
        title = title,
        status = status?.value ?: "accepted",
        source = source.value,
        note = note,
        thumbnailUrl = thumbnailUrl?.let { ApiConnection.resolveUrl(it, baseUrl = baseUrl) },
        totalKcal = totalKcal.asDouble(),
        totalCarbsG = totalCarbsG.asDouble(),
        totalProteinG = totalProteinG.asDouble(),
        totalFatG = totalFatG.asDouble(),
        totalFiberG = totalFiberG.asDouble(),
        updatedAt = updatedAt,
        fetchedAt = fetchedAt,
        confidence = confidence.asDouble(),
        hasCgm = hasCgm,
        hasInsulin = hasInsulin,
        itemsJson = items?.map { it.toDomain() }?.let { OpenApiJson.json.encodeToString(it) },
        nightscoutSyncStatus = nightscoutSyncStatus,
        nightscoutSyncedAt = nightscoutSyncedAt,
        nightscoutLastAttemptAt = nightscoutLastAttemptAt,
        nightscoutSyncError = nightscoutSyncError,
        postprandialJson = postprandialResponse?.let { OpenApiJson.json.encodeToString(it) },
        tagsCsv = tags.pack(),
        photoIdempotencyKey = photoIdempotencyKey,
        estimateStatus = estimateStatus,
        estimateError = estimateError,
        modelUsed = modelUsed,
        mealRole = derivedCategories
            ?.get("meal_role")
            ?.jsonPrimitive
            ?.contentOrNull,
    )

fun CachedMealEntity.toDomain(): Meal =
    Meal(
        id = id,
        eatenAt = eatenAt,
        eatenAtDay = eatenAtDay,
        title = title,
        status = status,
        source = source,
        note = note,
        thumbnailUrl = thumbnailUrl,
        totalKcal = totalKcal,
        totalCarbsG = totalCarbsG,
        totalProteinG = totalProteinG,
        totalFatG = totalFatG,
        totalFiberG = totalFiberG,
        updatedAt = updatedAt,
        confidence = confidence,
        hasCgm = hasCgm,
        hasInsulin = hasInsulin,
        items = itemsJson?.let { OpenApiJson.json.decodeFromString<List<MealItem>>(it) }.orEmpty(),
        nightscoutSyncStatus = nightscoutSyncStatus,
        nightscoutSyncedAt = nightscoutSyncedAt,
        nightscoutLastAttemptAt = nightscoutLastAttemptAt,
        nightscoutSyncError = nightscoutSyncError,
        tags = tagsCsv.unpack().toSet(),
        mealRole = mealRole,
        postprandialResponse = postprandialJson.toPostprandialResponse(),
        estimateStatus = estimateStatus,
        estimateError = estimateError,
        photoIdempotencyKey = photoIdempotencyKey,
        modelUsed = modelUsed,
    )

private fun String?.toPostprandialResponse(): PostprandialResponse? {
    if (isNullOrBlank()) return null
    val root = runCatching {
        OpenApiJson.json.parseToJsonElement(this) as? JsonObject
    }.getOrNull() ?: return null
    val anchors = root["anchors"] as? JsonObject
    val points = listOf(0, 30, 60, 90, 180, 240, 300).mapNotNull { offset ->
        val anchor = anchors?.get(offset.toString()) as? JsonObject
        val value = (anchor?.get("value") as? JsonPrimitive)
            ?.doubleOrNull
        value?.let { PostprandialPoint(offsetMinutes = offset, valueMmolL = it) }
    }
    return PostprandialResponse(
        deltaMaxMmolL = (root["delta_max"] as? JsonPrimitive)?.doubleOrNull,
        coverage180 = (root["coverage_180min"] as? JsonPrimitive)?.doubleOrNull,
        glycemicResponse = (root["glycemic_response"] as? JsonPrimitive)?.contentOrNull,
        points = points,
    )
}

fun MealItemResponse.toDomain(): MealItem =
    MealItem(
        id = id.toString(),
        mealId = mealId.toString(),
        name = name,
        grams = grams.asDouble(),
        kcal = kcal.asDouble(),
        carbsG = carbsG.asDouble(),
        proteinG = proteinG.asDouble(),
        fatG = fatG.asDouble(),
        fiberG = fiberG.asDouble(),
        sourceKind = sourceKind?.value,
        patternId = patternId?.toString(),
        productId = productId?.toString(),
    )

fun ProductResponse.toCachedEntity(fetchedAt: Instant): CachedProductEntity =
    CachedProductEntity(
        id = id.toString(),
        name = name,
        kind = "product",
        subtitle = brand,
        brand = brand,
        aliasesCsv = aliases.pack(),
        imageUrl = imageUrl,
        kcal = kcalPerServing.asDouble() ?: kcalPer100g.asDouble(),
        carbsG = carbsPerServing.asDouble() ?: carbsPer100g.asDouble(),
        proteinG = proteinPerServing.asDouble() ?: proteinPer100g.asDouble(),
        fatG = fatPerServing.asDouble() ?: fatPer100g.asDouble(),
        fiberG = fiberPerServing.asDouble() ?: fiberPer100g.asDouble(),
        defaultGrams = defaultGrams.asDouble(),
        usageCount = usageCount,
        lastUsedAt = lastUsedAt,
        fetchedAt = fetchedAt,
    )

fun DatabaseItemResponse.toCachedProductEntity(fetchedAt: Instant): CachedProductEntity =
    CachedProductEntity(
        id = id.toString(),
        name = displayName,
        kind = kind.value,
        subtitle = subtitle,
        brand = null,
        aliasesCsv = aliases.pack(),
        imageUrl = imageUrl,
        kcal = kcal.asDouble(),
        carbsG = carbsG.asDouble(),
        proteinG = proteinG.asDouble(),
        fatG = fatG.asDouble(),
        fiberG = fiberG.asDouble(),
        defaultGrams = defaultGrams.asDouble(),
        usageCount = usageCount ?: 0,
        lastUsedAt = lastUsedAt,
        fetchedAt = fetchedAt,
    )

fun CachedProductEntity.toDomain(): Product =
    Product(
        id = id,
        name = name,
        kind = kind,
        subtitle = subtitle,
        brand = brand,
        aliases = aliasesCsv.unpack(),
        imageUrl = imageUrl,
        kcal = kcal,
        carbsG = carbsG,
        proteinG = proteinG,
        fatG = fatG,
        fiberG = fiberG,
        defaultGrams = defaultGrams,
        usageCount = usageCount,
        lastUsedAt = lastUsedAt,
    )

fun PatternResponse.toCachedTemplateEntity(fetchedAt: Instant): CachedTemplateEntity =
    CachedTemplateEntity(
        id = id.toString(),
        prefix = prefix,
        name = displayName,
        aliasesCsv = aliases.pack(),
        imageUrl = imageUrl,
        defaultKcal = defaultKcal.asDouble(),
        defaultCarbsG = defaultCarbsG.asDouble(),
        defaultProteinG = defaultProteinG.asDouble(),
        defaultFatG = defaultFatG.asDouble(),
        defaultFiberG = defaultFiberG.asDouble(),
        defaultGrams = defaultGrams.asDouble(),
        usageCount = usageCount,
        lastUsedAt = lastUsedAt,
        fetchedAt = fetchedAt,
    )

fun CachedTemplateEntity.toDomain(): Template =
    Template(
        id = id,
        prefix = prefix,
        name = name,
        aliases = aliasesCsv.unpack(),
        imageUrl = imageUrl,
        defaultKcal = defaultKcal,
        defaultCarbsG = defaultCarbsG,
        defaultProteinG = defaultProteinG,
        defaultFatG = defaultFatG,
        defaultFiberG = defaultFiberG,
        defaultGrams = defaultGrams,
        usageCount = usageCount,
        lastUsedAt = lastUsedAt,
    )

fun OutboxEntity.toDomain(): OutboxItem =
    OutboxItem(
        id = id,
        kind = OpenApiJson.json.decodeFromString<OutboxKind>(kindJson),
        state = state,
        createdAt = createdAt,
        lastAttemptAt = lastAttemptAt,
        nextAttemptAt = nextAttemptAt,
        attempts = attempts,
        serverIdOnSuccess = serverIdOnSuccess,
        errorMessage = errorMessage.userSafePersistedError(),
        enteredCurrentStateAt = enteredCurrentStateAt,
        lastErrorCode = lastErrorCode,
        lastErrorMessage = lastErrorMessage.userSafePersistedError(),
        draft = draftJson?.let { OpenApiJson.json.decodeFromString<MealDraft>(it) },
        linkedMealId = linkedMealId,
        reconciledAt = reconciledAt,
    )

fun OutboxItem.toEntity(): OutboxEntity =
    OutboxEntity(
        id = id,
        kindType = kind.typeName,
        kindJson = OpenApiJson.json.encodeToString(kind),
        state = state,
        createdAt = createdAt,
        lastAttemptAt = lastAttemptAt,
        nextAttemptAt = nextAttemptAt,
        attempts = attempts,
        serverIdOnSuccess = serverIdOnSuccess,
        errorMessage = errorMessage,
        enteredCurrentStateAt = enteredCurrentStateAt,
        lastErrorCode = lastErrorCode,
        lastErrorMessage = lastErrorMessage,
        draftJson = draft?.let { OpenApiJson.json.encodeToString(it) },
        localPhotoPath = when (val itemKind = kind) {
            is OutboxKind.CapturedMeal -> itemKind.localPhotoPath
            is OutboxKind.CreateMeal -> itemKind.payload.localPhotoPath
            is OutboxKind.CopyMealItemWeight,
            is OutboxKind.DeleteMeal,
            is OutboxKind.EditMeal,
            is OutboxKind.PatchMealItem,
            -> null
            else -> null
        },
        linkedMealId = linkedMealId,
        reconciledAt = reconciledAt,
    )

fun MealDraft.toJson(): String = OpenApiJson.json.encodeToString(this)

private val OutboxKind.typeName: String
    get() = when (this) {
        is OutboxKind.CapturedMeal -> "captured_meal"
        is OutboxKind.CreateMeal -> "create_meal"
        is OutboxKind.CopyMealItemWeight -> "copy_meal_item_weight"
        is OutboxKind.DeleteMeal -> "delete_meal"
        is OutboxKind.EditMeal -> "edit_meal"
        is OutboxKind.PatchMealItem -> "patch_meal_item"
        else -> this::class.simpleName ?: "flavor_kind"
    }

private fun String?.userSafePersistedError(): String? {
    val value = this?.takeIf { it.isNotBlank() } ?: return null
    return if (ForbiddenUserErrorPattern.containsMatchIn(value)) {
        "что-то пошло не так · повторить"
    } else {
        value
    }
}

private val ForbiddenUserErrorPattern = Regex(
    pattern = """https?://|\b\d{1,3}(?:\.\d{1,3}){3}\b|timeout|cancellation|cancelled|exception|null|connect_timeout|\w+(?:Exception|Error)\b""",
    options = setOf(RegexOption.IGNORE_CASE),
)
