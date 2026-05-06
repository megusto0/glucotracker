package com.local.glucotracker.data.di

import com.local.glucotracker.data.api.OpenApiJson
import com.local.glucotracker.data.api.ApiConnection
import com.local.glucotracker.generated.api.ActivityApi
import com.local.glucotracker.generated.api.DashboardApi
import com.local.glucotracker.generated.api.DatabaseApi
import com.local.glucotracker.generated.api.GlucoseApi
import com.local.glucotracker.generated.api.MealsApi
import com.local.glucotracker.generated.api.NightscoutApi
import com.local.glucotracker.generated.api.PatternsApi
import com.local.glucotracker.generated.api.PhotosApi
import com.local.glucotracker.generated.api.ProductsApi
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import io.ktor.client.HttpClient
import io.ktor.client.engine.android.Android
import io.ktor.client.plugins.DefaultRequest
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.header
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
    fun provideDashboardApi(@Named("apiBaseUrl") baseUrl: String): DashboardApi =
        DashboardApi(baseUrl = baseUrl)

    @Provides
    @Singleton
    fun provideMealsApi(@Named("apiBaseUrl") baseUrl: String): MealsApi =
        MealsApi(baseUrl = baseUrl)

    @Provides
    @Singleton
    fun providePhotosApi(@Named("apiBaseUrl") baseUrl: String): PhotosApi =
        PhotosApi(baseUrl = baseUrl)

    @Provides
    @Singleton
    @Named("apiToken")
    fun provideApiToken(): String = ApiConnection.TOKEN

    @Provides
    @Singleton
    fun provideHttpClient(@Named("apiToken") token: String): HttpClient =
        HttpClient(Android) {
            install(ContentNegotiation) {
                json(OpenApiJson.json)
            }
            install(DefaultRequest) {
                header("Authorization", "Bearer $token")
            }
        }

    @Provides
    @Singleton
    fun provideGlucoseApi(@Named("apiBaseUrl") baseUrl: String): GlucoseApi =
        GlucoseApi(baseUrl = baseUrl)

    @Provides
    @Singleton
    fun provideProductsApi(@Named("apiBaseUrl") baseUrl: String): ProductsApi =
        ProductsApi(baseUrl = baseUrl)

    @Provides
    @Singleton
    fun providePatternsApi(@Named("apiBaseUrl") baseUrl: String): PatternsApi =
        PatternsApi(baseUrl = baseUrl)

    @Provides
    @Singleton
    fun provideDatabaseApi(@Named("apiBaseUrl") baseUrl: String): DatabaseApi =
        DatabaseApi(baseUrl = baseUrl)

    @Provides
    @Singleton
    fun provideNightscoutApi(@Named("apiBaseUrl") baseUrl: String): NightscoutApi =
        NightscoutApi(baseUrl = baseUrl)

    @Provides
    @Singleton
    fun provideActivityApi(@Named("apiBaseUrl") baseUrl: String): ActivityApi =
        ActivityApi(baseUrl = baseUrl)
}
