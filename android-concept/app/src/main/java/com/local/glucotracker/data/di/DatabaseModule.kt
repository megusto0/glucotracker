package com.local.glucotracker.data.di

import android.content.Context
import androidx.room.Room
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import com.local.glucotracker.data.api.OpenApiJson
import com.local.glucotracker.data.local.CachedDayTotalsDao
import com.local.glucotracker.data.local.CachedMealDao
import com.local.glucotracker.data.local.CachedProductDao
import com.local.glucotracker.data.local.CachedTemplateDao
import com.local.glucotracker.data.local.GlucotrackerDatabase
import com.local.glucotracker.data.local.OutboxDao
import com.local.glucotracker.data.local.PhotoEstimateLogDao
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {
    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): GlucotrackerDatabase =
        createDatabase(context)

    fun createDatabase(context: Context): GlucotrackerDatabase =
        Room.databaseBuilder(
            context,
            GlucotrackerDatabase::class.java,
            "glucotracker.db",
        ).addMigrations(
            Migration4To5,
            Migration5To6,
            Migration6To7,
            Migration7To8,
            Migration8To9,
            Migration9To10,
            Migration10To11,
            Migration11To12,
            Migration12To13,
            Migration13To14,
        ).build()

    @Provides
    fun provideOutboxDao(database: GlucotrackerDatabase): OutboxDao =
        database.outboxDao()

    @Provides
    fun providePhotoEstimateLogDao(database: GlucotrackerDatabase): PhotoEstimateLogDao =
        database.photoEstimateLogDao()

    @Provides
    fun provideCachedMealDao(database: GlucotrackerDatabase): CachedMealDao =
        database.cachedMealDao()

    @Provides
    fun provideCachedDayTotalsDao(database: GlucotrackerDatabase): CachedDayTotalsDao =
        database.cachedDayTotalsDao()

    @Provides
    fun provideCachedProductDao(database: GlucotrackerDatabase): CachedProductDao =
        database.cachedProductDao()

    @Provides
    fun provideCachedTemplateDao(database: GlucotrackerDatabase): CachedTemplateDao =
        database.cachedTemplateDao()

    private val Migration4To5 = object : Migration(4, 5) {
        override fun migrate(db: SupportSQLiteDatabase) {
            db.execSQL("UPDATE outbox SET state = 'Uploading' WHERE state = 'Sending'")
            db.execSQL("UPDATE outbox SET state = 'Confirmed' WHERE state = 'Sent'")
            db.execSQL("UPDATE outbox SET state = 'Queued' WHERE state = 'EstimateReady' OR state = 'Estimating'")
            migrateLegacyReadyMealRows(db)
            db.execSQL("UPDATE outbox SET kindType = 'captured_meal' WHERE kindType = 'photo_estimate_request'")
            db.execSQL(
                """
                UPDATE outbox
                SET kindJson = replace(kindJson, '"type":"photo_estimate_request"', '"type":"captured_meal"')
                WHERE kindJson LIKE '%"type":"photo_estimate_request"%'
                """.trimIndent(),
            )
            db.execSQL(
                """
                UPDATE outbox
                SET kindJson = replace(kindJson, '"source":"gallery"', '"source":"gallery","optimisticName":null,"optimisticWeightG":null')
                WHERE kindType = 'captured_meal' AND kindJson LIKE '%"source":"gallery"%'
                """.trimIndent(),
            )
            db.execSQL(
                """
                UPDATE outbox
                SET kindJson = replace(kindJson, '"source":"photo"', '"source":"photo","optimisticName":null,"optimisticWeightG":null')
                WHERE kindType = 'captured_meal' AND kindJson LIKE '%"source":"photo"%'
                """.trimIndent(),
            )
        }
    }

    private val Migration5To6 = object : Migration(5, 6) {
        override fun migrate(db: SupportSQLiteDatabase) {
            db.execSQL("ALTER TABLE cached_day_totals ADD COLUMN photoCount INTEGER NOT NULL DEFAULT 0")
            db.execSQL("ALTER TABLE cached_day_totals ADD COLUMN dailyAverageKcalForPeriod REAL")
            db.execSQL("ALTER TABLE cached_meals ADD COLUMN tagsCsv TEXT NOT NULL DEFAULT ''")
        }
    }

    private val Migration6To7 = object : Migration(6, 7) {
        override fun migrate(db: SupportSQLiteDatabase) {
            db.execSQL("ALTER TABLE outbox ADD COLUMN nextAttemptAt TEXT")
            db.execSQL("ALTER TABLE outbox ADD COLUMN enteredCurrentStateAt TEXT")
            db.execSQL("ALTER TABLE outbox ADD COLUMN lastErrorCode TEXT")
            db.execSQL("ALTER TABLE outbox ADD COLUMN lastErrorMessage TEXT")
            db.execSQL("UPDATE outbox SET enteredCurrentStateAt = createdAt WHERE enteredCurrentStateAt IS NULL")
            db.execSQL("UPDATE outbox SET state = 'Stuck', lastErrorCode = 'conflict', lastErrorMessage = errorMessage WHERE state = 'Conflict'")
        }
    }

    private val Migration7To8 = object : Migration(7, 8) {
        override fun migrate(db: SupportSQLiteDatabase) {
            db.execSQL("ALTER TABLE cached_meals ADD COLUMN postprandialJson TEXT")
        }
    }

    private val Migration8To9 = object : Migration(8, 9) {
        override fun migrate(db: SupportSQLiteDatabase) {
            db.execSQL("ALTER TABLE outbox ADD COLUMN linkedMealId TEXT")
            db.execSQL("ALTER TABLE outbox ADD COLUMN reconciledAt TEXT")
            db.execSQL("ALTER TABLE cached_meals ADD COLUMN photoIdempotencyKey TEXT")
        }
    }

    private val Migration9To10 = object : Migration(9, 10) {
        override fun migrate(db: SupportSQLiteDatabase) {
            db.execSQL("ALTER TABLE cached_meals ADD COLUMN estimateStatus TEXT")
            db.execSQL("ALTER TABLE cached_meals ADD COLUMN estimateError TEXT")
        }
    }

    private val Migration10To11 = object : Migration(10, 11) {
        override fun migrate(db: SupportSQLiteDatabase) {
            db.execSQL("ALTER TABLE cached_templates ADD COLUMN prefix TEXT NOT NULL DEFAULT ''")
        }
    }

    private val Migration11To12 = object : Migration(11, 12) {
        override fun migrate(db: SupportSQLiteDatabase) {
            db.execSQL("ALTER TABLE cached_meals ADD COLUMN mealRole TEXT")
        }
    }

    private val Migration12To13 = object : Migration(12, 13) {
        override fun migrate(db: SupportSQLiteDatabase) {
            db.execSQL("ALTER TABLE cached_day_totals ADD COLUMN activitySource TEXT")
        }
    }

    private val Migration13To14 = object : Migration(13, 14) {
        override fun migrate(db: SupportSQLiteDatabase) {
            db.execSQL(
                """
                CREATE TABLE IF NOT EXISTS photo_estimate_logs (
                    id TEXT NOT NULL PRIMARY KEY,
                    traceId TEXT NOT NULL,
                    outboxId TEXT,
                    idempotencyKey TEXT,
                    source TEXT,
                    eventType TEXT NOT NULL,
                    eventAt INTEGER NOT NULL,
                    capturedAt INTEGER,
                    serverMealId TEXT,
                    estimateStatus TEXT,
                    attempt INTEGER,
                    totalElapsedMs INTEGER,
                    queuedDelayMs INTEGER,
                    uploadDurationMs INTEGER,
                    retryDelayMs INTEGER,
                    httpStatus INTEGER,
                    errorCode TEXT,
                    errorMessage TEXT,
                    detailJson TEXT,
                    sentAt INTEGER
                )
                """.trimIndent(),
            )
            db.execSQL("CREATE INDEX IF NOT EXISTS index_photo_estimate_logs_sentAt ON photo_estimate_logs(sentAt)")
            db.execSQL("CREATE INDEX IF NOT EXISTS index_photo_estimate_logs_traceId ON photo_estimate_logs(traceId)")
        }
    }

    private fun migrateLegacyReadyMealRows(db: SupportSQLiteDatabase) {
        val cursor = db.query("SELECT id, kindJson, draftJson FROM outbox WHERE kindType = 'accept_draft'")
        cursor.use {
            while (it.moveToNext()) {
                val id = it.getString(0)
                val kindJson = it.getString(1)
                val draftJson = if (it.isNull(2)) null else it.getString(2)
                val draft = draftJson?.let { json -> OpenApiJson.json.parseToJsonElement(json) } ?: continue
                val kind = OpenApiJson.json.parseToJsonElement(kindJson).jsonObject
                val draftObject = draft.jsonObject
                val rewritten = buildJsonObject {
                    put("type", "create_meal")
                    put("payload", draft)
                    put("eatenAt", kind["eatenAt"] ?: draftObject.getValue("eatenAt"))
                    put("source", "photo")
                    put("items", kind["items"] ?: draftObject["items"] ?: JsonArray(emptyList()))
                }.toString()
                db.execSQL(
                    "UPDATE outbox SET kindType = 'create_meal', kindJson = ?, localPhotoPath = ? WHERE id = ?",
                    arrayOf(
                        rewritten,
                        draftObject["localPhotoPath"]?.jsonPrimitive?.contentOrNull,
                        id,
                    ),
                )
            }
        }
    }
}
