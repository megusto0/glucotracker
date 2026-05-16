package com.local.glucotracker.data.di

import com.local.glucotracker.data.api.ApiConnection
import com.local.glucotracker.data.api.OpenApiJson
import com.local.glucotracker.data.auth.AuthRepository
import com.local.glucotracker.data.auth.installAuthPlugin
import com.local.glucotracker.generated.api.ActivityApi
import com.local.glucotracker.generated.api.AuthApi
import com.local.glucotracker.generated.api.DashboardApi
import com.local.glucotracker.generated.api.DatabaseApi
import com.local.glucotracker.generated.api.MealsApi
import com.local.glucotracker.generated.api.PatternsApi
import com.local.glucotracker.generated.api.PhotosApi
import com.local.glucotracker.generated.api.ProductsApi
import com.local.glucotracker.generated.api.ScheduleApi
import com.local.glucotracker.generated.api.StatsApi
import com.local.glucotracker.generated.api.UsersApi
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import io.ktor.client.HttpClient
import io.ktor.client.HttpClientConfig
import io.ktor.client.engine.android.Android
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.serialization.kotlinx.json.json
import javax.inject.Named
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {
    @Provides
    @Singleton
    @Named("apiBaseUrl")
    fun provideApiBaseUrl(): String = ApiConnection.BASE_URL

    @Provides
    @Singleton
    fun provideAuthApi(@Named("apiBaseUrl") baseUrl: String): AuthApi =
        AuthApi(baseUrl = baseUrl)

    @Provides
    @Singleton
    fun provideDashboardApi(
        @Named("apiBaseUrl") baseUrl: String,
        authRepository: AuthRepository,
    ): DashboardApi =
        DashboardApi(baseUrl = baseUrl, httpClientConfig = authenticatedConfig(authRepository))

    @Provides
    @Singleton
    fun provideMealsApi(
        @Named("apiBaseUrl") baseUrl: String,
        authRepository: AuthRepository,
    ): MealsApi =
        MealsApi(baseUrl = baseUrl, httpClientConfig = authenticatedConfig(authRepository))

    @Provides
    @Singleton
    fun providePhotosApi(
        @Named("apiBaseUrl") baseUrl: String,
        authRepository: AuthRepository,
    ): PhotosApi =
        PhotosApi(baseUrl = baseUrl, httpClientConfig = authenticatedConfig(authRepository))

    @Provides
    @Singleton
    fun provideHttpClient(authRepository: AuthRepository): HttpClient =
        HttpClient(Android) {
            install(HttpTimeout) {
                requestTimeoutMillis = 30_000
                connectTimeoutMillis = 10_000
            }
            install(ContentNegotiation) {
                json(OpenApiJson.json)
            }
            installAuthPlugin(authRepository)
        }

    @Provides
    @Singleton
    fun provideProductsApi(
        @Named("apiBaseUrl") baseUrl: String,
        authRepository: AuthRepository,
    ): ProductsApi =
        ProductsApi(baseUrl = baseUrl, httpClientConfig = authenticatedConfig(authRepository))

    @Provides
    @Singleton
    fun providePatternsApi(
        @Named("apiBaseUrl") baseUrl: String,
        authRepository: AuthRepository,
    ): PatternsApi =
        PatternsApi(baseUrl = baseUrl, httpClientConfig = authenticatedConfig(authRepository))

    @Provides
    @Singleton
    fun provideDatabaseApi(
        @Named("apiBaseUrl") baseUrl: String,
        authRepository: AuthRepository,
    ): DatabaseApi =
        DatabaseApi(baseUrl = baseUrl, httpClientConfig = authenticatedConfig(authRepository))

    @Provides
    @Singleton
    fun provideActivityApi(
        @Named("apiBaseUrl") baseUrl: String,
        authRepository: AuthRepository,
    ): ActivityApi =
        ActivityApi(baseUrl = baseUrl, httpClientConfig = authenticatedConfig(authRepository))

    @Provides
    @Singleton
    fun provideStatsApi(
        @Named("apiBaseUrl") baseUrl: String,
        authRepository: AuthRepository,
    ): StatsApi =
        StatsApi(baseUrl = baseUrl, httpClientConfig = authenticatedConfig(authRepository))

    @Provides
    @Singleton
    fun provideScheduleApi(
        @Named("apiBaseUrl") baseUrl: String,
        authRepository: AuthRepository,
    ): ScheduleApi =
        ScheduleApi(baseUrl = baseUrl, httpClientConfig = authenticatedConfig(authRepository))

    @Provides
    @Singleton
    fun provideUsersApi(
        @Named("apiBaseUrl") baseUrl: String,
        authRepository: AuthRepository,
    ): UsersApi =
        UsersApi(baseUrl = baseUrl, httpClientConfig = authenticatedConfig(authRepository))

    private fun authenticatedConfig(
        authRepository: AuthRepository,
    ): (HttpClientConfig<*>) -> Unit = { config ->
        config.install(HttpTimeout) {
            requestTimeoutMillis = 30_000
            connectTimeoutMillis = 10_000
        }
        config.installAuthPlugin(authRepository)
    }
}
