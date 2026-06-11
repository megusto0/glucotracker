package com.local.glucotracker.ui.feature.more

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.data.api.GoalsApi
import com.local.glucotracker.data.api.ScheduleApi
import com.local.glucotracker.data.auth.AuthRepository
import com.local.glucotracker.data.local.GlucotrackerDatabase
import com.local.glucotracker.data.local.PhotoStorage
import com.local.glucotracker.data.settings.NotificationToggles
import com.local.glucotracker.data.settings.SettingsStore
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.domain.model.UiPrefs
import com.local.glucotracker.domain.model.UserGoals
import com.local.glucotracker.domain.repository.OutboxRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import java.text.DecimalFormat
import java.text.DecimalFormatSymbols
import java.util.Locale
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.datetime.Clock
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

data class MoreState(
    val goals: UserGoals,
    val uiPrefs: UiPrefs,
    val cacheSizeLabel: String,
    val productCount: Int,
    val templateCount: Int,
    val outboxCount: Int,
    val outboxStuckCount: Int,
    val notifications: NotificationToggles,
    val rhythm: RhythmUi?,
)

data class RhythmUi(
    val anchorMinutes: Int?,
    val basis: String?,
    val hasOverride: Boolean,
    val windows: List<RhythmWindowUi>,
)

data class RhythmWindowUi(
    val label: String,
    val startMinute: Int,
    val endMinute: Int,
)

@HiltViewModel
class MoreViewModel @Inject constructor(
    private val outboxRepository: OutboxRepository,
    private val settingsStore: SettingsStore,
    private val database: GlucotrackerDatabase,
    private val authRepository: AuthRepository,
    private val scheduleApi: ScheduleApi,
    private val goalsApi: GoalsApi,
    @ApplicationContext private val context: Context,
) : ViewModel() {

    private val photoDir = File(context.filesDir, "photos")
    private val rhythm = MutableStateFlow<RhythmUi?>(null)
    private val cacheSizeRefresh = MutableStateFlow(0)

    private val cacheSizeFlow = cacheSizeRefresh.map {
        computeCacheSizeLabel()
    }

    private val outboxSummaryFlow = outboxRepository.observe().map { items ->
        OutboxSummary(
            count = items.size,
            stuckCount = items.count { item -> item.state == OutboxState.Stuck },
        )
    }

    val state = combine(
        settingsStore.userGoals,
        settingsStore.uiPrefs,
        settingsStore.notificationToggles,
        cacheSizeFlow,
        rhythm,
        database.cachedProductDao().observeAll().map { products -> products.size },
        database.cachedTemplateDao().observeAll().map { templates -> templates.size },
        outboxSummaryFlow,
    ) { args: Array<Any?> ->
        @Suppress("UNCHECKED_CAST")
        val outboxSummary = args[7] as OutboxSummary
        MoreState(
            goals = args[0] as UserGoals,
            uiPrefs = args[1] as UiPrefs,
            notifications = args[2] as NotificationToggles,
            cacheSizeLabel = args[3] as String,
            rhythm = args[4] as RhythmUi?,
            productCount = args[5] as Int,
            templateCount = args[6] as Int,
            outboxCount = outboxSummary.count,
            outboxStuckCount = outboxSummary.stuckCount,
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = MoreState(
            goals = UserGoals(dailyKcal = null, dailyProteinG = null, dailyCarbsG = null, dailyFatG = null, weightKg = null),
            uiPrefs = UiPrefs(glucoseMode = "raw", useCompactRows = false),
            cacheSizeLabel = "—",
            productCount = 0,
            templateCount = 0,
            outboxCount = 0,
            outboxStuckCount = 0,
            notifications = NotificationToggles(
                mealReminder = false,
                nsFail = false,
                lowConfidence = false,
                outboxStuck = true,
            ),
            rhythm = null,
        ),
    )

    init {
        refreshRhythm()
        syncGoalsFromBackend()
    }

    fun clearCache() {
        viewModelScope.launch {
            val today = Clock.System.now().toLocalDateTime(TimeZone.currentSystemDefault()).date
            database.cachedMealDao().pruneOlderThan(today)
            database.cachedProductDao().replaceAll(emptyList())
            database.cachedTemplateDao().replaceAll(emptyList())
            val outboxItems = firstOrNull(outboxRepository.observe()).orEmpty()
            val referenced = outboxItems.mapNotNull { item ->
                when (val kind = item.kind) {
                    is OutboxKind.CapturedMeal -> kind.localPhotoPath
                    else -> null
                }
            }.toSet()
            PhotoStorage.sweepOrphans(photoDir, referenced)
            cacheSizeRefresh.value += 1
        }
    }

    fun updateGoal(field: String, value: String) {
        viewModelScope.launch {
            settingsStore.updateGoal(field, value)
            settingsStore.completeGoalsSetup()
            pushGoalsToBackend()
        }
    }

    fun saveGoals(
        dailyKcal: String,
        dailyProteinG: String,
        dailyCarbsG: String,
        dailyFatG: String,
        weightKg: String,
    ) {
        viewModelScope.launch {
            settingsStore.updateGoals(
                dailyKcal = dailyKcal,
                dailyProteinG = dailyProteinG,
                dailyCarbsG = dailyCarbsG,
                dailyFatG = dailyFatG,
                weightKg = weightKg,
            )
            settingsStore.completeGoalsSetup()
            pushGoalsToBackend()
        }
    }

    fun toggleNotification(key: String) {
        viewModelScope.launch {
            settingsStore.toggleNotification(key)
        }
    }

    fun refreshRhythm() {
        viewModelScope.launch {
            rhythm.value = runCatching { scheduleApi.getSchedule().toRhythmUi() }.getOrNull()
        }
    }

    fun setRhythmOverride(value: String) {
        val minutes = parseClockMinutes(value) ?: return
        viewModelScope.launch {
            rhythm.value = runCatching {
                scheduleApi.setOverride(minutes).toRhythmUi()
            }.getOrNull() ?: rhythm.value
        }
    }

    private fun parseClockMinutes(value: String): Int? {
        val trimmed = value.trim()
        val (hour, minute) = if (trimmed.contains(':')) {
            val parts = trimmed.split(':')
            if (parts.size != 2) return null
            parts[0].toIntOrNull() to parts[1].toIntOrNull()
        } else {
            val digits = trimmed.filter { it.isDigit() }
            if (digits.isEmpty()) return null
            when (digits.length) {
                1, 2 -> digits.toIntOrNull() to 0
                3 -> digits.take(1).toIntOrNull() to digits.takeLast(2).toIntOrNull()
                4 -> digits.take(2).toIntOrNull() to digits.takeLast(2).toIntOrNull()
                else -> return null
            }
        }
        val safeHour = hour?.takeIf { it in 0..23 } ?: return null
        val safeMinute = minute?.takeIf { it in 0..59 } ?: return null
        return safeHour * 60 + safeMinute
    }

    fun clearRhythmOverride() {
        viewModelScope.launch {
            rhythm.value = runCatching { scheduleApi.clearOverride().toRhythmUi() }
                .getOrNull() ?: rhythm.value
        }
    }

    fun logout() {
        viewModelScope.launch {
            authRepository.logout()
        }
    }

    private fun syncGoalsFromBackend() {
        viewModelScope.launch {
            runCatching {
                val remote = goalsApi.getGoals()
                settingsStore.syncGoalsFromBackend(
                    dailyKcal = remote.kcalGoalPerDay,
                    dailyProteinG = remote.proteinGoalGPerDay,
                    dailyCarbsG = remote.carbGoalGPerDay,
                    dailyFatG = remote.fatGoalGPerDay,
                    goalsSetupCompleted = remote.goalsSetupCompleted ?: false,
                )
            }
        }
    }

    private suspend fun pushGoalsToBackend() {
        val goals = settingsStore.userGoals.firstOrNull() ?: return
        runCatching {
            goalsApi.updateGoals(
                kcalGoalPerDay = goals.dailyKcal,
                proteinGoalGPerDay = goals.dailyProteinG,
                carbGoalGPerDay = goals.dailyCarbsG,
                fatGoalGPerDay = goals.dailyFatG,
                goalsSetupCompleted = true,
            )
        }
    }

    private fun computeCacheSizeLabel(): String {
        val photoSize = photoDir.walkTopDown().filter { it.isFile }.sumOf { it.length() }
        val dbPath = database.openHelper.writableDatabase.path
        val dbSize = dbPath?.let { File(it).length() } ?: 0L
        return formatBytes(photoSize + dbSize)
    }

    private fun formatBytes(bytes: Long): String {
        val df = DecimalFormat("#,##0.#", DecimalFormatSymbols(Locale("ru")))
        return when {
            bytes >= 1_073_741_824 -> "${df.format(bytes.toDouble() / 1_073_741_824)} ГБ"
            bytes >= 1_048_576 -> "${df.format(bytes.toDouble() / 1_048_576)} МБ"
            bytes >= 1_024 -> "${df.format(bytes.toDouble() / 1_024)} КБ"
            else -> "$bytes Б"
        }
    }

    private suspend fun <T> firstOrNull(flow: kotlinx.coroutines.flow.Flow<T>): T? =
        flow.firstOrNull()

}

private data class OutboxSummary(
    val count: Int,
    val stuckCount: Int,
)

private fun com.local.glucotracker.generated.model.ScheduleResponse.toRhythmUi(): RhythmUi =
    RhythmUi(
        anchorMinutes = effectiveAnchorMinutes,
        basis = basis,
        hasOverride = userOverrideMinutes != null,
        windows = windows.map { window ->
            RhythmWindowUi(
                label = window.label,
                startMinute = window.startMinute,
                endMinute = window.endMinute,
            )
        },
    )
