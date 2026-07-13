package com.local.glucotracker.data.settings

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

data class GlucoAlarmToggles(
    val low: Boolean = true,
    val high: Boolean = true,
    val sensorSignalLoss: Boolean = true,
)

private val Context.glucoSettingsDataStore by preferencesDataStore(
    name = "gluco_settings",
)

@Singleton
class GlucoSettingsStore @Inject constructor(
    @ApplicationContext context: Context,
) {
    private val dataStore = context.glucoSettingsDataStore

    val alarmToggles: Flow<GlucoAlarmToggles> =
        dataStore.data.map { preferences ->
            GlucoAlarmToggles(
                low = preferences[Keys.LowAlarm] ?: true,
                high = preferences[Keys.HighAlarm] ?: true,
                sensorSignalLoss = preferences[Keys.SensorSignalLoss] ?: true,
            )
        }

    val normalizedGlucoseDisplay: Flow<Boolean> =
        dataStore.data.map { preferences ->
            preferences[Keys.NormalizedGlucoseDisplay] ?: false
        }

    suspend fun toggleNormalizedGlucoseDisplay() {
        dataStore.edit { preferences ->
            preferences[Keys.NormalizedGlucoseDisplay] =
                !(preferences[Keys.NormalizedGlucoseDisplay] ?: false)
        }
    }

    suspend fun toggleAlarm(key: String) {
        dataStore.edit { preferences ->
            val prefKey = when (key) {
                "low" -> Keys.LowAlarm
                "high" -> Keys.HighAlarm
                "sensor_signal_loss" -> Keys.SensorSignalLoss
                else -> return@edit
            }
            preferences[prefKey] = !(preferences[prefKey] ?: true)
        }
    }

    private object Keys {
        val LowAlarm = booleanPreferencesKey("low_alarm")
        val HighAlarm = booleanPreferencesKey("high_alarm")
        val SensorSignalLoss = booleanPreferencesKey("sensor_signal_loss")
        val NormalizedGlucoseDisplay = booleanPreferencesKey("normalized_glucose_display")
    }
}
