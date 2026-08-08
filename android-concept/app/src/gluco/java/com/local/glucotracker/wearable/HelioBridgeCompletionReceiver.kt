package com.local.glucotracker.wearable

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.local.glucotracker.healthconnect.DebugHealthConnectSync

/** Uploads a completed Bridge export even when the settings screen is closed. */
class HelioBridgeCompletionReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ActionResult) return
        if (intent.getStringExtra("phase") != "complete") return
        DebugHealthConnectSync.enqueueBridgeSync(context.applicationContext)
    }

    private companion object {
        const val ActionResult = "com.glucotracker.mobile.wearable.RESULT"
    }
}
