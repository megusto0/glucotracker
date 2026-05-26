package com.local.glucotracker.healthconnect

import android.content.Context
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.result.ActivityResultLauncher
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.aggregate.AggregateMetric
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.RestingHeartRateRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.records.TotalCaloriesBurnedRecord
import androidx.health.connect.client.request.AggregateRequest
import androidx.health.connect.client.time.TimeRangeFilter
import com.local.glucotracker.data.api.SyncApi
import com.local.glucotracker.generated.model.ActivitySyncRequest
import java.math.BigDecimal
import java.time.LocalDate
import java.time.ZoneId
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.datetime.LocalDate as KxLocalDate

object DebugHealthConnectSync {
    private const val PreferencesName = "debug_health_connect"
    private const val RequestedPermissionsKey = "requested_permissions"
    private const val ProviderPackage = "com.google.android.apps.healthdata"
    private const val DaysToSync = 14
    private const val Tag = "DebugHealthConnect"

    private val totalCaloriesPermission = HealthPermission.getReadPermission(TotalCaloriesBurnedRecord::class)
    private val activeCaloriesPermission = HealthPermission.getReadPermission(ActiveCaloriesBurnedRecord::class)
    private val stepsPermission = HealthPermission.getReadPermission(StepsRecord::class)
    private val heartRatePermission = HealthPermission.getReadPermission(HeartRateRecord::class)
    private val restingHeartRatePermission = HealthPermission.getReadPermission(RestingHeartRateRecord::class)

    private val requestedPermissions = setOf(
        totalCaloriesPermission,
        activeCaloriesPermission,
        stepsPermission,
        heartRatePermission,
        restingHeartRatePermission,
    )
    private val syncablePermissions = setOf(
        totalCaloriesPermission,
        activeCaloriesPermission,
        stepsPermission,
    )
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var permissionLauncher: ActivityResultLauncher<Set<String>>? = null
    private var healthConnectClient: HealthConnectClient? = null
    private var healthSyncApi: SyncApi? = null

    @JvmStatic
    fun install(activity: ComponentActivity, syncApi: SyncApi) {
        val status = HealthConnectClient.getSdkStatus(activity, ProviderPackage)
        if (status != HealthConnectClient.SDK_AVAILABLE) return

        val client = HealthConnectClient.getOrCreate(activity)
        healthConnectClient = client
        healthSyncApi = syncApi
        permissionLauncher = activity.registerForActivityResult(
            PermissionController.createRequestPermissionResultContract(),
        ) { granted ->
            if (granted.canSyncActivity()) {
                scope.launch { syncRecentDays(client, syncApi, granted) }
            }
        }

        scope.launch {
            val granted = client.permissionController.getGrantedPermissions()
            if (granted.canSyncActivity()) {
                syncRecentDays(client, syncApi, granted)
                return@launch
            }

            val preferences = activity.getSharedPreferences(PreferencesName, Context.MODE_PRIVATE)
            if (!preferences.getBoolean(RequestedPermissionsKey, false)) {
                preferences.edit().putBoolean(RequestedPermissionsKey, true).apply()
                withContext(Dispatchers.Main) {
                    permissionLauncher?.launch(requestedPermissions)
                }
            }
        }
    }

    @JvmStatic
    fun requestSync() {
        val client = healthConnectClient ?: return
        val syncApi = healthSyncApi ?: return
        scope.launch {
            val granted = client.permissionController.getGrantedPermissions()
            if (granted.canSyncActivity()) {
                syncRecentDays(client, syncApi, granted)
            } else {
                withContext(Dispatchers.Main) {
                    permissionLauncher?.launch(requestedPermissions)
                }
            }
        }
    }

    private suspend fun syncRecentDays(
        client: HealthConnectClient,
        syncApi: SyncApi,
        grantedPermissions: Set<String>,
    ) {
        val zone = ZoneId.systemDefault()
        val today = LocalDate.now(zone)
        (0 until DaysToSync).forEach { offset ->
            runCatching {
                syncDay(
                    client = client,
                    syncApi = syncApi,
                    day = today.minusDays(offset.toLong()),
                    zone = zone,
                    grantedPermissions = grantedPermissions,
                )
            }.onFailure { error ->
                Log.w(Tag, "Health Connect sync failed for ${today.minusDays(offset.toLong())}", error)
            }
        }
    }

    private suspend fun syncDay(
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
            if (stepsPermission in grantedPermissions) {
                add(StepsRecord.COUNT_TOTAL)
            }
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

    private fun Set<String>.canSyncActivity(): Boolean = any { it in syncablePermissions }

    private fun Double.toBigDecimalOrZero(): BigDecimal =
        if (isFinite()) BigDecimal.valueOf(this) else BigDecimal.ZERO
}
