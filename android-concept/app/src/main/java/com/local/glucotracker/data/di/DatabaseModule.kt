package com.local.glucotracker.data.di

import android.content.Context
import androidx.room.Room
import com.local.glucotracker.data.local.CachedDayTotalsDao
import com.local.glucotracker.data.local.CachedGlucoseDao
import com.local.glucotracker.data.local.CachedMealDao
import com.local.glucotracker.data.local.CachedProductDao
import com.local.glucotracker.data.local.CachedTemplateDao
import com.local.glucotracker.data.local.GlucotrackerDatabase
import com.local.glucotracker.data.local.OutboxDao
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {
    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): GlucotrackerDatabase =
        Room.databaseBuilder(
            context,
            GlucotrackerDatabase::class.java,
            "glucotracker.db",
        ).fallbackToDestructiveMigration(dropAllTables = true).build()

    @Provides
    fun provideOutboxDao(database: GlucotrackerDatabase): OutboxDao =
        database.outboxDao()

    @Provides
    fun provideCachedMealDao(database: GlucotrackerDatabase): CachedMealDao =
        database.cachedMealDao()

    @Provides
    fun provideCachedDayTotalsDao(database: GlucotrackerDatabase): CachedDayTotalsDao =
        database.cachedDayTotalsDao()

    @Provides
    fun provideCachedGlucoseDao(database: GlucotrackerDatabase): CachedGlucoseDao =
        database.cachedGlucoseDao()

    @Provides
    fun provideCachedProductDao(database: GlucotrackerDatabase): CachedProductDao =
        database.cachedProductDao()

    @Provides
    fun provideCachedTemplateDao(database: GlucotrackerDatabase): CachedTemplateDao =
        database.cachedTemplateDao()
}
