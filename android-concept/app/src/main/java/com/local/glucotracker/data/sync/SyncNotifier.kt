package com.local.glucotracker.data.sync

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.ForegroundInfo
import com.local.glucotracker.MainActivity
import com.local.glucotracker.R
import com.local.glucotracker.data.settings.SettingsStore
import com.local.glucotracker.ui.navigation.Route
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking

interface SyncNotifier {
    fun ensureChannel()
    fun photoUploadForegroundInfo(): ForegroundInfo
    fun notifyOutboxStuck()
}

@Singleton
class AndroidSyncNotifier @Inject constructor(
    @ApplicationContext private val context: Context,
    private val settingsStore: SettingsStore? = null,
) : SyncNotifier {
    override fun ensureChannel() {
        val manager = context.getSystemService(NotificationManager::class.java)
        val syncChannel = NotificationChannel(
            SyncNotificationChannelId,
            context.getString(R.string.sync_channel_name),
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = context.getString(R.string.sync_channel_description)
        }
        manager.createNotificationChannel(syncChannel)
        val stuckChannel = NotificationChannel(
            OutboxStuckNotificationChannelId,
            context.getString(R.string.notification_outbox_stuck_channel_name),
            NotificationManager.IMPORTANCE_DEFAULT,
        ).apply {
            description = context.getString(R.string.notification_outbox_stuck_channel_description)
        }
        manager.createNotificationChannel(stuckChannel)
    }

    override fun photoUploadForegroundInfo(): ForegroundInfo {
        ensureChannel()
        val notification = NotificationCompat.Builder(context, SyncNotificationChannelId)
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setContentTitle(context.getString(R.string.notification_sync_title))
            .setContentText(context.getString(R.string.notification_photo_upload_text))
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()

        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ForegroundInfo(
                SyncForegroundNotificationId,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
            )
        } else {
            ForegroundInfo(SyncForegroundNotificationId, notification)
        }
    }

    override fun notifyOutboxStuck() {
        val enabled = settingsStore?.let { store ->
            runBlocking { store.notificationToggles.first().outboxStuck }
        } ?: false
        if (!enabled) return
        val now = System.currentTimeMillis()
        if (now - lastStuckNotificationAt < StuckNotificationThrottleMs) return
        lastStuckNotificationAt = now

        ensureChannel()
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(
                context,
                Manifest.permission.POST_NOTIFICATIONS,
            ) != PackageManager.PERMISSION_GRANTED
        ) {
            return
        }
        val outboxIntent = Intent(
            Intent.ACTION_VIEW,
            Uri.parse(Route.OutboxInspector.DeepLinkUri),
            context,
            MainActivity::class.java,
        )
        val outboxPendingIntent = PendingIntent.getActivity(
            context,
            OutboxStuckNotificationId,
            outboxIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = NotificationCompat.Builder(context, OutboxStuckNotificationChannelId)
            .setSmallIcon(android.R.drawable.stat_notify_error)
            .setContentTitle(context.getString(R.string.notification_outbox_stuck_title))
            .setContentText(context.getString(R.string.notification_outbox_stuck_text))
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setContentIntent(outboxPendingIntent)
            .setAutoCancel(true)
            .build()
        runCatching {
            NotificationManagerCompat.from(context).notify(OutboxStuckNotificationId, notification)
        }.onFailure { throwable ->
            if (throwable !is SecurityException) throw throwable
        }
    }

    private companion object {
        const val SyncForegroundNotificationId = 1202
        const val OutboxStuckNotificationId = 1203
        const val StuckNotificationThrottleMs = 10 * 60 * 1_000L
        var lastStuckNotificationAt = 0L
    }
}

const val SyncNotificationChannelId = "sync"
const val OutboxStuckNotificationChannelId = "outbox_stuck"
