package com.local.glucotracker.ui.feature.more

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.data.local.GlucotrackerDatabase
import com.local.glucotracker.data.local.PhotoStorage
import com.local.glucotracker.data.settings.NotificationToggles
import com.local.glucotracker.data.settings.SettingsStore
import com.local.glucotracker.domain.model.NightscoutConnectionState
import com.local.glucotracker.domain.model.NightscoutStatus
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.UiPrefs
import com.local.glucotracker.domain.model.UserGoals
import com.local.glucotracker.domain.repository.NightscoutRepository
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
    val nightscoutStatus: NightscoutStatus,
    val isNightscoutRefreshing: Boolean,
    val goals: UserGoals,
    val uiPrefs: UiPrefs,
    val cacheSizeLabel: String,
    val notifications: NotificationToggles,
)

@HiltViewModel
class MoreViewModel @Inject constructor(
    private val outboxRepository: OutboxRepository,
    private val nightscoutRepository: NightscoutRepository,
    private val settingsStore: SettingsStore,
    private val database: GlucotrackerDatabase,
    @ApplicationContext private val context: Context,
) : ViewModel() {

    private val photoDir = File(context.filesDir, "photos")
    private val nightscoutStatus = MutableStateFlow(emptyNightscoutStatus())
    private val isNightscoutRefreshing = MutableStateFlow(false)

    private val cacheSizeFlow = settingsStore.uiPrefs.map {
        computeCacheSizeLabel()
    }

    init {
        refreshNightscout()
    }

    val state = kotlinx.coroutines.flow.combine(
        nightscoutStatus,
        isNightscoutRefreshing,
        settingsStore.userGoals,
        settingsStore.uiPrefs,
        settingsStore.notificationToggles,
        cacheSizeFlow,
    ) { args: Array<Any> ->
        @Suppress("UNCHECKED_CAST")
        MoreState(
            nightscoutStatus = args[0] as NightscoutStatus,
            isNightscoutRefreshing = args[1] as Boolean,
            goals = args[2] as UserGoals,
            uiPrefs = args[3] as UiPrefs,
            notifications = args[4] as NotificationToggles,
            cacheSizeLabel = args[5] as String,
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = MoreState(
            nightscoutStatus = emptyNightscoutStatus(),
            isNightscoutRefreshing = false,
            goals = UserGoals(dailyKcal = null, dailyCarbsG = null, weightKg = null),
            uiPrefs = UiPrefs(glucoseMode = "raw", useCompactRows = false),
            cacheSizeLabel = "—",
            notifications = NotificationToggles(
                mealReminder = false,
                nsFail = false,
                lowConfidence = false,
                estimateReady = true,
            ),
        ),
    )

    fun refreshNightscout() {
        viewModelScope.launch {
            loadNightscoutStatus {
                nightscoutRepository.dayStatus(currentLocalDate()).toStatus()
            }
        }
    }

    fun syncNightscoutNow() {
        viewModelScope.launch {
            loadNightscoutStatus {
                nightscoutRepository.syncToday(currentLocalDate()).toStatus()
            }
        }
    }

    fun clearCache() {
        viewModelScope.launch {
            val today = Clock.System.now().toLocalDateTime(TimeZone.currentSystemDefault()).date
            database.cachedMealDao().pruneOlderThan(today)
            database.cachedGlucoseDao().pruneOlderThan(Clock.System.now())
            database.cachedProductDao().replaceAll(emptyList())
            database.cachedTemplateDao().replaceAll(emptyList())
            val outboxItems = firstOrNull(outboxRepository.observe()).orEmpty()
            val referenced = outboxItems.mapNotNull { item ->
                when (val kind = item.kind) {
                    is OutboxKind.PhotoEstimateRequest -> kind.localPhotoPath
                    else -> null
                }
            }.toSet()
            PhotoStorage.sweepOrphans(photoDir, referenced)
        }
    }

    fun updateGoal(field: String, value: String) {
        viewModelScope.launch {
            settingsStore.updateGoal(field, value)
        }
    }

    fun toggleNotification(key: String) {
        viewModelScope.launch {
            settingsStore.toggleNotification(key)
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

    private suspend fun loadNightscoutStatus(block: suspend () -> NightscoutStatus) {
        isNightscoutRefreshing.value = true
        val current = nightscoutStatus.value
        nightscoutStatus.value = runCatching { block() }
            .getOrElse {
                runCatching { nightscoutRepository.status() }
                    .getOrElse { current.copy(connectionState = NightscoutConnectionState.Disconnected) }
            }
        isNightscoutRefreshing.value = false
    }

}

private fun com.local.glucotracker.domain.model.NightscoutDayStatus.toStatus(): NightscoutStatus =
    NightscoutStatus(
        lastSyncAt = lastSyncAt,
        queueDepth = unsyncedMealsCount + failedMealsCount,
        connectionState = when {
            !configured -> NightscoutConnectionState.Unknown
            connected -> NightscoutConnectionState.Connected
            else -> NightscoutConnectionState.Disconnected
        },
    )

private fun emptyNightscoutStatus(): NightscoutStatus =
    NightscoutStatus(
        lastSyncAt = null,
        queueDepth = 0,
        connectionState = NightscoutConnectionState.Unknown,
    )

private fun currentLocalDate() =
    Clock.System.now().toLocalDateTime(TimeZone.currentSystemDefault()).date
