package com.local.glucotracker.healthconnect

import com.local.glucotracker.data.auth.AuthRepository
import com.local.glucotracker.data.auth.installAuthPlugin
import com.local.glucotracker.generated.api.HealthConnectApi
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import io.ktor.client.plugins.HttpTimeout
import javax.inject.Named
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object HealthConnectNetworkModule {
    @Provides
    @Singleton
    fun provideHealthConnectApi(
        @Named("apiBaseUrl") baseUrl: String,
        authRepository: AuthRepository,
    ): HealthConnectApi = HealthConnectApi(
        baseUrl = baseUrl,
        httpClientConfig = { config ->
            config.install(HttpTimeout) {
                requestTimeoutMillis = 60_000
                connectTimeoutMillis = 10_000
            }
            config.installAuthPlugin(authRepository)
        },
    )
}
