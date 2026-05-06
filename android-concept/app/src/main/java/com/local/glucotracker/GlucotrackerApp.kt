package com.local.glucotracker

import android.app.Application
import com.local.glucotracker.data.cache.CachePruneScheduler
import com.local.glucotracker.data.sync.AndroidSyncNotifier
import com.local.glucotracker.data.sync.OutboxWorkScheduler
import dagger.hilt.android.HiltAndroidApp

@HiltAndroidApp
class GlucotrackerApp : Application() {
    override fun onCreate() {
        super.onCreate()
        AndroidSyncNotifier(this).ensureChannel()
        CachePruneScheduler.schedule(this)
        OutboxWorkScheduler.schedulePeriodic(this)
        OutboxWorkScheduler.enqueueImmediate(this)
    }
}
