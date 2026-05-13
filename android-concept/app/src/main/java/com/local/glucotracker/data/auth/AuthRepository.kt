package com.local.glucotracker.data.auth

import com.local.glucotracker.generated.api.AuthApi
import com.local.glucotracker.generated.model.LoginRequest
import com.local.glucotracker.generated.model.LogoutRequest
import com.local.glucotracker.generated.model.RefreshRequest
import com.local.glucotracker.generated.model.IssuedTokensResponse
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
    private val refreshMutex = Mutex()

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
            val me = authApi.getAuthMe(authorization = issued.authorizationHeader())
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
        refreshMutex.withLock {
            runCatching {
                val session = tokenStore.readSession() ?: throw AuthException("No auth session.")
                if (!force && !session.needsRefresh()) return@runCatching

                val response = authApi.refreshAuthToken(
                    RefreshRequest(refreshToken = session.refreshToken),
                )
                if (!response.success) {
                    tokenStore.clear()
                    throw AuthException("Refresh failed.")
                }

                val issued = response.body()
                val me = authApi.getAuthMe(authorization = issued.authorizationHeader())
                if (!me.success) {
                    tokenStore.clear()
                    throw AuthException("Could not load current user.")
                }

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

    suspend fun clearLocalSession() {
        tokenStore.clear()
    }
}

private fun AuthSession.needsRefresh(): Boolean {
    val nowWithSkew = Clock.System.now().toEpochMilliseconds() + RefreshSkewMillis
    return accessExpiresAt.toEpochMilliseconds() <= nowWithSkew
}

private fun IssuedTokensResponse.authorizationHeader(): String =
    "Bearer $access"

private const val RefreshSkewMillis = 60_000L
