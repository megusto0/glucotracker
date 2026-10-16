package com.local.glucotracker.ui.glucose

import com.local.glucotracker.wearable.HelioBridgeStatus

/**
 * Where heart rate is on its way from the strap to the server.
 *
 * Three hops can each stall on their own, and a single "last sync" line hid
 * which one: on 2026-10-05 Bridge reported "complete" every round while the
 * strap delivered nothing for 27 hours, and the server upload then sat in an
 * exponential retry for hours more. Each step here says what it last saw.
 */
internal enum class SyncStepState { Ok, Working, Waiting, Failed, Unknown }

internal sealed interface SyncDetail {
    // Strap → Bridge.
    data object BridgeMissing : SyncDetail
    data object NotPaired : SyncDetail
    data object HealthConnectRequired : SyncDetail
    data object ConnectTimeout : SyncDetail
    data object BridgeFailed : SyncDetail
    data object Connecting : SyncDetail
    data object Fetching : SyncDetail
    data object Exporting : SyncDetail
    data object NoStrapData : SyncDetail
    data class DataThrough(val at: Long) : SyncDetail
    data class StrapSilent(val since: Long) : SyncDetail

    // Bridge → Health Connect.
    data object NoHeartRate : SyncDetail
    data class HeartRate(val bpm: Long) : SyncDetail
    data class HealthConnectBehind(val since: Long) : SyncDetail

    // Health Connect → server.
    data object NeverUploaded : SyncDetail
    data class Uploading(val sent: Int) : SyncDetail
    data class UploadFailed(val error: String) : SyncDetail
    data object UploadPending : SyncDetail
    data class Uploaded(val records: Int) : SyncDetail
    data object UpToDate : SyncDetail
}

internal data class SyncStep(
    val state: SyncStepState,
    val detail: SyncDetail,
    /** Epoch millis shown beside the step, or ≤ 0 when there is none. */
    val at: Long,
)

internal data class SyncPipeline(
    val strap: SyncStep,
    val healthConnect: SyncStep,
    val server: SyncStep,
) {
    val steps: List<SyncStep> get() = listOf(strap, healthConnect, server)

    /** The step that explains the state: the first failure, then the first stall. */
    val headline: SyncStep?
        get() = steps.firstOrNull { it.state == SyncStepState.Failed }
            ?: steps.firstOrNull { it.state == SyncStepState.Working }
            ?: steps.firstOrNull { it.state == SyncStepState.Waiting }
            ?: steps.firstOrNull { it.state == SyncStepState.Unknown }

    val allOk: Boolean get() = headline == null
}

/** Strap data older than this, with the strap worn, means it is not arriving. */
internal const val StaleDataMillis = 30L * 60L * 1_000L

/** Health Connect may trail Bridge's newest sample by a few unrecorded minutes. */
private const val HealthConnectSlackMillis = 10L * 60L * 1_000L

internal fun syncPipeline(
    bridge: HelioBridgeStatus,
    upload: HcSyncStatus,
    uploading: Boolean,
    uploadedSoFar: Int,
    now: Long,
): SyncPipeline = SyncPipeline(
    strap = strapStep(bridge, now),
    healthConnect = healthConnectStep(bridge, upload),
    server = serverStep(bridge, upload, uploading, uploadedSoFar),
)

private fun strapStep(bridge: HelioBridgeStatus, now: Long): SyncStep {
    val at = bridge.lastCompleteAt
    fun step(state: SyncStepState, detail: SyncDetail) = SyncStep(state, detail, at)
    return when {
        !bridge.installed -> step(SyncStepState.Unknown, SyncDetail.BridgeMissing)
        bridge.error == "not_paired" -> step(SyncStepState.Failed, SyncDetail.NotPaired)
        bridge.error == "health_connect_required" ->
            step(SyncStepState.Failed, SyncDetail.HealthConnectRequired)
        bridge.error == "connect_timeout" -> step(SyncStepState.Failed, SyncDetail.ConnectTimeout)
        bridge.phase == "error" -> step(SyncStepState.Failed, SyncDetail.BridgeFailed)
        bridge.phase == "connecting" -> step(SyncStepState.Working, SyncDetail.Connecting)
        bridge.phase == "device_sync" || bridge.phase == "syncing" ->
            step(SyncStepState.Working, SyncDetail.Fetching)
        bridge.phase == "health_connect" -> step(SyncStepState.Working, SyncDetail.Exporting)
        bridge.dataThroughAt <= 0L -> step(SyncStepState.Unknown, SyncDetail.NoStrapData)
        now - bridge.dataThroughAt > StaleDataMillis ->
            step(SyncStepState.Waiting, SyncDetail.StrapSilent(bridge.dataThroughAt))
        else -> step(SyncStepState.Ok, SyncDetail.DataThrough(bridge.dataThroughAt))
    }
}

private fun healthConnectStep(bridge: HelioBridgeStatus, upload: HcSyncStatus): SyncStep {
    val at = upload.latestHeartRateAt
    return when {
        upload.latestHeartRateBpm <= 0L || at <= 0L ->
            SyncStep(SyncStepState.Unknown, SyncDetail.NoHeartRate, -1L)
        bridge.dataThroughAt > 0L && at < bridge.dataThroughAt - HealthConnectSlackMillis ->
            SyncStep(SyncStepState.Waiting, SyncDetail.HealthConnectBehind(at), at)
        else -> SyncStep(SyncStepState.Ok, SyncDetail.HeartRate(upload.latestHeartRateBpm), at)
    }
}

private fun serverStep(
    bridge: HelioBridgeStatus,
    upload: HcSyncStatus,
    uploading: Boolean,
    uploadedSoFar: Int,
): SyncStep {
    val at = upload.lastSyncAt
    fun step(state: SyncStepState, detail: SyncDetail) = SyncStep(state, detail, at)
    return when {
        uploading -> step(SyncStepState.Working, SyncDetail.Uploading(uploadedSoFar))
        upload.error != null -> step(SyncStepState.Failed, SyncDetail.UploadFailed(upload.error))
        at <= 0L -> step(SyncStepState.Unknown, SyncDetail.NeverUploaded)
        // Bridge handed over a batch after the last upload finished.
        bridge.lastCompleteAt > at -> step(SyncStepState.Waiting, SyncDetail.UploadPending)
        upload.records > 0 -> step(SyncStepState.Ok, SyncDetail.Uploaded(upload.records))
        else -> step(SyncStepState.Ok, SyncDetail.UpToDate)
    }
}
