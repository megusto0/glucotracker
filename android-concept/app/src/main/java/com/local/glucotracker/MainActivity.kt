package com.local.glucotracker

import android.net.ConnectivityManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.local.glucotracker.data.sync.OutboxWorkScheduler
import com.local.glucotracker.domain.repository.OutboxRepository
import com.local.glucotracker.ui.design.GTTheme
import com.local.glucotracker.ui.navigation.GlucotrackerApp
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject
import javax.inject.Named
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    @Inject lateinit var outboxRepository: OutboxRepository
    @Inject @Named("apiBaseUrl") lateinit var apiBaseUrl: String

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        installHealthConnect()
        setContent {
            GTTheme {
                GlucotrackerApp()
            }
        }
    }

    override fun onStart() {
        super.onStart()
        scope.launch {
            val hasPending = outboxRepository.observeActiveCount().first() > 0
            if (hasPending && isOnline()) {
                OutboxWorkScheduler.enqueueSweep(this@MainActivity, apiBaseUrl)
            }
        }
    }

    private fun isOnline(): Boolean {
        val cm = getSystemService(ConnectivityManager::class.java)
        val network = cm.activeNetwork
        val caps = network?.let(cm::getNetworkCapabilities)
        return caps?.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_INTERNET) == true
    }

    private fun installHealthConnect() {
        runCatching {
            Class.forName("com.local.glucotracker.healthconnect.DebugHealthConnectSync")
                .getMethod("install", ComponentActivity::class.java)
                .invoke(null, this)
        }
    }
}
