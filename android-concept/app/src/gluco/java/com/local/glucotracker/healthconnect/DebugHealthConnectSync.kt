package com.local.glucotracker.healthconnect

import android.content.Context
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.result.ActivityResultLauncher
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.aggregate.AggregateMetric
import androidx.health.connect.client.changes.DeletionChange
import androidx.health.connect.client.changes.UpsertionChange
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.*
import androidx.health.connect.client.request.AggregateRequest
import androidx.health.connect.client.request.ChangesTokenRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.local.glucotracker.data.api.SyncApi
import com.local.glucotracker.generated.api.HealthConnectApi
import com.local.glucotracker.generated.model.ActivitySyncRequest
import com.local.glucotracker.generated.model.HealthConnectRecordUpload
import com.local.glucotracker.generated.model.HealthConnectSyncRequest
import dagger.hilt.EntryPoint
import dagger.hilt.InstallIn
import dagger.hilt.android.EntryPointAccessors
import dagger.hilt.components.SingletonComponent
import io.ktor.http.isSuccess
import java.io.IOException
import java.lang.reflect.Modifier
import java.math.BigDecimal
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.temporal.TemporalAccessor
import java.util.IdentityHashMap
import java.util.concurrent.TimeUnit
import kotlin.reflect.KClass
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.datetime.Instant as KxInstant
import kotlinx.datetime.LocalDate as KxLocalDate
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

@EntryPoint
@InstallIn(SingletonComponent::class)
interface HealthConnectEntryPoint {
    fun healthConnectApi(): HealthConnectApi

    fun syncApi(): SyncApi
}

object DebugHealthConnectSync {
    private const val PreferencesName = "health_connect_sync"
    private const val RequestedPermissionsVersionKey = "requested_permissions_version"
    private const val RequestedPermissionsVersion = 2
    private const val ProviderPackage = "com.google.android.apps.healthdata"
    private const val DaysToAggregate = 14
    private const val PageSize = 500
    private const val Tag = "HealthConnectSync"

    private val supportedRecordTypes: List<KClass<out Record>> = listOf(
        ActiveCaloriesBurnedRecord::class,
        BasalBodyTemperatureRecord::class,
        BasalMetabolicRateRecord::class,
        BloodGlucoseRecord::class,
        BloodPressureRecord::class,
        BodyFatRecord::class,
        BodyTemperatureRecord::class,
        BodyWaterMassRecord::class,
        BoneMassRecord::class,
        CervicalMucusRecord::class,
        CyclingPedalingCadenceRecord::class,
        DistanceRecord::class,
        ElevationGainedRecord::class,
        ExerciseSessionRecord::class,
        FloorsClimbedRecord::class,
        HeartRateRecord::class,
        HeartRateVariabilityRmssdRecord::class,
        HeightRecord::class,
        HydrationRecord::class,
        IntermenstrualBleedingRecord::class,
        LeanBodyMassRecord::class,
        MenstruationFlowRecord::class,
        MenstruationPeriodRecord::class,
        MindfulnessSessionRecord::class,
        NutritionRecord::class,
        OvulationTestRecord::class,
        OxygenSaturationRecord::class,
        PlannedExerciseSessionRecord::class,
        PowerRecord::class,
        RespiratoryRateRecord::class,
        RestingHeartRateRecord::class,
        SexualActivityRecord::class,
        SkinTemperatureRecord::class,
        SleepSessionRecord::class,
        SpeedRecord::class,
        StepsCadenceRecord::class,
        StepsRecord::class,
        TotalCaloriesBurnedRecord::class,
        Vo2MaxRecord::class,
        WeightRecord::class,
        WheelchairPushesRecord::class,
    )
    private val recordReadPermissions = supportedRecordTypes
        .map(HealthPermission::getReadPermission)
        .toSet()
    private val requestedPermissions = recordReadPermissions + setOf(
        HealthPermission.PERMISSION_READ_HEALTH_DATA_HISTORY,
        HealthPermission.PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND,
    )
    private val totalCaloriesPermission =
        HealthPermission.getReadPermission(TotalCaloriesBurnedRecord::class)
    private val activeCaloriesPermission =
        HealthPermission.getReadPermission(ActiveCaloriesBurnedRecord::class)
    private val stepsPermission = HealthPermission.getReadPermission(StepsRecord::class)
    private val heartRatePermission = HealthPermission.getReadPermission(HeartRateRecord::class)
    private val restingHeartRatePermission =
        HealthPermission.getReadPermission(RestingHeartRateRecord::class)
    private val activityPermissions = setOf(
        totalCaloriesPermission,
        activeCaloriesPermission,
        stepsPermission,
        heartRatePermission,
        restingHeartRatePermission,
    )
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var permissionLauncher: ActivityResultLauncher<Set<String>>? = null
    private var appContext: Context? = null

    @JvmStatic
    fun install(activity: ComponentActivity) {
        if (HealthConnectClient.getSdkStatus(activity, ProviderPackage) !=
            HealthConnectClient.SDK_AVAILABLE
        ) {
            return
        }
        appContext = activity.applicationContext
        val client = HealthConnectClient.getOrCreate(activity)
        permissionLauncher = activity.registerForActivityResult(
            PermissionController.createRequestPermissionResultContract(),
        ) { granted ->
            val context = activity.applicationContext
            context.getSharedPreferences(PreferencesName, Context.MODE_PRIVATE)
                .edit()
                .putInt(RequestedPermissionsVersionKey, RequestedPermissionsVersion)
                .apply()
            if (HealthPermission.PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND in granted) {
                schedulePeriodicSync(context)
            }
            launchSync(context, client, granted)
        }

        scope.launch {
            val granted = client.permissionController.getGrantedPermissions()
            val preferences = activity.getSharedPreferences(
                PreferencesName,
                Context.MODE_PRIVATE,
            )
            val shouldRequest = requestedPermissions.any { it !in granted } &&
                preferences.getInt(RequestedPermissionsVersionKey, 0) <
                RequestedPermissionsVersion
            if (shouldRequest) {
                withContext(Dispatchers.Main) {
                    permissionLauncher?.launch(requestedPermissions)
                }
            } else {
                if (HealthPermission.PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND in granted) {
                    schedulePeriodicSync(activity.applicationContext)
                }
                runForegroundSync(activity.applicationContext, client, granted)
            }
        }
    }

    @JvmStatic
    fun requestSync() {
        val context = appContext ?: return
        if (HealthConnectClient.getSdkStatus(context, ProviderPackage) !=
            HealthConnectClient.SDK_AVAILABLE
        ) {
            return
        }
        val client = HealthConnectClient.getOrCreate(context)
        scope.launch {
            val granted = client.permissionController.getGrantedPermissions()
            if (requestedPermissions.any { it !in granted }) {
                withContext(Dispatchers.Main) {
                    permissionLauncher?.launch(requestedPermissions)
                }
            } else {
                runForegroundSync(context, client, granted)
            }
        }
    }

    internal suspend fun syncFromWorker(context: Context): Boolean {
        if (HealthConnectClient.getSdkStatus(context, ProviderPackage) !=
            HealthConnectClient.SDK_AVAILABLE
        ) {
            return true
        }
        val client = HealthConnectClient.getOrCreate(context)
        val granted = client.permissionController.getGrantedPermissions()
        if (HealthPermission.PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND !in granted) {
            return true
        }
        return runCatching {
            syncGrantedData(context, client, granted)
            true
        }.getOrElse { error ->
            Log.w(Tag, "Background sync failed: ${error.safeFailureName()}")
            !error.shouldRetryInBackground()
        }
    }

    private fun launchSync(
        context: Context,
        client: HealthConnectClient,
        granted: Set<String>,
    ) {
        scope.launch {
            runForegroundSync(context, client, granted)
        }
    }

    private suspend fun runForegroundSync(
        context: Context,
        client: HealthConnectClient,
        granted: Set<String>,
    ) {
        runCatching { syncGrantedData(context, client, granted) }
            .onFailure { error ->
                Log.w(Tag, "Foreground sync failed: ${error.safeFailureName()}")
            }
    }

    private suspend fun syncGrantedData(
        context: Context,
        client: HealthConnectClient,
        granted: Set<String>,
    ) {
        val entryPoint = EntryPointAccessors.fromApplication(
            context,
            HealthConnectEntryPoint::class.java,
        )
        if (granted.any { it in activityPermissions }) {
            syncRecentActivity(
                client = client,
                syncApi = entryPoint.syncApi(),
                grantedPermissions = granted,
            )
        }
        if (granted.any { it in recordReadPermissions }) {
            syncRawRecords(
                context = context,
                client = client,
                api = entryPoint.healthConnectApi(),
                grantedPermissions = granted,
            )
        }
    }

    private suspend fun syncRawRecords(
        context: Context,
        client: HealthConnectClient,
        api: HealthConnectApi,
        grantedPermissions: Set<String>,
    ) {
        val canReadHistory = HealthPermission.PERMISSION_READ_HEALTH_DATA_HISTORY in
            grantedPermissions
        supportedRecordTypes.forEach { recordType ->
            val permission = HealthPermission.getReadPermission(recordType)
            if (permission !in grantedPermissions) return@forEach
            try {
                syncRecordType(
                    context = context,
                    client = client,
                    api = api,
                    recordType = recordType,
                    canReadHistory = canReadHistory,
                )
            } catch (error: Throwable) {
                if (error is HealthConnectUploadException || error.isRetryableSyncFailure()) {
                    throw error
                }
                Log.w(
                    Tag,
                    "Skipped ${recordType.simpleName}: ${error::class.java.simpleName}",
                )
            }
        }
    }

    private suspend fun syncRecordType(
        context: Context,
        client: HealthConnectClient,
        api: HealthConnectApi,
        recordType: KClass<out Record>,
        canReadHistory: Boolean,
        allowExpiredTokenReset: Boolean = true,
    ) {
        val preferences = context.getSharedPreferences(PreferencesName, Context.MODE_PRIVATE)
        val tokenKey = "changes_token_${recordType.qualifiedName}"
        var changesToken = preferences.getString(tokenKey, null)
        if (changesToken == null) {
            changesToken = client.getChangesToken(
                ChangesTokenRequest(recordTypes = setOf(recordType)),
            )
            val start = if (canReadHistory) {
                Instant.EPOCH
            } else {
                Instant.now().minus(Duration.ofDays(30))
            }
            readAndUploadAll(
                client = client,
                api = api,
                recordType = recordType,
                start = start,
                end = Instant.now(),
            )
            preferences.edit().putString(tokenKey, changesToken).apply()
        }

        var activeToken = changesToken ?: return
        while (true) {
            val response = client.getChanges(activeToken)
            if (response.changesTokenExpired) {
                preferences.edit().remove(tokenKey).apply()
                if (allowExpiredTokenReset) {
                    syncRecordType(
                        context = context,
                        client = client,
                        api = api,
                        recordType = recordType,
                        canReadHistory = canReadHistory,
                        allowExpiredTokenReset = false,
                    )
                }
                return
            }
            val upserts = response.changes
                .filterIsInstance<UpsertionChange>()
                .map { it.record }
            val deletions = response.changes
                .filterIsInstance<DeletionChange>()
                .map { it.recordId }
            upload(api, upserts, deletions)
            activeToken = response.nextChangesToken
            preferences.edit().putString(tokenKey, activeToken).apply()
            if (!response.hasMore) return
        }
    }

    private suspend fun readAndUploadAll(
        client: HealthConnectClient,
        api: HealthConnectApi,
        recordType: KClass<out Record>,
        start: Instant,
        end: Instant,
    ) {
        var pageToken: String? = null
        do {
            val response = client.readRecords(
                ReadRecordsRequest(
                    recordType = recordType,
                    timeRangeFilter = TimeRangeFilter.between(start, end),
                    ascendingOrder = true,
                    pageSize = PageSize,
                    pageToken = pageToken,
                ),
            )
            upload(api, response.records, emptyList())
            pageToken = response.pageToken
        } while (pageToken != null)
    }

    private suspend fun upload(
        api: HealthConnectApi,
        records: List<Record>,
        deletedRecordIds: List<String>,
    ) {
        records.chunked(PageSize).forEach { batch ->
            send(
                api,
                HealthConnectSyncRequest(
                    records = batch.map { record -> record.toUpload() },
                    deletedRecordIds = emptyList(),
                ),
            )
        }
        deletedRecordIds.chunked(1000).forEach { batch ->
            send(
                api,
                HealthConnectSyncRequest(
                    records = emptyList(),
                    deletedRecordIds = batch,
                ),
            )
        }
    }

    private suspend fun send(
        api: HealthConnectApi,
        request: HealthConnectSyncRequest,
    ) {
        val response = api.syncHealthConnectRecords(request)
        if (!response.response.status.isSuccess()) {
            throw HealthConnectUploadException(response.response.status.value)
        }
        response.body()
    }

    private fun Record.toUpload(): HealthConnectRecordUpload {
        val instantTime = instantProperty("getTime")
        val start = instantProperty("getStartTime") ?: instantTime
        val end = instantProperty("getEndTime") ?: instantTime
        val serialized = toJsonElement(this, IdentityHashMap())
        val payload = (serialized as? JsonObject)?.toMap()
            ?: mapOf("value" to serialized)
        return HealthConnectRecordUpload(
            recordId = metadata.id,
            recordType = this::class.simpleName ?: javaClass.name,
            clientRecordId = metadata.clientRecordId,
            clientRecordVersion = metadata.clientRecordVersion,
            dataOrigin = metadata.dataOrigin.packageName,
            recordingMethod = metadata.recordingMethod,
            startTime = start?.toKxInstant(),
            endTime = end?.toKxInstant(),
            lastModifiedTime = metadata.lastModifiedTime.toKxInstant(),
            payload = payload,
        )
    }

    private fun Instant.toKxInstant(): KxInstant = KxInstant.parse(toString())

    private fun Record.instantProperty(getterName: String): Instant? =
        javaClass.methods
            .firstOrNull { method ->
                method.name == getterName && method.parameterCount == 0
            }
            ?.let { method -> runCatching { method.invoke(this) as? Instant }.getOrNull() }

    private fun toJsonElement(
        value: Any?,
        visited: IdentityHashMap<Any, Boolean>,
        depth: Int = 0,
    ): JsonElement {
        if (value == null) return JsonNull
        if (depth > 12) return JsonPrimitive(value.toString())
        return when (value) {
            is JsonElement -> value
            is Boolean -> JsonPrimitive(value)
            is Byte, is Short, is Int, is Long -> JsonPrimitive(value as Number)
            is Float -> if (value.isFinite()) JsonPrimitive(value) else JsonPrimitive(value.toString())
            is Double -> if (value.isFinite()) JsonPrimitive(value) else JsonPrimitive(value.toString())
            is BigDecimal -> JsonPrimitive(value)
            is CharSequence, is Char, is Enum<*> -> JsonPrimitive(value.toString())
            is TemporalAccessor, is Duration -> JsonPrimitive(value.toString())
            is Map<*, *> -> JsonObject(
                value.entries.associate { (key, nested) ->
                    key.toString() to toJsonElement(nested, visited, depth + 1)
                },
            )
            is Iterable<*> -> JsonArray(
                value.map { nested -> toJsonElement(nested, visited, depth + 1) },
            )
            else -> reflectObject(value, visited, depth)
        }
    }

    private fun reflectObject(
        value: Any,
        visited: IdentityHashMap<Any, Boolean>,
        depth: Int,
    ): JsonElement {
        if (value.javaClass.isArray) {
            val length = java.lang.reflect.Array.getLength(value)
            return JsonArray(
                (0 until length).map { index ->
                    toJsonElement(java.lang.reflect.Array.get(value, index), visited, depth + 1)
                },
            )
        }
        if (visited.put(value, true) != null) return JsonPrimitive(value.toString())
        return try {
            val properties = value.javaClass.methods
                .asSequence()
                .filter { method ->
                    method.parameterCount == 0 &&
                        !Modifier.isStatic(method.modifiers) &&
                        method.name != "getClass" &&
                        '$' !in method.name &&
                        (method.name.startsWith("get") || method.name.startsWith("is"))
                }
                .sortedBy { it.name }
                .mapNotNull { method ->
                    val propertyName = when {
                        method.name.startsWith("get") -> method.name.removePrefix("get")
                        else -> method.name.removePrefix("is")
                    }.replaceFirstChar(Char::lowercase)
                    runCatching { method.invoke(value) }
                        .getOrNull()
                        ?.let { nested ->
                            propertyName to toJsonElement(nested, visited, depth + 1)
                        }
                }
                .toMap()
            if (properties.isEmpty()) JsonPrimitive(value.toString()) else JsonObject(properties)
        } finally {
            visited.remove(value)
        }
    }

    private fun Throwable.isRetryableSyncFailure(): Boolean =
        this is IOException || javaClass.name.startsWith("io.ktor.")

    private fun Throwable.shouldRetryInBackground(): Boolean =
        isRetryableSyncFailure() ||
            (this is HealthConnectUploadException && statusCode >= 500)

    private fun Throwable.safeFailureName(): String =
        if (this is HealthConnectUploadException) {
            "HTTP $statusCode"
        } else {
            javaClass.simpleName
        }

    private suspend fun syncRecentActivity(
        client: HealthConnectClient,
        syncApi: SyncApi,
        grantedPermissions: Set<String>,
    ) {
        val zone = ZoneId.systemDefault()
        val today = LocalDate.now(zone)
        (0 until DaysToAggregate).forEach { offset ->
            val day = today.minusDays(offset.toLong())
            try {
                syncActivityDay(client, syncApi, day, zone, grantedPermissions)
            } catch (error: Throwable) {
                if (error.isRetryableSyncFailure()) throw error
                Log.w(Tag, "Activity aggregate skipped: ${error::class.java.simpleName}")
            }
        }
    }

    private suspend fun syncActivityDay(
        client: HealthConnectClient,
        syncApi: SyncApi,
        day: LocalDate,
        zone: ZoneId,
        grantedPermissions: Set<String>,
    ) {
        val start = day.atStartOfDay(zone).toInstant()
        val end = day.plusDays(1).atStartOfDay(zone).toInstant()
        val metrics = buildSet<AggregateMetric<*>> {
            if (totalCaloriesPermission in grantedPermissions) {
                add(TotalCaloriesBurnedRecord.ENERGY_TOTAL)
            }
            if (activeCaloriesPermission in grantedPermissions) {
                add(ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL)
            }
            if (stepsPermission in grantedPermissions) add(StepsRecord.COUNT_TOTAL)
            if (heartRatePermission in grantedPermissions) {
                add(HeartRateRecord.BPM_AVG)
                add(HeartRateRecord.MEASUREMENTS_COUNT)
            }
            if (restingHeartRatePermission in grantedPermissions) {
                add(RestingHeartRateRecord.BPM_AVG)
            }
        }
        if (metrics.isEmpty()) return
        val result = client.aggregate(
            AggregateRequest(
                metrics = metrics,
                timeRangeFilter = TimeRangeFilter.between(start, end),
            ),
        )
        val totalKcal = result[TotalCaloriesBurnedRecord.ENERGY_TOTAL]?.inKilocalories
        val activeKcal = result[ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL]?.inKilocalories
        val steps = result[StepsRecord.COUNT_TOTAL]?.toInt() ?: 0
        val heartRateAvg = result[HeartRateRecord.BPM_AVG]?.toDouble()
        val heartRateRest = result[RestingHeartRateRecord.BPM_AVG]?.toDouble()
        val heartRateSamples = result[HeartRateRecord.MEASUREMENTS_COUNT]?.toInt() ?: 0
        val kcal = totalKcal?.takeIf { it > 0.0 }
            ?: activeKcal?.takeIf { it > 0.0 }
            ?: 0.0
        val source = when {
            totalKcal != null && totalKcal > 0.0 -> "health_connect_total"
            activeKcal != null && activeKcal > 0.0 -> "health_connect_active"
            else -> "health_connect_steps"
        }
        val confidence = when (source) {
            "health_connect_total" -> "high"
            "health_connect_active" -> "medium"
            else -> "low"
        }
        if (kcal <= 0.0 && steps <= 0 && heartRateSamples <= 0) return
        syncApi.syncActivity(
            ActivitySyncRequest(
                date = KxLocalDate(day.year, day.monthValue, day.dayOfMonth),
                steps = steps,
                activeMinutes = 0,
                kcalBurned = kcal.toBigDecimalOrZero(),
                heartRateAvg = heartRateAvg?.toBigDecimalOrZero(),
                heartRateRest = heartRateRest?.toBigDecimalOrZero(),
                source = source,
                hrSamples = heartRateSamples,
                hrActiveMinutes = 0,
                kcalHrActive = (activeKcal ?: 0.0).toBigDecimalOrZero(),
                kcalSteps = BigDecimal.ZERO,
                kcalNoMoveHr = BigDecimal.ZERO,
                calorieConfidence = confidence,
            ),
        )
    }

    private fun Double.toBigDecimalOrZero(): BigDecimal =
        if (isFinite()) BigDecimal.valueOf(this) else BigDecimal.ZERO

    private fun schedulePeriodicSync(context: Context) {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()
        val request = PeriodicWorkRequestBuilder<HealthConnectSyncWorker>(
            1,
            TimeUnit.HOURS,
        ).setConstraints(constraints).build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            "health_connect_raw_sync",
            ExistingPeriodicWorkPolicy.UPDATE,
            request,
        )
    }
}

private class HealthConnectUploadException(
    val statusCode: Int,
) : RuntimeException()

class HealthConnectSyncWorker(
    appContext: Context,
    workerParameters: WorkerParameters,
) : CoroutineWorker(appContext, workerParameters) {
    override suspend fun doWork(): Result =
        if (DebugHealthConnectSync.syncFromWorker(applicationContext)) {
            Result.success()
        } else {
            Result.retry()
        }
}
