package com.local.glucotracker.ui.glucose

import androidx.compose.foundation.layout.Column
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import com.local.glucotracker.R
import com.local.glucotracker.healthconnect.DebugHealthConnectSync
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.feature.more.SettingsGlyphKind
import com.local.glucotracker.ui.feature.more.SettingsGroup
import com.local.glucotracker.ui.feature.more.SettingsRow
import com.local.glucotracker.ui.feature.more.SettingsSection
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.delay

/**
 * Health Connect settings, in the flavor that has Health Connect.
 *
 * This lived in the shared More screen and reached its own flavor's syncer
 * through `Class.forName`, which is what the surface interface exists to avoid
 * — and it put `HealthConnectSyncBridge` in the food binary, where the build's
 * own guard against glucose classes had been failing over it unnoticed.
 * Nothing here is reflective any more.
 */
@Composable
internal fun MoreHealthConnectSurface() {
    if (!DebugHealthConnectSync.isAvailable()) return

    var isRunning by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf(HcSyncStatus()) }
    var sent by remember { mutableStateOf(0) }

    LaunchedEffect(Unit) {
        status = lastSyncStatus()
        DebugHealthConnectSync.refreshLatestHeartRate()
        status = lastSyncStatus()
        if (DebugHealthConnectSync.isSyncRunning()) {
            isRunning = true
        }
    }
    LaunchedEffect(isRunning) {
        if (!isRunning) return@LaunchedEffect
        // Polls every half second and reads the running total, so a sync that
        // takes minutes shows movement instead of one frozen line.
        while (DebugHealthConnectSync.isSyncRunning()) {
            sent = DebugHealthConnectSync.getSyncProgressRecords()
            delay(500)
        }
        status = lastSyncStatus()
        sent = 0
        isRunning = false
    }

    MoreHealthConnectContent(
        status = status,
        isRunning = isRunning,
        sent = sent,
        onSync = {
            DebugHealthConnectSync.forceSyncNow()
            isRunning = true
        },
    )
}

/**
 * The section without its live state, so a snapshot can render it.
 *
 * The fake surface Paparazzi uses returns Unit for every gluco section, so
 * moving this behind the interface would have silently dropped it from the
 * "Ещё" golden — a whole section gone with no test noticing. Splitting the
 * state off keeps the layout under test.
 */
@Composable
internal fun MoreHealthConnectContent(
    status: HcSyncStatus,
    isRunning: Boolean,
    sent: Int,
    onSync: () -> Unit,
) {
    val latestHeartRate = if (
        status.latestHeartRateBpm > 0L && status.latestHeartRateAt > 0L
    ) {
        stringResource(
            R.string.more_hc_latest_heart_rate,
            status.latestHeartRateBpm,
            status.latestHeartRateAt.timeLabel(),
        )
    } else {
        null
    }
    val description = when {
        isRunning && sent > 0 -> stringResource(R.string.more_hc_sync_run_progress, sent)
        isRunning -> stringResource(R.string.more_hc_sync_run_desc)
        status.error != null -> stringResource(R.string.more_hc_status_error)
        status.lastSyncAt <= 0L -> stringResource(R.string.more_health_connect_hint)
        status.skipped > 0 -> stringResource(
            R.string.more_hc_status_partial,
            status.lastSyncAt.timeLabel(),
        )
        // Records Health Connect itself cannot hand over are not a sync
        // failure, and saying "часть данных не синхронизирована" about them
        // reported a permanent, unfixable fault on every single run.
        status.unreadable > 0 -> stringResource(
            R.string.more_hc_status_unreadable,
            status.records,
            status.lastSyncAt.timeLabel(),
        )
        status.records > 0 -> stringResource(
            R.string.more_hc_status_records,
            status.records,
            status.lastSyncAt.timeLabel(),
        )
        else -> stringResource(
            R.string.more_hc_status_uptodate,
            status.lastSyncAt.timeLabel(),
        )
    }

    SettingsSection(title = stringResource(R.string.more_health_connect_title)) {
        SettingsGroup {
            SettingsRow(
                title = stringResource(R.string.more_health_connect_title),
                description = description,
                glyph = SettingsGlyphKind.Signal,
                actionBelow = true,
                action = {
                    GTOutlineButton(
                        text = stringResource(
                            when {
                                isRunning -> R.string.more_hc_sync_running
                                status.lastSyncAt <= 0L -> R.string.more_health_connect_connect
                                else -> R.string.more_hc_sync_now
                            },
                        ),
                        meta = latestHeartRate,
                        enabled = !isRunning,
                        onClick = onSync,
                    )
                },
            )
        }
    }
}

internal data class HcSyncStatus(
    val lastSyncAt: Long = -1L,
    val records: Int = 0,
    val deleted: Int = 0,
    val skipped: Int = 0,
    val unreadable: Int = 0,
    val error: String? = null,
    val latestHeartRateBpm: Long = -1L,
    val latestHeartRateAt: Long = -1L,
)

/** Straight calls now: the surface lives in the flavor that owns the class. */
private fun lastSyncStatus(): HcSyncStatus = HcSyncStatus(
    lastSyncAt = DebugHealthConnectSync.getLastSyncAtMillis(),
    records = DebugHealthConnectSync.getLastSyncRecords(),
    deleted = DebugHealthConnectSync.getLastSyncDeleted(),
    skipped = DebugHealthConnectSync.getLastSyncSkipped(),
    unreadable = DebugHealthConnectSync.getLastSyncUnreadable(),
    error = DebugHealthConnectSync.getLastSyncError(),
    latestHeartRateBpm = DebugHealthConnectSync.getLatestHeartRateBpm(),
    latestHeartRateAt = DebugHealthConnectSync.getLatestHeartRateAtMillis(),
)

private fun Long.timeLabel(): String =
    Instant.ofEpochMilli(this)
        .atZone(ZoneId.systemDefault())
        .format(DateTimeFormatter.ofPattern("HH:mm"))

