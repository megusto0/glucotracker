package com.local.glucotracker.data.settings

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.doublePreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.local.glucotracker.domain.model.UiPrefs
import com.local.glucotracker.domain.model.StatsPeriod
import com.local.glucotracker.domain.model.UserGoals
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

data class NotificationToggles(
    val mealReminder: Boolean,
    val nsFail: Boolean,
    val lowConfidence: Boolean,
    val outboxStuck: Boolean = false,
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
                dailyProteinG = preferences[Keys.DailyProteinG],
                dailyCarbsG = preferences[Keys.DailyCarbsG],
                dailyFatG = preferences[Keys.DailyFatG],
                weightKg = preferences[Keys.WeightKg],
                goalsSetupCompleted = preferences[Keys.GoalsSetupCompleted] ?: false,
            )
        }

    val uiPrefs: Flow<UiPrefs> =
        dataStore.data.map { preferences ->
            UiPrefs(
                glucoseMode = preferences[Keys.GlucoseMode] ?: "raw",
                useCompactRows = preferences[Keys.UseCompactRows] ?: false,
            )
        }

    val notificationToggles: Flow<NotificationToggles> =
        dataStore.data.map { preferences ->
            NotificationToggles(
                mealReminder = preferences[Keys.NotifMealReminder] ?: false,
                nsFail = preferences[Keys.NotifNsFail] ?: false,
                lowConfidence = preferences[Keys.NotifLowConfidence] ?: false,
                outboxStuck = preferences[Keys.NotifOutboxStuck] ?: false,
            )
        }

    val statsPeriod: Flow<StatsPeriod> =
        dataStore.data.map { preferences ->
            when (preferences[Keys.StatsPeriod]) {
                StatsPeriod.Week.name -> StatsPeriod.Week
                StatsPeriod.Month.name -> StatsPeriod.Month
                else -> StatsPeriod.Fortnight
            }
        }

    val composeSheetOpenCount: Flow<Int> =
        dataStore.data.map { preferences -> preferences[Keys.ComposeSheetOpenCount] ?: 0 }

    suspend fun updateGoal(field: String, value: String) {
        dataStore.edit { preferences ->
            when (field) {
                "dailyKcal" -> preferences[Keys.DailyKcal] = value.toIntOrNull() ?: return@edit
                "dailyProteinG" -> preferences[Keys.DailyProteinG] = value.toIntOrNull() ?: return@edit
                "dailyCarbsG" -> preferences[Keys.DailyCarbsG] = value.toIntOrNull() ?: return@edit
                "dailyFatG" -> preferences[Keys.DailyFatG] = value.toIntOrNull() ?: return@edit
                "weightKg" -> preferences[Keys.WeightKg] = value.toDoubleOrNull() ?: return@edit
            }
        }
    }

    suspend fun updateGoals(
        dailyKcal: String,
        dailyProteinG: String,
        dailyCarbsG: String,
        dailyFatG: String,
        weightKg: String,
    ) {
        dataStore.edit { preferences ->
            preferences.writeIntOrClear(Keys.DailyKcal, dailyKcal)
            preferences.writeIntOrClear(Keys.DailyProteinG, dailyProteinG)
            preferences.writeIntOrClear(Keys.DailyCarbsG, dailyCarbsG)
            preferences.writeIntOrClear(Keys.DailyFatG, dailyFatG)
            val normalizedWeight = weightKg.trim().replace(',', '.')
            val parsedWeight = normalizedWeight.toDoubleOrNull()
            if (weightKg.isBlank()) {
                preferences.remove(Keys.WeightKg)
            } else if (parsedWeight != null && parsedWeight > 0.0) {
                preferences[Keys.WeightKg] = parsedWeight
            }
        }
    }

    suspend fun completeGoalsSetup() {
        dataStore.edit { preferences ->
            preferences[Keys.GoalsSetupCompleted] = true
        }
    }

    suspend fun syncGoalsFromBackend(
        dailyKcal: Int?,
        dailyProteinG: Int?,
        dailyCarbsG: Int?,
        dailyFatG: Int?,
        goalsSetupCompleted: Boolean,
    ) {
        dataStore.edit { preferences ->
            dailyKcal?.let { preferences[Keys.DailyKcal] = it }
            dailyProteinG?.let { preferences[Keys.DailyProteinG] = it }
            dailyCarbsG?.let { preferences[Keys.DailyCarbsG] = it }
            dailyFatG?.let { preferences[Keys.DailyFatG] = it }
            val hasRemoteDailyGoal = listOf(
                dailyKcal,
                dailyProteinG,
                dailyCarbsG,
                dailyFatG,
            ).any { goal -> goal != null && goal > 0 }
            val setupCompleted =
                goalsSetupCompleted ||
                hasRemoteDailyGoal ||
                (preferences[Keys.GoalsSetupCompleted] ?: false)
            preferences[Keys.GoalsSetupCompleted] = setupCompleted
        }
    }

    suspend fun toggleNotification(key: String) {
        dataStore.edit { preferences ->
            val prefKey = when (key) {
                "meal_reminder" -> Keys.NotifMealReminder
                "ns_fail" -> Keys.NotifNsFail
                "low_confidence" -> Keys.NotifLowConfidence
                "outbox_stuck" -> Keys.NotifOutboxStuck
                else -> return@edit
            }
            preferences[prefKey] = !(preferences[prefKey] ?: false)
        }
    }

    suspend fun updateStatsPeriod(period: StatsPeriod) {
        dataStore.edit { preferences ->
            preferences[Keys.StatsPeriod] = period.name
        }
    }

    suspend fun incrementComposeSheetOpenCount() {
        dataStore.edit { preferences ->
            preferences[Keys.ComposeSheetOpenCount] =
                (preferences[Keys.ComposeSheetOpenCount] ?: 0) + 1
        }
    }

    private object Keys {
        val DailyKcal = intPreferencesKey("daily_kcal")
        val DailyProteinG = intPreferencesKey("daily_protein_g")
        val DailyCarbsG = intPreferencesKey("daily_carbs_g")
        val DailyFatG = intPreferencesKey("daily_fat_g")
        val WeightKg = doublePreferencesKey("weight_kg")
        val GoalsSetupCompleted = booleanPreferencesKey("goals_setup_completed")
        val GlucoseMode = stringPreferencesKey("glucose_mode")
        val UseCompactRows = booleanPreferencesKey("use_compact_rows")
        val NotifMealReminder = booleanPreferencesKey("notif_meal_reminder")
        val NotifNsFail = booleanPreferencesKey("notif_ns_fail")
        val NotifLowConfidence = booleanPreferencesKey("notif_low_confidence")
        val NotifOutboxStuck = booleanPreferencesKey("notif_outbox_stuck")
        val StatsPeriod = stringPreferencesKey("stats_period")
        val ComposeSheetOpenCount = intPreferencesKey("compose_sheet_open_count")
    }
}

private fun androidx.datastore.preferences.core.MutablePreferences.writeIntOrClear(
    key: androidx.datastore.preferences.core.Preferences.Key<Int>,
    value: String,
) {
    val trimmed = value.trim()
    if (trimmed.isBlank()) {
        remove(key)
        return
    }
    val parsed = trimmed.toIntOrNull()
    if (parsed != null && parsed > 0) {
        this[key] = parsed
    }
}
