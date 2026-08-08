package com.local.glucotracker.wearable

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat

/** Signature-protected IPC client for the separate Gadgetbridge fork. */
object HelioBridgeClient {
    const val BridgePackage = "com.glucotracker.bridge"
    const val ControlPermission =
        "com.glucotracker.mobile.permission.CONTROL_WEARABLE_BRIDGE"

    private const val ActionStatus = "com.glucotracker.mobile.wearable.STATUS"
    private const val ActionSync = "com.glucotracker.mobile.wearable.SYNC"
    private const val ActionResult = "com.glucotracker.mobile.wearable.RESULT"

    fun isInstalled(context: Context): Boolean = try {
        context.packageManager.getApplicationInfo(BridgePackage, 0)
        true
    } catch (_: PackageManager.NameNotFoundException) {
        false
    }

    fun requestStatus(context: Context) {
        context.sendBroadcast(bridgeIntent(ActionStatus))
    }

    fun sync(context: Context) {
        context.sendBroadcast(bridgeIntent(ActionSync))
    }

    fun openBridge(context: Context): Boolean {
        val launchIntent = context.packageManager.getLaunchIntentForPackage(BridgePackage)
            ?: return false
        launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(launchIntent)
        return true
    }

    fun register(
        context: Context,
        onStatus: (HelioBridgeStatus) -> Unit,
    ): BroadcastReceiver {
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context?, intent: Intent?) {
                if (intent?.action != ActionResult) return
                onStatus(
                    HelioBridgeStatus(
                        installed = true,
                        phase = intent.getStringExtra("phase").orEmpty(),
                        connected = intent.getBooleanExtra("connected", false),
                        deviceName = intent.getStringExtra("device_name")
                            ?: "Amazfit Helio Strap",
                        battery = intent.getIntExtra("battery", -1),
                        error = intent.getStringExtra("error"),
                    ),
                )
            }
        }
        ContextCompat.registerReceiver(
            context,
            receiver,
            IntentFilter(ActionResult),
            ControlPermission,
            null,
            ContextCompat.RECEIVER_EXPORTED,
        )
        return receiver
    }

    private fun bridgeIntent(action: String): Intent = Intent(action)
        .setPackage(BridgePackage)
        // A freshly installed companion is in Android's stopped state until
        // first launch. The explicit, signature-protected request is allowed
        // to wake it without exposing a general background entry point.
        .addFlags(Intent.FLAG_INCLUDE_STOPPED_PACKAGES)
}

data class HelioBridgeStatus(
    val installed: Boolean = false,
    val phase: String = "idle",
    val connected: Boolean = false,
    val deviceName: String = "Amazfit Helio Strap",
    val battery: Int = -1,
    val error: String? = null,
) {
    val isBusy: Boolean
        get() = phase in setOf("connecting", "device_sync", "health_connect", "syncing")
}
