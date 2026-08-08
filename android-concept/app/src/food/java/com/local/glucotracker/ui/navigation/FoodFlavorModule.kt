package com.local.glucotracker.ui.navigation

import com.local.glucotracker.R
import com.local.glucotracker.data.repository.MealContextProvider
import com.local.glucotracker.data.repository.NoopMealContextProvider
import com.local.glucotracker.data.sync.KtorOutboxRemote
import com.local.glucotracker.data.sync.OutboxRemote
import com.local.glucotracker.ui.design.FoodBrandTokens
import com.local.glucotracker.ui.glucose.GlucoseSurfaces
import com.local.glucotracker.ui.glucose.GlucoseSurfacesNoop
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object FoodFlavorModule {
    @Provides
    @Singleton
    fun provideNavConfig(): NavConfig = FoodNavConfig

    @Provides
    @Singleton
    fun provideFlavorNavGraph(): FlavorNavGraph = NoopFlavorNavGraph

    @Provides
    @Singleton
    fun provideSurfaces(): GlucoseSurfaces = GlucoseSurfacesNoop

    @Provides
    @Singleton
    fun provideMealContextProvider(): MealContextProvider = NoopMealContextProvider

    @Provides
    @Singleton
    fun provideOutboxRemote(impl: KtorOutboxRemote): OutboxRemote = impl
}

private object FoodNavConfig : NavConfig {
    override val tabs = listOf(
        TabSpec(Route.Today.route, R.string.nav_today, NavIcon.Today),
        TabSpec(Route.Norm.route, R.string.stats_page_label, NavIcon.Stats),
        TabSpec(Route.History.route, R.string.nav_history, NavIcon.History),
        TabSpec(Route.More.route, R.string.nav_more, NavIcon.More),
    )
    override val captureSheetEntries = DefaultCaptureSheetEntries
    override val brand = BrandSpec(
        mark = R.drawable.ic_brand_mark,
        name = R.string.app_name,
        activeIndicatorColor = FoodBrandTokens.Tangerine,
        showHeader = false,
    )
}
