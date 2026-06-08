package com.local.glucotracker.data.auth

import com.local.glucotracker.generated.api.AuthApi
import com.local.glucotracker.generated.model.LoginRequest
import com.local.glucotracker.generated.model.LogoutRequest
import com.local.glucotracker.generated.model.RefreshRequest
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.datetime.Clock

@Singleton
class AuthRepository @Inject constructor(
    private val tokenStore: TokenStore,
    private val authApi: AuthApi,
) {
    fun observeSession(): Flow<AuthSession?> =
        tokenStore.observeSession()

    suspend fun currentAccessToken(): String? =
        tokenStore.readSession()?.accessToken

    suspend fun login(username: String, password: String): Result<AuthSession> =
        runCatching {
            val tokens = authApi.login(
                LoginRequest(username = username, password = password),
            )
            if (!tokens.success) throw AuthException("Invalid credentials.")

            val issued = tokens.body()
            val me = authApi.getAuthMeWithAccessToken(issued.access)
            if (!me.success) throw AuthException("Could not load current user.")

            val user = me.body()
            AuthSession(
                accessToken = issued.access,
                refreshToken = issued.refresh,
                accessExpiresAt = issued.accessExpiresAt,
                userId = user.id,
                role = user.role.value,
            ).also { tokenStore.save(it) }
        }

    suspend fun logout() {
        val session = tokenStore.readSession()
        if (session != null) {
            runCatching {
                authApi.setBearerToken(session.accessToken)
                authApi.logout(
                    logoutRequest = LogoutRequest(refreshToken = session.refreshToken),
                )
            }
        }
        tokenStore.clear()
    }

    suspend fun refreshIfNeeded(force: Boolean = false): Result<Unit> =
        RefreshMutex.withLock {
            runCatching {
                val session = tokenStore.readSession() ?: throw AuthException("No auth session.")
                if (!force && !session.needsRefresh()) return@runCatching

                val response = authApi.refreshAuthToken(
                    RefreshRequest(refreshToken = session.refreshToken),
                )
                if (!response.success) {
                    if (tokenStore.hasFreshReplacementFor(session)) return@runCatching
                    tokenStore.clear()
                    throw AuthException("Refresh failed.")
                }

                val issued = response.body()
                val refreshedSession = AuthSession(
                    accessToken = issued.access,
                    refreshToken = issued.refresh,
                    accessExpiresAt = issued.accessExpiresAt,
                    userId = session.userId,
                    role = session.role,
                )
                tokenStore.save(refreshedSession)

                val me = authApi.getAuthMeWithAccessToken(issued.access)
                if (!me.success) return@runCatching

                val user = me.body()
                tokenStore.save(
                    AuthSession(
                        accessToken = issued.access,
                        refreshToken = issued.refresh,
                        accessExpiresAt = issued.accessExpiresAt,
                        userId = user.id,
                        role = user.role.value,
                    ),
                )
            }
        }

    private companion object {
        val RefreshMutex = Mutex()
    }
}

private fun AuthSession.needsRefresh(): Boolean {
    val nowWithSkew = Clock.System.now().toEpochMilliseconds() + RefreshSkewMillis
    return accessExpiresAt.toEpochMilliseconds() <= nowWithSkew
}

private suspend fun TokenStore.hasFreshReplacementFor(previous: AuthSession): Boolean {
    val latest = readSession() ?: return false
    return latest.refreshToken != previous.refreshToken && !latest.needsRefresh()
}

private suspend fun AuthApi.getAuthMeWithAccessToken(
    accessToken: String,
) = run {
    setBearerToken(accessToken)
    getAuthMe()
}

private const val RefreshSkewMillis = 60_000L
