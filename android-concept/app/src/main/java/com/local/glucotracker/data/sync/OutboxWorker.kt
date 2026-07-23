package com.local.glucotracker.data.sync

import android.content.Context
import android.net.ConnectivityManager
import android.util.Log
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import com.local.glucotracker.data.api.MealApi
import com.local.glucotracker.data.api.ApiConnection
import com.local.glucotracker.data.api.OpenApiJson
import com.local.glucotracker.data.api.PhotoUploadClient
import com.local.glucotracker.data.auth.AuthRepository
import com.local.glucotracker.data.auth.TokenStore
import com.local.glucotracker.data.auth.installAuthPlugin
import com.local.glucotracker.data.di.DatabaseModule
import com.local.glucotracker.data.local.GlucotrackerDatabase
import com.local.glucotracker.data.repository.OutboxRepositoryImpl
import com.local.glucotracker.data.telemetry.PhotoEstimateTelemetryClient
import com.local.glucotracker.data.telemetry.PhotoEstimateTelemetryFlusher
import com.local.glucotracker.data.telemetry.PhotoEstimateTelemetryLogger
import com.local.glucotracker.data.telemetry.PhotoEstimateVisibilityTracker
import com.local.glucotracker.generated.api.AuthApi
import com.local.glucotracker.generated.api.MealsApi
import com.local.glucotracker.generated.api.PhotosApi
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Named
import java.util.concurrent.TimeUnit
import io.ktor.client.HttpClient
import io.ktor.client.HttpClientConfig
import io.ktor.client.engine.android.Android
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

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
            runCatching {
                setForeground(notifier.photoUploadForegroundInfo())
            }.onFailure { throwable ->
                Log.w(Tag, "Photo upload foreground mode unavailable; continuing in background.", throwable)
            }
        }

        val database = DatabaseModule.createDatabase(applicationContext)
        val baseUrl = inputData.getString(InputApiBaseUrl) ?: DefaultApiBaseUrl
        val authRepository = AuthRepository(
            tokenStore = TokenStore(applicationContext),
            authApi = AuthApi(baseUrl = baseUrl),
        )
        val authenticatedConfig: (HttpClientConfig<*>) -> Unit = { config ->
            config.install(HttpTimeout) {
                requestTimeoutMillis = 30_000
                connectTimeoutMillis = 10_000
            }
            config.installAuthPlugin(authRepository, clientName = "android-outbox")
        }
        val httpClient = HttpClient(Android) {
            install(HttpTimeout) {
                requestTimeoutMillis = 30_000
                connectTimeoutMillis = 10_000
            }
            install(ContentNegotiation) {
                json(OpenApiJson.json)
            }
            installAuthPlugin(authRepository, clientName = "android-outbox")
        }

        return try {
            val outboxDao = database.outboxDao()
            val photoLogDao = database.photoEstimateLogDao()
            val repository = OutboxRepositoryImpl(database, outboxDao, NoOpOutboxFlushScheduler)
            val reconciler = MealReconciler(outboxDao)
            val telemetryLogger = PhotoEstimateTelemetryLogger(photoLogDao)
            val mealApi = MealApi(MealsApi(baseUrl = baseUrl, httpClientConfig = authenticatedConfig))
            val telemetryClient = PhotoEstimateTelemetryClient(baseUrl, httpClient)
            val telemetryFlusher = PhotoEstimateTelemetryFlusher(photoLogDao, telemetryClient)
            val baseRemote = KtorOutboxRemote(
                mealsApi = MealsApi(baseUrl = baseUrl, httpClientConfig = authenticatedConfig),
                photosApi = PhotosApi(baseUrl = baseUrl, httpClientConfig = authenticatedConfig),
                photoUploadClient = PhotoUploadClient(baseUrl, httpClient),
            )
            val processor = OutboxProcessorImpl(
                queueStore = RoomOutboxQueueStore(database, outboxDao),
                outboxRepository = repository,
                remote = createOutboxRemote(baseRemote, baseUrl, authRepository),
                notifier = notifier,
                reconciler = reconciler,
                mealApi = mealApi,
                photoTelemetryLogger = telemetryLogger,
                photoVisibilityTracker = PhotoEstimateVisibilityTracker(
                    database = database,
                    mealDao = database.cachedMealDao(),
                    mealApi = mealApi,
                    telemetryLogger = telemetryLogger,
                    baseUrl = baseUrl,
                ),
            )
            val result = OutboxWorkerProcessLock.mutex.withLock {
                processor.processOnce()
            }
            val telemetryResult = telemetryFlusher.flushOnce()
            if (result.shouldRetry || telemetryResult.shouldRetry) Result.retry() else Result.success()
        } catch (cancellation: CancellationException) {
            throw cancellation
        } catch (throwable: Throwable) {
            Log.w(Tag, "Outbox worker failed before the queue was fully processed.", throwable)
            Result.retry()
        } finally {
            httpClient.close()
            database.close()
        }
    }

    private fun isActiveNetworkMetered(): Boolean =
        applicationContext.getSystemService(ConnectivityManager::class.java).isActiveNetworkMetered

    private fun createOutboxRemote(
        baseRemote: KtorOutboxRemote,
        baseUrl: String,
        authRepository: AuthRepository,
    ): OutboxRemote {
        val factoryClass = try {
            Class.forName("com.local.glucotracker.data.sync.FlavorOutboxRemoteFactory")
        } catch (_: ClassNotFoundException) {
            return baseRemote
        }

        return runCatching {
            val method = factoryClass.getMethod(
                "create",
                KtorOutboxRemote::class.java,
                String::class.java,
                AuthRepository::class.java,
            )
            method.invoke(null, baseRemote, baseUrl, authRepository) as OutboxRemote
        }.getOrElse { throwable ->
            Log.w(Tag, "Flavor outbox remote factory failed; using base outbox remote.", throwable)
            baseRemote
        }
    }

    companion object {
        const val InputForegroundPhotoUpload = "foreground_photo_upload"
        const val InputApiBaseUrl = "api_base_url"
        val DefaultApiBaseUrl = ApiConnection.BASE_URL
        private const val Tag = "OutboxWorker"
    }
}

private object OutboxWorkerProcessLock {
    val mutex = Mutex()
}

object OutboxWorkScheduler {
    private const val ImmediateWorkName = "outbox-immediate-flush"
    private const val PeriodicWorkName = "outbox-periodic-flush"
    private const val ActiveRecoveryWorkName = "outbox-active-recovery"

    private val ConnectedConstraint = Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .build()

    fun enqueueImmediate(
        context: Context,
        foregroundPhotoUpload: Boolean = false,
        apiBaseUrl: String = OutboxWorker.DefaultApiBaseUrl,
    ) {
        val builder = OneTimeWorkRequestBuilder<OutboxWorker>()
            .setConstraints(ConnectedConstraint)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .setInputData(
                workDataOf(
                    OutboxWorker.InputForegroundPhotoUpload to foregroundPhotoUpload,
                    OutboxWorker.InputApiBaseUrl to apiBaseUrl,
                ),
            )
        if (foregroundPhotoUpload) {
            builder.setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
        }
        val request = builder.build()

        WorkManager.getInstance(context).enqueueUniqueWork(
            ImmediateWorkName,
            ImmediateWorkPolicy,
            request,
        )
    }

    fun schedulePeriodic(context: Context) {
        schedulePeriodic(context, OutboxWorker.DefaultApiBaseUrl)
    }

    fun schedulePeriodic(context: Context, apiBaseUrl: String) {
        val request = PeriodicWorkRequestBuilder<OutboxWorker>(15, TimeUnit.MINUTES)
            .setConstraints(ConnectedConstraint)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .setInputData(workDataOf(OutboxWorker.InputApiBaseUrl to apiBaseUrl))
            .build()

        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            PeriodicWorkName,
            ExistingPeriodicWorkPolicy.UPDATE,
            request,
        )
    }

    fun scheduleActiveRecovery(context: Context) {
        scheduleActiveRecovery(context, OutboxWorker.DefaultApiBaseUrl)
    }

    fun scheduleActiveRecovery(context: Context, apiBaseUrl: String) {
        val request = PeriodicWorkRequestBuilder<OutboxWorker>(15, TimeUnit.MINUTES)
            .setConstraints(ConnectedConstraint)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .setInputData(workDataOf(OutboxWorker.InputApiBaseUrl to apiBaseUrl))
            .build()

        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            ActiveRecoveryWorkName,
            ExistingPeriodicWorkPolicy.UPDATE,
            request,
        )
    }

    fun cancelActiveRecovery(context: Context) {
        WorkManager.getInstance(context).cancelUniqueWork(ActiveRecoveryWorkName)
    }

    fun enqueueSweep(context: Context) {
        enqueueSweep(context, OutboxWorker.DefaultApiBaseUrl)
    }

    fun enqueueSweep(context: Context, apiBaseUrl: String) {
        val request = OneTimeWorkRequestBuilder<OutboxWorker>()
            .setConstraints(ConnectedConstraint)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .setInputData(workDataOf(OutboxWorker.InputApiBaseUrl to apiBaseUrl))
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            "outbox-connectivity-sweep",
            ExistingWorkPolicy.REPLACE,
            request,
        )
    }
}

internal val ImmediateWorkPolicy = ExistingWorkPolicy.APPEND_OR_REPLACE
