package com.local.glucotracker.ui.glucose

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.local.glucotracker.R
import com.local.glucotracker.healthconnect.DebugHealthConnectSync
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.feature.more.SettingsGlyphKind
import com.local.glucotracker.ui.feature.more.SettingsGroup
import com.local.glucotracker.ui.feature.more.SettingsRow
import com.local.glucotracker.ui.feature.more.SettingsSection
import com.local.glucotracker.ui.feature.more.SettingsSwitch
import com.local.glucotracker.wearable.HelioBridgeClient
import com.local.glucotracker.wearable.HelioBridgeStatus
import java.time.Instant
import java.time.LocalDate
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

    val context = LocalContext.current
    var isRunning by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf(HcSyncStatus()) }
    var sent by remember { mutableStateOf(0) }
    var now by remember { mutableStateOf(System.currentTimeMillis()) }
    var bridgeStatus by remember {
        mutableStateOf(
            HelioBridgeStatus(installed = HelioBridgeClient.isInstalled(context)),
        )
    }

    DisposableEffect(context) {
        val receiver = HelioBridgeClient.register(context) { bridgeStatus = it }
        if (bridgeStatus.installed) {
            HelioBridgeClient.requestStatus(context)
        }
        onDispose { context.unregisterReceiver(receiver) }
    }

    LaunchedEffect(Unit) {
        status = lastSyncStatus()
        DebugHealthConnectSync.refreshLatestHeartRate()
        status = lastSyncStatus()
        if (DebugHealthConnectSync.isSyncRunning()) {
            isRunning = true
        }
        // The upload after a Bridge batch runs in the background; re-read its
        // result while the screen is open so the steps do not go stale.
        while (true) {
            delay(StatusRefreshMillis)
            now = System.currentTimeMillis()
            status = lastSyncStatus()
            if (DebugHealthConnectSync.isSyncRunning()) isRunning = true
        }
    }
    LaunchedEffect(bridgeStatus.phase) {
        if (bridgeStatus.phase == "complete") {
            DebugHealthConnectSync.refreshLatestHeartRate()
            status = lastSyncStatus()
            now = System.currentTimeMillis()
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
    val uploadNow = {
        DebugHealthConnectSync.forceSyncNow()
        isRunning = true
    }
    MoreWearableBridgeContent(
        bridge = bridgeStatus,
        pipeline = syncPipeline(
            bridge = bridgeStatus,
            upload = status,
            uploading = isRunning,
            uploadedSoFar = sent,
            now = now,
        ),
        onSync = {
            if (bridgeStatus.error == "health_connect_required") {
                HelioBridgeClient.openHealthConnectSettings(context)
            } else if (bridgeStatus.installed && bridgeStatus.error != "not_paired") {
                bridgeStatus = bridgeStatus.copy(phase = "connecting", error = null)
                HelioBridgeClient.sync(context)
            } else if (bridgeStatus.installed) {
                HelioBridgeClient.openBridge(context)
            }
        },
        onUpload = { if (!isRunning) uploadNow() },
        onOpen = { HelioBridgeClient.openBridge(context) },
        onAutoSyncToggle = {
            val enabled = !bridgeStatus.autoSyncEnabled
            bridgeStatus = bridgeStatus.copy(autoSyncEnabled = enabled)
            HelioBridgeClient.setAutoSync(context, enabled)
        },
    )

    // With Bridge the pipeline covers the upload; the plain section stays for
    // connecting Health Connect the first time and for phones without Bridge.
    if (!bridgeStatus.installed || status.lastSyncAt <= 0L) {
        MoreHealthConnectContent(
            status = status,
            isRunning = isRunning,
            sent = sent,
            onSync = uploadNow,
        )
    }
}

private const val StatusRefreshMillis = 5_000L

@Composable
private fun MoreWearableBridgeContent(
    bridge: HelioBridgeStatus,
    pipeline: SyncPipeline,
    onSync: () -> Unit,
    onUpload: () -> Unit,
    onOpen: () -> Unit,
    onAutoSyncToggle: () -> Unit,
) {
    val battery = if (bridge.battery in 0..100) {
        stringResource(R.string.more_wearable_battery, bridge.battery)
    } else {
        ""
    }
    val description = when {
        !bridge.installed -> stringResource(R.string.more_wearable_not_installed)
        bridge.connected -> stringResource(R.string.more_wearable_connected, battery)
        else -> stringResource(R.string.more_wearable_disconnected)
    }

    SettingsSection(title = stringResource(R.string.more_wearable_section)) {
        SettingsGroup {
            SettingsRow(
                title = stringResource(R.string.more_wearable_title),
                description = description,
                glyph = SettingsGlyphKind.Signal,
                onClick = if (bridge.installed && !bridge.isBusy) onOpen else null,
            )
            if (bridge.installed) {
                GTHairlineDivider()
                SyncPipelineBlock(
                    pipeline = pipeline,
                    syncLabel = stringResource(
                        when {
                            bridge.isBusy -> R.string.more_wearable_syncing
                            bridge.error == "not_paired" -> R.string.more_wearable_open
                            bridge.error == "health_connect_required" ->
                                R.string.more_wearable_open
                            else -> R.string.more_wearable_sync
                        },
                    ),
                    syncEnabled = !bridge.isBusy,
                    onSync = onSync,
                    onUpload = onUpload,
                )
                GTHairlineDivider()
                SettingsRow(
                    title = stringResource(R.string.more_wearable_auto_title),
                    description = if (bridge.autoSyncEnabled) {
                        stringResource(
                            R.string.more_wearable_auto_enabled,
                            bridge.autoSyncIntervalMinutes,
                        )
                    } else {
                        stringResource(R.string.more_wearable_auto_disabled)
                    },
                    action = {
                        SettingsSwitch(
                            checked = bridge.autoSyncEnabled,
                            accent = GT.colors.info,
                            onToggle = onAutoSyncToggle,
                        )
                    },
                    onClick = onAutoSyncToggle,
                )
            }
        }
    }
}

/**
 * Headline plus one line per hop. The headline names the first hop that is
 * failing or stalled, so "no heart rate on the server" points at its cause.
 */
@Composable
internal fun SyncPipelineBlock(
    pipeline: SyncPipeline,
    syncLabel: String,
    syncEnabled: Boolean,
    onSync: () -> Unit,
    onUpload: () -> Unit,
) {
    val headline = pipeline.headline
    val headlineText = if (headline == null) {
        stringResource(R.string.more_sync_all_ok, pipeline.strap.headlineTime().dayTimeLabel())
    } else {
        syncDetailText(headline.detail)
    }
    val names = listOf(
        stringResource(R.string.more_sync_step_strap),
        stringResource(R.string.more_sync_step_hc),
        stringResource(R.string.more_sync_step_server),
    )
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 14.dp, vertical = 12.dp),
    ) {
        // The server step's text says "нажмите, чтобы отправить"; when it is the
        // headline, the headline has to honour that too.
        val headlineUploads = headline != null && headline === pipeline.server &&
            headline.state != SyncStepState.Working
        Text(
            text = headlineText,
            modifier = if (headlineUploads) {
                Modifier.clickable(role = Role.Button, onClick = onUpload)
            } else {
                Modifier
            },
            color = headline?.state?.textColor() ?: GT.colors.ink,
            style = GT.type.sansBody.copy(fontSize = 14.sp),
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        Spacer(Modifier.height(10.dp))
        pipeline.steps.forEachIndexed { index, step ->
            val isServer = index == pipeline.steps.lastIndex
            SyncStepRow(
                name = names[index],
                step = step,
                first = index == 0,
                last = isServer,
                onClick = if (isServer && step.state != SyncStepState.Working) onUpload else null,
            )
        }
        Spacer(Modifier.height(6.dp))
        GTOutlineButton(
            text = syncLabel,
            enabled = syncEnabled,
            onClick = onSync,
        )
    }
}

@Composable
private fun SyncStepRow(
    name: String,
    step: SyncStep,
    first: Boolean,
    last: Boolean,
    onClick: (() -> Unit)?,
) {
    val detail = syncDetailText(step.detail)
    val time = if (step.at > 0L) step.at.dayTimeLabel() else ""
    val dotColor = step.state.dotColor()
    val lineColor = GT.colors.hairline2
    val a11y = stringResource(R.string.more_sync_step_description, name, detail, time)
    val clickModifier = if (onClick != null) {
        Modifier.clickable(role = Role.Button, onClick = onClick)
    } else {
        Modifier
    }
    Row(
        modifier = clickModifier
            .fillMaxWidth()
            .heightIn(min = GT.space.touch)
            .semantics(mergeDescendants = true) { contentDescription = a11y },
        verticalAlignment = Alignment.Top,
    ) {
        // Dot and connector: the three hops read as one line top to bottom.
        Box(
            modifier = Modifier
                .width(14.dp)
                .heightIn(min = GT.space.touch)
                .drawBehind {
                    val x = size.width / 2f
                    val dotY = 8.dp.toPx()
                    val stroke = 1.dp.toPx()
                    if (!first) drawLine(lineColor, Offset(x, 0f), Offset(x, dotY), stroke)
                    if (!last) drawLine(lineColor, Offset(x, dotY), Offset(x, size.height), stroke)
                    drawCircle(dotColor, radius = 4.dp.toPx(), center = Offset(x, dotY))
                },
        )
        Spacer(Modifier.width(10.dp))
        Column(
            modifier = Modifier
                .weight(1f)
                .padding(bottom = 8.dp),
        ) {
            Text(
                text = name,
                color = GT.colors.muted,
                style = GT.type.sansLabel.copy(fontSize = 11.sp),
                maxLines = 1,
            )
            Text(
                text = detail,
                modifier = Modifier.padding(top = 2.dp),
                color = step.state.textColor(),
                style = GT.type.sansBody.copy(fontSize = 13.sp),
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
        }
        if (time.isNotEmpty()) {
            Spacer(Modifier.width(8.dp))
            Text(
                text = time,
                color = GT.colors.muted,
                style = GT.type.monoLabel.copy(fontSize = 11.sp),
                maxLines = 1,
            )
        }
    }
}

@Composable
private fun SyncStepState.dotColor(): Color = when (this) {
    SyncStepState.Ok -> GT.colors.good
    SyncStepState.Working -> GT.colors.info
    SyncStepState.Waiting -> GT.colors.warn
    SyncStepState.Failed -> GT.colors.bad
    SyncStepState.Unknown -> GT.colors.hairline2
}

@Composable
private fun SyncStepState.textColor(): Color = when (this) {
    SyncStepState.Waiting -> GT.colors.warn
    SyncStepState.Failed -> GT.colors.bad
    else -> GT.colors.ink
}

/** Time behind "всё работает": the newest strap data, not the transfer. */
private fun SyncStep.headlineTime(): Long = (detail as? SyncDetail.DataThrough)?.at ?: at

@Composable
private fun syncDetailText(detail: SyncDetail): String = when (detail) {
    SyncDetail.BridgeMissing -> stringResource(R.string.more_sync_bridge_missing)
    SyncDetail.NotPaired -> stringResource(R.string.more_sync_not_paired)
    SyncDetail.HealthConnectRequired -> stringResource(R.string.more_sync_hc_required)
    SyncDetail.ConnectTimeout -> stringResource(R.string.more_sync_connect_timeout)
    SyncDetail.BridgeFailed -> stringResource(R.string.more_sync_bridge_failed)
    SyncDetail.Connecting -> stringResource(R.string.more_sync_connecting)
    SyncDetail.Fetching -> stringResource(R.string.more_sync_fetching)
    SyncDetail.Exporting -> stringResource(R.string.more_sync_exporting)
    SyncDetail.NoStrapData -> stringResource(R.string.more_sync_no_strap_data)
    is SyncDetail.DataThrough ->
        stringResource(R.string.more_sync_data_through, detail.at.dayTimeLabel())
    is SyncDetail.StrapSilent ->
        stringResource(R.string.more_sync_strap_silent, detail.since.dayTimeLabel())
    SyncDetail.NoHeartRate -> stringResource(R.string.more_sync_no_heart_rate)
    is SyncDetail.HeartRate -> stringResource(R.string.more_sync_heart_rate, detail.bpm)
    is SyncDetail.HealthConnectBehind ->
        stringResource(R.string.more_sync_hc_behind, detail.since.dayTimeLabel())
    SyncDetail.NeverUploaded -> stringResource(R.string.more_sync_never_uploaded)
    is SyncDetail.Uploading -> if (detail.sent > 0) {
        stringResource(R.string.more_hc_sync_run_progress, detail.sent)
    } else {
        stringResource(R.string.more_hc_sync_run_desc)
    }
    is SyncDetail.UploadFailed -> stringResource(R.string.more_sync_upload_failed, detail.error)
    SyncDetail.UploadPending -> stringResource(R.string.more_sync_upload_pending)
    is SyncDetail.Uploaded -> stringResource(R.string.more_sync_uploaded, detail.records)
    SyncDetail.UpToDate -> stringResource(R.string.more_sync_up_to_date)
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

/** "12:48" today, "вчера 09:40", older as "03.10 09:40". */
@Composable
private fun Long.dayTimeLabel(): String {
    val zone = ZoneId.systemDefault()
    val at = Instant.ofEpochMilli(this).atZone(zone)
    val today = LocalDate.now(zone)
    val time = at.format(DateTimeFormatter.ofPattern("HH:mm"))
    return when (at.toLocalDate()) {
        today -> time
        today.minusDays(1) -> stringResource(R.string.more_sync_yesterday, time)
        else -> at.format(DateTimeFormatter.ofPattern("dd.MM HH:mm"))
    }
}
