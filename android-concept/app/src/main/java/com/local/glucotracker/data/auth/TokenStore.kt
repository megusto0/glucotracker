package com.local.glucotracker.data.auth

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import java.io.IOException
import java.security.GeneralSecurityException
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.withContext
import kotlinx.datetime.Instant

@Singleton
class TokenStore @Inject constructor(
    @ApplicationContext context: Context,
) {
    private val appContext = context.applicationContext
    private val changes = MutableSharedFlow<Unit>(replay = 1)

    @Volatile
    private var _lastAccessToken: String? = null
    val lastAccessToken: String? get() = _lastAccessToken

    private val prefs by lazy {
        val masterKey = MasterKey.Builder(appContext)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            appContext,
            AuthPrefsName,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    init {
        changes.tryEmit(Unit)
    }

    fun observeSession(): Flow<AuthSession?> =
        changes
            .map { readSession() }
            .distinctUntilChanged()

    suspend fun readSession(): AuthSession? = withContext(Dispatchers.IO) {
        runCatching {
            readSessionUnsafe(prefs)
        }.getOrElse { throwable ->
            if (!throwable.isRecoverableAuthStorageFailure()) throw throwable
            resetAuthStorage()
            null
        }
    }.also { _lastAccessToken = it?.accessToken }

    private fun readSessionUnsafe(prefs: SharedPreferences): AuthSession? {
        val access = prefs.getString(KeyAccessToken, null) ?: return null
        val refresh = prefs.getString(KeyRefreshToken, null) ?: return null
        val accessExpiry = prefs.getString(KeyAccessExpiry, null) ?: return null
        val userId = prefs.getString(KeyUserId, null) ?: return null
        val role = prefs.getString(KeyRole, null) ?: return null
        return runCatching {
            AuthSession(
                accessToken = access,
                refreshToken = refresh,
                accessExpiresAt = Instant.parse(accessExpiry),
                userId = UUID.fromString(userId),
                role = role,
            )
        }.getOrNull()
    }

    suspend fun save(session: AuthSession) {
        withContext(Dispatchers.IO) {
            val committed = runCatching {
                writeSession(prefs, session)
            }.getOrElse { throwable ->
                if (!throwable.isRecoverableAuthStorageFailure()) throw throwable
                resetAuthStorage()
                writeSession(prefs, session)
            }
            if (!committed) throw AuthException("Could not save auth session.")
        }
        _lastAccessToken = session.accessToken
        changes.emit(Unit)
    }

    suspend fun clear() {
        _lastAccessToken = null
        withContext(Dispatchers.IO) {
            val committed = runCatching {
                prefs.edit().clear().commit()
            }.getOrElse { throwable ->
                if (!throwable.isRecoverableAuthStorageFailure()) throw throwable
                resetAuthStorage()
            }
            if (!committed) throw AuthException("Could not clear auth session.")
        }
        changes.emit(Unit)
    }

    private fun writeSession(prefs: SharedPreferences, session: AuthSession): Boolean =
        prefs.edit()
            .putString(KeyAccessToken, session.accessToken)
            .putString(KeyRefreshToken, session.refreshToken)
            .putString(KeyAccessExpiry, session.accessExpiresAt.toString())
            .putString(KeyUserId, session.userId.toString())
            .putString(KeyRole, session.role)
            .commit()

    private fun resetAuthStorage(): Boolean {
        val cleared = runCatching {
            appContext.getSharedPreferences(AuthPrefsName, Context.MODE_PRIVATE)
                .edit()
                .clear()
                .commit()
        }.getOrDefault(false)
        val deleted = runCatching {
            File(appContext.applicationInfo.dataDir, "shared_prefs/$AuthPrefsName.xml").delete()
        }.getOrDefault(false)
        return cleared || deleted
    }

    private fun Throwable.isRecoverableAuthStorageFailure(): Boolean =
        this is GeneralSecurityException ||
            this is IOException ||
            this is SecurityException ||
            this is IllegalStateException ||
            this is IllegalArgumentException

    private companion object {
        const val AuthPrefsName = "gt_auth_tokens"
        const val KeyAccessToken = "access_token"
        const val KeyRefreshToken = "refresh_token"
        const val KeyAccessExpiry = "access_expires_at"
        const val KeyUserId = "user_id"
        const val KeyRole = "role"
    }
}
