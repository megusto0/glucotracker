package com.local.glucotracker

import android.app.Application
import android.net.ConnectivityManager
import android.net.Network
import coil3.ImageLoader
import coil3.SingletonImageLoader
import coil3.disk.DiskCache
import coil3.disk.directory
import coil3.memory.MemoryCache
import coil3.request.CachePolicy
import com.local.glucotracker.data.cache.CachePruneScheduler
import com.local.glucotracker.data.sync.AndroidSyncNotifier
import com.local.glucotracker.data.sync.OutboxWorkScheduler
import com.local.glucotracker.domain.repository.OutboxRepository
import com.local.glucotracker.domain.repository.ProductsRepository
import dagger.hilt.android.HiltAndroidApp
import javax.inject.Inject
import javax.inject.Named
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.first

@HiltAndroidApp
class GlucotrackerApp : Application(), SingletonImageLoader.Factory {
    @Inject lateinit var productsRepository: ProductsRepository
    @Inject lateinit var outboxRepository: OutboxRepository
    @Inject @Named("apiBaseUrl") lateinit var apiBaseUrl: String

    private val appScope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    override fun onCreate() {
        super.onCreate()
        AndroidSyncNotifier(this).ensureChannel()
        CachePruneScheduler.schedule(this)
        OutboxWorkScheduler.schedulePeriodic(this, apiBaseUrl)
        OutboxWorkScheduler.enqueueImmediate(this, apiBaseUrl = apiBaseUrl)
        appScope.launch {
            outboxRepository.revertNetworkStuckItems()
            OutboxWorkScheduler.enqueueSweep(this@GlucotrackerApp, apiBaseUrl)
        }
        appScope.launch { runCatching { productsRepository.refreshProducts() } }
        registerConnectivityCallback()
        scheduleAdaptivePeriodic()
    }

    private fun registerConnectivityCallback() {
        val cm = getSystemService(ConnectivityManager::class.java)
        cm.registerDefaultNetworkCallback(object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                appScope.launch {
                    outboxRepository.revertNetworkStuckItems()
                    OutboxWorkScheduler.enqueueSweep(this@GlucotrackerApp, apiBaseUrl)
                }
            }
        })
    }

    private fun scheduleAdaptivePeriodic() {
        appScope.launch {
            outboxRepository.observeActiveCount()
                .collect { count ->
                    if (count > 0) {
                        OutboxWorkScheduler.scheduleActiveRecovery(this@GlucotrackerApp, apiBaseUrl)
                    } else {
                        OutboxWorkScheduler.cancelActiveRecovery(this@GlucotrackerApp)
                    }
                }
        }
    }

    override fun newImageLoader(context: coil3.PlatformContext): ImageLoader =
        ImageLoader.Builder(context)
            .memoryCache {
                MemoryCache.Builder()
                    .maxSizePercent(context, 0.25)
                    .build()
            }
            .diskCache {
                DiskCache.Builder()
                    .directory(cacheDir.resolve("image_cache"))
                    .maxSizeBytes(100L * 1024L * 1024L)
                    .build()
            }
            .memoryCachePolicy(CachePolicy.ENABLED)
            .diskCachePolicy(CachePolicy.ENABLED)
            .networkCachePolicy(CachePolicy.ENABLED)
            .build()
}
