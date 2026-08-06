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
import io.ktor.client.statement.bodyAsText
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
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
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
    private const val LastSyncAtKey = "last_sync_at"
    private const val LastSyncRecordsKey = "last_sync_records"
    private const val LastSyncDeletedKey = "last_sync_deleted"
    private const val LastSyncSkippedKey = "last_sync_skipped"
    private const val LastSyncUnreadableKey = "last_sync_unreadable"
    private const val LastSyncErrorKey = "last_sync_error"
    private const val ProviderPackage = "com.google.android.apps.healthdata"
    private const val DaysToAggregate = 14
    private const val PageSize = 500
    private const val ActivityDayConcurrency = 4
    private const val UploadErrorDetailChars = 400

    /**
     * Narrowest window worth isolating around a record the SDK cannot read.
     *
     * Splitting further would cost more round trips than the hour of data is
     * worth, and the record is unreadable at the source either way.
     */
    private val UnreadableSpanFloor: Duration = Duration.ofHours(1)
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

    @Volatile
    private var syncInProgress = false

    /**
     * Set the moment the button is pressed, not when the coroutine gets going.
     *
     * [syncInProgress] was only raised inside [runForegroundSync], which starts
     * after `getGrantedPermissions()` has suspended. A caller polling "is it
     * running" in that gap saw false, decided the run had finished, and redrew
     * the previous run's numbers — so the button appeared to do nothing, or to
     * stop after a second with a stale result.
     */
    @Volatile
    private var syncRequested = false

    /** Records uploaded so far in the run, so a long sync can show movement. */
    @Volatile
    private var progressRecords = 0

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
        syncRequested = true
        progressRecords = 0
        scope.launch {
            try {
                val granted = client.permissionController.getGrantedPermissions()
                if (requestedPermissions.any { it !in granted }) {
                    withContext(Dispatchers.Main) {
                        permissionLauncher?.launch(requestedPermissions)
                    }
                } else {
                    runForegroundSync(context, client, granted)
                }
            } finally {
                // Also clears on the permission-dialog path, where no sync runs
                // at all and the caller would otherwise wait for one forever.
                syncRequested = false
            }
        }
    }

    @JvmStatic
    fun forceSyncNow() {
        requestSync()
    }

    @JvmStatic
    fun isSyncRunning(): Boolean = syncRequested || syncInProgress

    @JvmStatic
    fun getSyncProgressRecords(): Int = progressRecords

    @JvmStatic
    fun getLastSyncAtMillis(): Long =
        appContext?.getSharedPreferences(PreferencesName, Context.MODE_PRIVATE)
            ?.getLong(LastSyncAtKey, -1L)
            ?: -1L

    @JvmStatic
    fun getLastSyncRecords(): Int =
        appContext?.getSharedPreferences(PreferencesName, Context.MODE_PRIVATE)
            ?.getInt(LastSyncRecordsKey, 0)
            ?: 0

    @JvmStatic
    fun getLastSyncDeleted(): Int =
        appContext?.getSharedPreferences(PreferencesName, Context.MODE_PRIVATE)
            ?.getInt(LastSyncDeletedKey, 0)
            ?: 0

    @JvmStatic
    fun getLastSyncSkipped(): Int =
        appContext?.getSharedPreferences(PreferencesName, Context.MODE_PRIVATE)
            ?.getInt(LastSyncSkippedKey, 0)
            ?: 0

    @JvmStatic
    fun getLastSyncUnreadable(): Int =
        appContext?.getSharedPreferences(PreferencesName, Context.MODE_PRIVATE)
            ?.getInt(LastSyncUnreadableKey, 0)
            ?: 0

    @JvmStatic
    fun getLastSyncError(): String? =
        appContext?.getSharedPreferences(PreferencesName, Context.MODE_PRIVATE)
            ?.getString(LastSyncErrorKey, null)
            ?.takeIf { it.isNotEmpty() }

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
            val counts = syncGrantedData(context, client, granted)
            persistLastSync(context, counts, error = null)
            true
        }.getOrElse { error ->
            persistLastSync(context, SyncRunCounts(), error = error.safeFailureName())
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
        syncInProgress = true
        progressRecords = 0
        try {
            val counts = syncGrantedData(context, client, granted)
            persistLastSync(context, counts, error = null)
        } catch (error: Throwable) {
            persistLastSync(context, SyncRunCounts(), error = error.safeFailureName())
            Log.w(Tag, "Foreground sync failed: ${error.safeFailureName()}")
        } finally {
            syncInProgress = false
        }
    }

    private fun persistLastSync(
        context: Context,
        counts: SyncRunCounts,
        error: String?,
    ) {
        context.getSharedPreferences(PreferencesName, Context.MODE_PRIVATE)
            .edit()
            .putLong(LastSyncAtKey, System.currentTimeMillis())
            .putInt(LastSyncRecordsKey, counts.records)
            .putInt(LastSyncDeletedKey, counts.deleted)
            .putInt(LastSyncSkippedKey, counts.skipped)
            .putInt(LastSyncUnreadableKey, counts.unreadable)
            .putString(LastSyncErrorKey, error.orEmpty())
            .apply()
    }

    /** Days are aggregated several at a time, so the tallies are guarded. */
    private class SyncRunCounts {
        private val lock = Any()
        var records: Int = 0
            private set
        var deleted: Int = 0
            private set
        var days: Int = 0
            private set
        var skipped: Int = 0
            private set

        /**
         * Spans the SDK could not build records from, which is not a failure of
         * ours to fix and not a reason to tell the user their data is missing.
         */
        var unreadable: Int = 0
            private set

        fun addRecords(count: Int): Int = synchronized(lock) {
            records += count
            records
        }

        fun addDeleted(count: Int) = synchronized(lock) { deleted += count }

        fun addDay() = synchronized(lock) { days += 1 }

        fun addSkipped() = synchronized(lock) { skipped += 1 }

        fun addUnreadable() = synchronized(lock) { unreadable += 1 }
    }

    private suspend fun syncGrantedData(
        context: Context,
        client: HealthConnectClient,
        granted: Set<String>,
    ): SyncRunCounts {
        val counts = SyncRunCounts()
        val entryPoint = EntryPointAccessors.fromApplication(
            context,
            HealthConnectEntryPoint::class.java,
        )
        if (granted.any { it in activityPermissions }) {
            syncRecentActivity(
                client = client,
                syncApi = entryPoint.syncApi(),
                grantedPermissions = granted,
                counts = counts,
            )
        }
        if (granted.any { it in recordReadPermissions }) {
            syncRawRecords(
                context = context,
                client = client,
                api = entryPoint.healthConnectApi(),
                grantedPermissions = granted,
                counts = counts,
            )
        }
        return counts
    }

    private suspend fun syncRawRecords(
        context: Context,
        client: HealthConnectClient,
        api: HealthConnectApi,
        grantedPermissions: Set<String>,
        counts: SyncRunCounts,
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
                    counts = counts,
                )
            } catch (error: Throwable) {
                // A 5xx or a dropped connection is worth abandoning the run
                // for: the next one will get further. A 4xx never will — the
                // server has judged this record type and will judge it the same
                // way forever, so it must not take the other forty with it.
                if (error.isRetryableSyncFailure() ||
                    (error is HealthConnectUploadException && error.statusCode >= 500)
                ) {
                    throw error
                }
                if (error is HealthConnectUploadException) {
                    Log.w(
                        Tag,
                        "Rejected ${recordType.simpleName}: " +
                            "HTTP ${error.statusCode} ${error.detail}",
                    )
                } else {
                    Log.w(
                        Tag,
                        "Skipped ${recordType.simpleName}: ${error.stackTraceToString()}",
                    )
                }
                counts.addSkipped()
            }
        }
    }

    private suspend fun syncRecordType(
        context: Context,
        client: HealthConnectClient,
        api: HealthConnectApi,
        recordType: KClass<out Record>,
        canReadHistory: Boolean,
        counts: SyncRunCounts,
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
                counts = counts,
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
                        counts = counts,
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
            upload(api, upserts, deletions, counts)
            activeToken = response.nextChangesToken
            preferences.edit().putString(tokenKey, activeToken).apply()
            if (!response.hasMore) return
        }
    }

    /**
     * Read a range, and if the provider holds a record the SDK cannot build,
     * narrow in on it rather than losing the whole record type.
     *
     * Health Connect stores step records with `startTime == endTime`, which the
     * androidx converter rejects — `readRecords` throws before returning a
     * single row. The changes token is only saved once that first read
     * succeeds, so every run retried the same page, failed the same way, and
     * reported partial data forever. Steps never synced at all.
     *
     * Halving the range isolates the unreadable span: everything either side of
     * it goes up, and only the last hour-wide window around the bad record is
     * given up. The fast path is unchanged — one pass over the whole range, and
     * the splitting only happens after something has actually failed.
     */
    private suspend fun readAndUploadAll(
        client: HealthConnectClient,
        api: HealthConnectApi,
        recordType: KClass<out Record>,
        start: Instant,
        end: Instant,
        counts: SyncRunCounts,
    ) {
        val pending = ArrayDeque<Pair<Instant, Instant>>()
        pending.addLast(start to end)
        while (pending.isNotEmpty()) {
            val (from, to) = pending.removeFirst()
            try {
                readRange(client, api, recordType, from, to, counts)
            } catch (error: Throwable) {
                if (error is HealthConnectUploadException ||
                    error.isRetryableSyncFailure()
                ) {
                    throw error
                }
                val span = Duration.between(from, to)
                if (span <= UnreadableSpanFloor) {
                    Log.w(
                        Tag,
                        "Unreadable ${recordType.simpleName} near $from: " +
                            error.safeFailureName(),
                    )
                    counts.addUnreadable()
                    continue
                }
                val middle = from.plus(span.dividedBy(2))
                // Oldest first, so uploads keep arriving in time order.
                pending.addFirst(middle to to)
                pending.addFirst(from to middle)
            }
        }
    }

    /**
     * Read the next page while the previous one is still uploading.
     *
     * These alternated strictly: read 500 records, serialize them, POST them,
     * wait, then read the next 500. Both halves are latency-bound and neither
     * needs the other, so the run cost their sum. Overlapping them costs the
     * larger of the two, which on a first sync of a year of heart rate is the
     * difference between minutes and a fraction of them. One page in flight —
     * enough to hide the latency without holding two pages of serialized JSON
     * in memory or letting the uploads arrive out of order.
     */
    private suspend fun readRange(
        client: HealthConnectClient,
        api: HealthConnectApi,
        recordType: KClass<out Record>,
        start: Instant,
        end: Instant,
        counts: SyncRunCounts,
    ) = coroutineScope {
        var pageToken: String? = null
        var inFlight: Deferred<Unit>? = null
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
            val page = response.records
            // Surfaces a failed upload here rather than swallowing it into a
            // cancelled scope, and keeps at most one page outstanding.
            inFlight?.await()
            inFlight = async { upload(api, page, emptyList(), counts) }
            pageToken = response.pageToken
        } while (pageToken != null)
        inFlight?.await()
    }

    private suspend fun upload(
        api: HealthConnectApi,
        records: List<Record>,
        deletedRecordIds: List<String>,
        counts: SyncRunCounts,
    ) {
        records.chunked(PageSize).forEach { batch ->
            send(
                api,
                HealthConnectSyncRequest(
                    records = batch.map { record -> record.toUpload() },
                    deletedRecordIds = emptyList(),
                ),
            )
            progressRecords = counts.addRecords(batch.size)
        }
        deletedRecordIds.chunked(1000).forEach { batch ->
            send(
                api,
                HealthConnectSyncRequest(
                    records = emptyList(),
                    deletedRecordIds = batch,
                ),
            )
            counts.addDeleted(batch.size)
        }
    }

    private suspend fun send(
        api: HealthConnectApi,
        request: HealthConnectSyncRequest,
    ) {
        val response = api.syncHealthConnectRecords(request)
        if (!response.response.status.isSuccess()) {
            // The body said which field the server refused and was thrown away,
            // leaving "HTTP 422" as the only evidence of a rejected upload.
            val detail = runCatching { response.response.bodyAsText() }
                .getOrDefault("")
                .take(UploadErrorDetailChars)
            throw HealthConnectUploadException(response.response.status.value, detail)
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
        counts: SyncRunCounts,
    ) {
        val zone = ZoneId.systemDefault()
        val today = LocalDate.now(zone)
        // Fourteen days, each an aggregate query and a POST, ran one after the
        // other for no reason: the days are independent and land in different
        // rows. A few at a time keeps the round trips overlapping without
        // opening fourteen sockets at once.
        (0 until DaysToAggregate)
            .map { offset -> today.minusDays(offset.toLong()) }
            .chunked(ActivityDayConcurrency)
            .forEach { group ->
                coroutineScope {
                    group.map { day ->
                        async {
                            try {
                                syncActivityDay(
                                    client,
                                    syncApi,
                                    day,
                                    zone,
                                    grantedPermissions,
                                    counts,
                                )
                            } catch (error: Throwable) {
                                if (error.isRetryableSyncFailure()) throw error
                                Log.w(
                                    Tag,
                                    "Activity aggregate skipped: " +
                                        error::class.java.simpleName,
                                )
                            }
                        }
                    }.forEach { it.await() }
                }
            }
    }

    private suspend fun syncActivityDay(
        client: HealthConnectClient,
        syncApi: SyncApi,
        day: LocalDate,
        zone: ZoneId,
        grantedPermissions: Set<String>,
        counts: SyncRunCounts,
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
        counts.addDay()
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
    val detail: String = "",
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
