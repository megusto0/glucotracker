package com.local.glucotracker.data.di

import com.local.glucotracker.data.repository.GlucoseRepositoryImpl
import com.local.glucotracker.data.repository.HistoryRepositoryImpl
import com.local.glucotracker.data.repository.MealRepositoryImpl
import com.local.glucotracker.data.repository.NightscoutRepositoryImpl
import com.local.glucotracker.data.repository.OutboxRepositoryImpl
import com.local.glucotracker.data.repository.ProductsRepositoryImpl
import com.local.glucotracker.data.repository.StatsRepositoryImpl
import com.local.glucotracker.data.repository.SyncRepositoryImpl
import com.local.glucotracker.data.repository.TodayRepositoryImpl
import com.local.glucotracker.data.sync.AndroidSyncNotifier
import com.local.glucotracker.data.sync.KtorOutboxRemote
import com.local.glucotracker.data.sync.OutboxFlushScheduler
import com.local.glucotracker.data.sync.OutboxProcessorImpl
import com.local.glucotracker.data.sync.OutboxQueueStore
import com.local.glucotracker.data.sync.OutboxProcessor
import com.local.glucotracker.data.sync.OutboxRemote
import com.local.glucotracker.data.sync.RoomOutboxQueueStore
import com.local.glucotracker.data.sync.SyncNotifier
import com.local.glucotracker.data.sync.WorkManagerOutboxFlushScheduler
import com.local.glucotracker.domain.repository.GlucoseRepository
import com.local.glucotracker.domain.repository.HistoryRepository
import com.local.glucotracker.domain.repository.MealRepository
import com.local.glucotracker.domain.repository.NightscoutRepository
import com.local.glucotracker.domain.repository.OutboxRepository
import com.local.glucotracker.domain.repository.ProductsRepository
import com.local.glucotracker.domain.repository.StatsRepository
import com.local.glucotracker.domain.repository.SyncRepository
import com.local.glucotracker.domain.repository.TodayRepository
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class RepositoryModule {
    @Binds
    @Singleton
    abstract fun bindTodayRepository(impl: TodayRepositoryImpl): TodayRepository

    @Binds
    @Singleton
    abstract fun bindGlucoseRepository(impl: GlucoseRepositoryImpl): GlucoseRepository

    @Binds
    @Singleton
    abstract fun bindStatsRepository(impl: StatsRepositoryImpl): StatsRepository

    @Binds
    @Singleton
    abstract fun bindHistoryRepository(impl: HistoryRepositoryImpl): HistoryRepository

    @Binds
    @Singleton
    abstract fun bindProductsRepository(impl: ProductsRepositoryImpl): ProductsRepository

    @Binds
    @Singleton
    abstract fun bindMealRepository(impl: MealRepositoryImpl): MealRepository

    @Binds
    @Singleton
    abstract fun bindNightscoutRepository(impl: NightscoutRepositoryImpl): NightscoutRepository

    @Binds
    @Singleton
    abstract fun bindOutboxRepository(impl: OutboxRepositoryImpl): OutboxRepository

    @Binds
    @Singleton
    abstract fun bindSyncRepository(impl: SyncRepositoryImpl): SyncRepository

    @Binds
    @Singleton
    abstract fun bindOutboxProcessor(impl: OutboxProcessorImpl): OutboxProcessor

    @Binds
    @Singleton
    abstract fun bindOutboxRemote(impl: KtorOutboxRemote): OutboxRemote

    @Binds
    @Singleton
    abstract fun bindOutboxQueueStore(impl: RoomOutboxQueueStore): OutboxQueueStore

    @Binds
    @Singleton
    abstract fun bindOutboxFlushScheduler(impl: WorkManagerOutboxFlushScheduler): OutboxFlushScheduler

    @Binds
    @Singleton
    abstract fun bindSyncNotifier(impl: AndroidSyncNotifier): SyncNotifier
}
