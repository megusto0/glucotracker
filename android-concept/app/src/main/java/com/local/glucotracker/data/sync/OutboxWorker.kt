package com.local.glucotracker.data.sync

import android.content.Context
import android.net.ConnectivityManager
import androidx.room.Room
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import com.local.glucotracker.data.api.OpenApiJson
import com.local.glucotracker.data.api.PhotoUploadClient
import com.local.glucotracker.data.local.GlucotrackerDatabase
import com.local.glucotracker.data.repository.OutboxRepositoryImpl
import com.local.glucotracker.generated.api.GlucoseApi
import com.local.glucotracker.generated.api.MealsApi
import com.local.glucotracker.generated.api.PhotosApi
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Named
import java.util.concurrent.TimeUnit
import io.ktor.client.HttpClient
import io.ktor.client.engine.android.Android
import io.ktor.client.plugins.DefaultRequest
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.header
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.CancellationException

interface OutboxFlushScheduler {
    fun enqueueImmediate(foregroundPhotoUpload: Boolean = false)
}

class WorkManagerOutboxFlushScheduler @Inject constructor(
    @ApplicationContext private val context: Context,
    @Named("apiBaseUrl") private val apiBaseUrl: String,
) : OutboxFlushScheduler {
    override fun enqueueImmediate(foregroundPhotoUpload: Boolean) {
        OutboxWorkScheduler.enqueueImmediate(
            context = context,
            foregroundPhotoUpload = foregroundPhotoUpload,
            apiBaseUrl = apiBaseUrl,
        )
    }
}

object NoOpOutboxFlushScheduler : OutboxFlushScheduler {
    override fun enqueueImmediate(foregroundPhotoUpload: Boolean) = Unit
}

class OutboxWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        val notifier = AndroidSyncNotifier(applicationContext)
        notifier.ensureChannel()

        if (inputData.getBoolean(InputForegroundPhotoUpload, false) && isActiveNetworkMetered()) {
            setForeground(notifier.photoUploadForegroundInfo())
        }

        val database = Room.databaseBuilder(
            applicationContext,
            GlucotrackerDatabase::class.java,
            "glucotracker.db",
        ).fallbackToDestructiveMigration(dropAllTables = true).build()
        val httpClient = HttpClient(Android) {
            install(ContentNegotiation) {
                json(OpenApiJson.json)
            }
            install(DefaultRequest) {
                header("Authorization", "Bearer dev")
            }
        }

        return try {
            val baseUrl = inputData.getString(InputApiBaseUrl) ?: DefaultApiBaseUrl
            val outboxDao = database.outboxDao()
            val repository = OutboxRepositoryImpl(database, outboxDao, NoOpOutboxFlushScheduler)
            val processor = OutboxProcessorImpl(
                queueStore = RoomOutboxQueueStore(database, outboxDao),
                outboxRepository = repository,
                remote = KtorOutboxRemote(
                    mealsApi = MealsApi(baseUrl = baseUrl),
                    photosApi = PhotosApi(baseUrl = baseUrl),
                    glucoseApi = GlucoseApi(baseUrl = baseUrl),
                    photoUploadClient = PhotoUploadClient(baseUrl, httpClient),
                ),
                notifier = notifier,
            )
            processor.processOnce()
            Result.success()
        } catch (cancellation: CancellationException) {
            throw cancellation
        } catch (throwable: Throwable) {
            Result.retry()
        } finally {
            httpClient.close()
            database.close()
        }
    }

    private fun isActiveNetworkMetered(): Boolean =
        applicationContext.getSystemService(ConnectivityManager::class.java).isActiveNetworkMetered

    companion object {
        const val InputForegroundPhotoUpload = "foreground_photo_upload"
        const val InputApiBaseUrl = "api_base_url"
        const val DefaultApiBaseUrl = "http://192.168.3.6:8000"
    }
}

object OutboxWorkScheduler {
    private const val ImmediateWorkName = "outbox-immediate-flush"
    private const val PeriodicWorkName = "outbox-periodic-flush"

    private val ConnectedConstraint = Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .build()

    fun enqueueImmediate(
        context: Context,
        foregroundPhotoUpload: Boolean = false,
        apiBaseUrl: String = OutboxWorker.DefaultApiBaseUrl,
    ) {
        val request = OneTimeWorkRequestBuilder<OutboxWorker>()
            .setConstraints(ConnectedConstraint)
            .setInputData(
                workDataOf(
                    OutboxWorker.InputForegroundPhotoUpload to foregroundPhotoUpload,
                    OutboxWorker.InputApiBaseUrl to apiBaseUrl,
                ),
            )
            .build()

        WorkManager.getInstance(context).enqueueUniqueWork(
            ImmediateWorkName,
            ExistingWorkPolicy.APPEND_OR_REPLACE,
            request,
        )
    }

    fun schedulePeriodic(context: Context) {
        val request = PeriodicWorkRequestBuilder<OutboxWorker>(15, TimeUnit.MINUTES)
            .setConstraints(ConnectedConstraint)
            .build()

        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            PeriodicWorkName,
            ExistingPeriodicWorkPolicy.UPDATE,
            request,
        )
    }
}
