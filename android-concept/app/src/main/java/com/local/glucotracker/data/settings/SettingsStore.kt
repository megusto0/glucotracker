package com.local.glucotracker.data.settings

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.doublePreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.local.glucotracker.domain.model.NightscoutConnectionState
import com.local.glucotracker.domain.model.NightscoutStatus
import com.local.glucotracker.domain.model.UiPrefs
import com.local.glucotracker.domain.model.UserGoals
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.datetime.Instant

data class NotificationToggles(
    val mealReminder: Boolean,
    val nsFail: Boolean,
    val lowConfidence: Boolean,
    val estimateReady: Boolean,
)

private val Context.settingsDataStore by preferencesDataStore(name = "settings")

@Singleton
class SettingsStore @Inject constructor(
    @ApplicationContext context: Context,
) {
    private val dataStore = context.settingsDataStore

    val userGoals: Flow<UserGoals> =
        dataStore.data.map { preferences ->
            UserGoals(
                dailyKcal = preferences[Keys.DailyKcal],
                dailyCarbsG = preferences[Keys.DailyCarbsG],
                weightKg = preferences[Keys.WeightKg],
            )
        }

    val uiPrefs: Flow<UiPrefs> =
        dataStore.data.map { preferences ->
            UiPrefs(
                glucoseMode = preferences[Keys.GlucoseMode] ?: "raw",
                useCompactRows = preferences[Keys.UseCompactRows] ?: false,
            )
        }

    val nightscoutStatus: Flow<NightscoutStatus> =
        dataStore.data.map { preferences ->
            NightscoutStatus(
                lastSyncAt = preferences[Keys.NightscoutLastSyncAt]?.let(Instant::fromEpochMilliseconds),
                queueDepth = preferences[Keys.NightscoutQueueDepth] ?: 0,
                connectionState = preferences[Keys.NightscoutConnectionState]
                    ?.let { runCatching { NightscoutConnectionState.valueOf(it) }.getOrNull() }
                    ?: NightscoutConnectionState.Unknown,
            )
        }

    val notificationToggles: Flow<NotificationToggles> =
        dataStore.data.map { preferences ->
            NotificationToggles(
                mealReminder = preferences[Keys.NotifMealReminder] ?: false,
                nsFail = preferences[Keys.NotifNsFail] ?: false,
                lowConfidence = preferences[Keys.NotifLowConfidence] ?: false,
                estimateReady = preferences[Keys.NotifEstimateReady] ?: true,
            )
        }

    suspend fun updateGoal(field: String, value: String) {
        dataStore.edit { preferences ->
            when (field) {
                "dailyKcal" -> preferences[Keys.DailyKcal] = value.toIntOrNull() ?: return@edit
                "dailyCarbsG" -> preferences[Keys.DailyCarbsG] = value.toIntOrNull() ?: return@edit
                "weightKg" -> preferences[Keys.WeightKg] = value.toDoubleOrNull() ?: return@edit
            }
        }
    }

    suspend fun toggleNotification(key: String) {
        dataStore.edit { preferences ->
            val prefKey = when (key) {
                "meal_reminder" -> Keys.NotifMealReminder
                "ns_fail" -> Keys.NotifNsFail
                "low_confidence" -> Keys.NotifLowConfidence
                "estimate_ready" -> Keys.NotifEstimateReady
                else -> return@edit
            }
            preferences[prefKey] = !(preferences[prefKey] ?: false)
        }
    }

    private object Keys {
        val DailyKcal = intPreferencesKey("daily_kcal")
        val DailyCarbsG = intPreferencesKey("daily_carbs_g")
        val WeightKg = doublePreferencesKey("weight_kg")
        val GlucoseMode = stringPreferencesKey("glucose_mode")
        val UseCompactRows = booleanPreferencesKey("use_compact_rows")
        val NightscoutLastSyncAt = longPreferencesKey("nightscout_last_sync_at")
        val NightscoutQueueDepth = intPreferencesKey("nightscout_queue_depth")
        val NightscoutConnectionState = stringPreferencesKey("nightscout_connection_state")
        val NotifMealReminder = booleanPreferencesKey("notif_meal_reminder")
        val NotifNsFail = booleanPreferencesKey("notif_ns_fail")
        val NotifLowConfidence = booleanPreferencesKey("notif_low_confidence")
        val NotifEstimateReady = booleanPreferencesKey("notif_estimate_ready")
    }
}
