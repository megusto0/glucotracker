package com.local.glucotracker.ui.navigation

import android.content.Context
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.compose.composable
import androidx.room.Room
import com.local.glucotracker.R
import com.local.glucotracker.data.auth.AuthRepository
import com.local.glucotracker.data.auth.installAuthPlugin
import com.local.glucotracker.data.local.CachedGlucoseDao
import com.local.glucotracker.data.local.GlucoseCacheDatabase
import com.local.glucotracker.data.repository.GlucoseRepositoryImpl
import com.local.glucotracker.data.repository.MealContextProvider
import com.local.glucotracker.data.repository.NightscoutMealContextProvider
import com.local.glucotracker.data.repository.NightscoutRepositoryImpl
import com.local.glucotracker.data.sync.GlucoOutboxRemote
import com.local.glucotracker.data.sync.OutboxRemote
import com.local.glucotracker.domain.repository.GlucoseRepository
import com.local.glucotracker.domain.repository.NightscoutRepository
import com.local.glucotracker.generated.api.GlucoseApi as GeneratedGlucoseApi
import com.local.glucotracker.generated.api.NightscoutApi as GeneratedNightscoutApi
import com.local.glucotracker.ui.feature.glucose.GlucoseRoute
import com.local.glucotracker.ui.feature.insulin.InsulinEntryRoute
import com.local.glucotracker.ui.glucose.GlucoseSurfaces
import com.local.glucotracker.ui.glucose.GlucoseSurfacesReal
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import io.ktor.client.HttpClientConfig
import javax.inject.Named
import javax.inject.Singleton

private const val GlucoseRoutePath = "glucose"
private const val QuickNumberRoutePath = "quick_number"

object GlucoNavConfig : NavConfig {
    override val tabs = listOf(
        TabSpec(Route.Today.route, R.string.nav_today, NavIcon.Today),
        TabSpec(GlucoseRoutePath, R.string.nav_glucose, NavIcon.Trend),
        TabSpec(Route.History.route, R.string.nav_history, NavIcon.History),
        TabSpec(Route.More.route, R.string.nav_more, NavIcon.More),
    )
    override val captureSheetEntries = DefaultCaptureSheetEntries
    override val captureFabExtraAction = CaptureFabExtraActionSpec(
        label = R.string.fab_option_insulin,
        route = QuickNumberRoutePath,
    )
    override val brand: BrandSpec? = null
}

class GlucoFlavorNavGraph : FlavorNavGraph {
    override fun NavGraphBuilder.registerFlavorRoutes(navController: NavHostController) {
        composable(GlucoseRoutePath) {
            GlucoseRoute()
        }
        composable(QuickNumberRoutePath) {
            InsulinEntryRoute(onClose = { navController.popBackStack() })
        }
    }
}

@Module
@InstallIn(SingletonComponent::class)
object GlucoFlavorModule {
    @Provides
    @Singleton
    fun provideNavConfig(): NavConfig = GlucoNavConfig

    @Provides
    @Singleton
    fun provideFlavorNavGraph(): FlavorNavGraph = GlucoFlavorNavGraph()

    @Provides
    @Singleton
    fun provideSurfaces(impl: GlucoseSurfacesReal): GlucoseSurfaces = impl

    @Provides
    @Singleton
    fun provideGeneratedGlucoseApi(
        @Named("apiBaseUrl") baseUrl: String,
        authRepository: AuthRepository,
    ): GeneratedGlucoseApi =
        GeneratedGlucoseApi(baseUrl = baseUrl, httpClientConfig = authenticatedConfig(authRepository))

    @Provides
    @Singleton
    fun provideGeneratedNightscoutApi(
        @Named("apiBaseUrl") baseUrl: String,
        authRepository: AuthRepository,
    ): GeneratedNightscoutApi =
        GeneratedNightscoutApi(baseUrl = baseUrl, httpClientConfig = authenticatedConfig(authRepository))

    @Provides
    @Singleton
    fun provideGlucoseCacheDatabase(@ApplicationContext context: Context): GlucoseCacheDatabase =
        Room.databaseBuilder(
            context,
            GlucoseCacheDatabase::class.java,
            "glucotracker-glucose.db",
        ).build()

    @Provides
    fun provideCachedGlucoseDao(database: GlucoseCacheDatabase): CachedGlucoseDao =
        database.cachedGlucoseDao()

    @Provides
    @Singleton
    fun provideGlucoseRepository(impl: GlucoseRepositoryImpl): GlucoseRepository = impl

    @Provides
    @Singleton
    fun provideNightscoutRepository(impl: NightscoutRepositoryImpl): NightscoutRepository = impl

    @Provides
    @Singleton
    fun provideMealContextProvider(impl: NightscoutMealContextProvider): MealContextProvider = impl

    @Provides
    @Singleton
    fun provideOutboxRemote(impl: GlucoOutboxRemote): OutboxRemote = impl

    private fun authenticatedConfig(
        authRepository: AuthRepository,
    ): (HttpClientConfig<*>) -> Unit = { config ->
        config.installAuthPlugin(authRepository)
    }
}
