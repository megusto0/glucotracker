package com.local.glucotracker.data.sync

import com.local.glucotracker.data.auth.AuthRepository
import com.local.glucotracker.data.auth.installAuthPlugin
import com.local.glucotracker.generated.api.GlucoseApi
import com.local.glucotracker.generated.api.NightscoutApi
import io.ktor.client.HttpClientConfig
import io.ktor.client.plugins.HttpTimeout

object FlavorOutboxRemoteFactory {
    @JvmStatic
    fun create(
        base: KtorOutboxRemote,
        baseUrl: String,
        authRepository: AuthRepository,
    ): OutboxRemote =
        GlucoOutboxRemote(
            base = base,
            glucoseApi = GlucoseApi(
                baseUrl = baseUrl,
                httpClientConfig = authenticatedConfig(authRepository),
            ),
            nightscoutApi = NightscoutApi(
                baseUrl = baseUrl,
                httpClientConfig = authenticatedConfig(authRepository),
            ),
        )

    private fun authenticatedConfig(
        authRepository: AuthRepository,
    ): (HttpClientConfig<*>) -> Unit = { config ->
        config.install(HttpTimeout) {
            requestTimeoutMillis = 30_000
            connectTimeoutMillis = 10_000
        }
        config.installAuthPlugin(authRepository, clientName = "android-outbox")
    }
}
