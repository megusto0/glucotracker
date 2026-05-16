package com.local.glucotracker.data.auth

import io.ktor.client.HttpClientConfig
import io.ktor.client.plugins.api.Send
import io.ktor.client.plugins.api.createClientPlugin
import io.ktor.client.request.HttpRequestBuilder
import io.ktor.client.request.header
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.encodedPath

class AuthPluginConfig {
    lateinit var authRepository: AuthRepository
    var clientName: String = "android"
}

val AuthPlugin = createClientPlugin("AuthPlugin", ::AuthPluginConfig) {
    val authRepository = pluginConfig.authRepository
    val clientName = pluginConfig.clientName

    onRequest { request, _ ->
        request.prepareAuthRequest(authRepository, clientName)
    }

    on(Send) { request ->
        val originalCall = proceed(request)
        if (
            originalCall.response.status == HttpStatusCode.Unauthorized &&
            !request.url.encodedPath.isAuthRoute()
        ) {
            val refreshed = authRepository.refreshIfNeeded(force = true)
            if (refreshed.isSuccess) {
                request.prepareAuthRequest(authRepository, clientName)
                proceed(request)
            } else {
                originalCall
            }
        } else {
            originalCall
        }
    }
}

fun HttpClientConfig<*>.installAuthPlugin(
    authRepository: AuthRepository,
    clientName: String = "android",
) {
    install(AuthPlugin) {
        this.authRepository = authRepository
        this.clientName = clientName
    }
}

private suspend fun HttpRequestBuilder.prepareAuthRequest(
    authRepository: AuthRepository,
    clientName: String,
) {
    header("X-Glucotracker-Client", clientName)
    if (url.encodedPath.isAuthRoute()) return

    authRepository.refreshIfNeeded()
    authRepository.currentAccessToken()?.let { access ->
        headers.remove(HttpHeaders.Authorization)
        header(HttpHeaders.Authorization, "Bearer $access")
    }
}

private fun String.isAuthRoute(): Boolean =
    startsWith("/auth/login") ||
        startsWith("/auth/refresh") ||
        startsWith("/auth/logout")
