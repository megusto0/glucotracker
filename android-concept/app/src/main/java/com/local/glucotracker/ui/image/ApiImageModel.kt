package com.local.glucotracker.ui.image

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.runtime.State
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil3.network.NetworkHeaders
import coil3.network.httpHeaders
import coil3.request.CachePolicy
import coil3.request.ImageRequest
import com.local.glucotracker.data.api.ApiConnection
import com.local.glucotracker.data.auth.TokenStore
import dagger.hilt.EntryPoint
import dagger.hilt.InstallIn
import dagger.hilt.android.EntryPointAccessors
import dagger.hilt.components.SingletonComponent
import java.io.File
import kotlinx.coroutines.flow.map

@Composable
fun rememberApiImageModel(model: Any?): Any? {
    val context = LocalContext.current
    val appContext = context.applicationContext
    val tokenStore = remember(appContext) {
        runCatching {
            EntryPointAccessors.fromApplication(
                appContext,
                ApiImageEntryPoint::class.java,
            ).tokenStore()
        }.getOrNull()
    }
    val accessTokenState: State<String?> = if (tokenStore == null) {
        remember { mutableStateOf(null) }
    } else {
        val accessTokenFlow = remember(tokenStore) {
            tokenStore.observeSession().map { it?.accessToken }
        }
        accessTokenFlow.collectAsStateWithLifecycle(initialValue = tokenStore.lastAccessToken)
    }
    val accessToken by accessTokenState
    return remember(context, model, accessToken) {
        apiImageModel(context, model, accessToken)
    }
}

fun apiImageModel(context: Context, model: Any?, accessToken: String? = null): Any? =
    when (model) {
        null -> null
        is String -> model.trim().takeIf { it.isNotEmpty() }?.let { value ->
            when {
                ApiConnection.isApiImageUrl(value) && accessToken != null ->
                    ImageRequest.Builder(context)
                        .data(ApiConnection.resolveUrl(value))
                        .memoryCacheKey(ApiConnection.imageCacheKey(value))
                        .diskCacheKey(ApiConnection.imageCacheKey(value))
                        .memoryCachePolicy(CachePolicy.ENABLED)
                        .diskCachePolicy(CachePolicy.ENABLED)
                        .networkCachePolicy(CachePolicy.ENABLED)
                        .httpHeaders(
                            NetworkHeaders.Builder()
                                .set("Authorization", "Bearer $accessToken")
                                .build(),
                        )
                        .build()

                ApiConnection.isApiImageUrl(value) -> null
                ApiConnection.isHttpUrl(value) -> value
                value.startsWith("/") || value.contains(":\\") -> File(value)
                else -> value
            }
        }
        else -> model
    }

@EntryPoint
@InstallIn(SingletonComponent::class)
private interface ApiImageEntryPoint {
    fun tokenStore(): TokenStore
}
