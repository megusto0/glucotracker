package com.local.glucotracker.ui.image

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import coil3.network.NetworkHeaders
import coil3.network.httpHeaders
import coil3.request.ImageRequest
import com.local.glucotracker.data.api.ApiConnection
import java.io.File

private val ApiImageHeaders = NetworkHeaders.Builder()
    .set("Authorization", "Bearer ${ApiConnection.TOKEN}")
    .build()

@Composable
fun rememberApiImageModel(model: Any?): Any? {
    val context = LocalContext.current
    return remember(context, model) {
        apiImageModel(context, model)
    }
}

fun apiImageModel(context: Context, model: Any?): Any? =
    when (model) {
        null -> null
        is String -> model.trim().takeIf { it.isNotEmpty() }?.let { value ->
            when {
                ApiConnection.isApiRelativeUrl(value) || ApiConnection.isSameApiUrl(value) ->
                    ImageRequest.Builder(context)
                        .data(ApiConnection.resolveUrl(value))
                        .httpHeaders(ApiImageHeaders)
                        .build()

                ApiConnection.isHttpUrl(value) -> value
                value.startsWith("/") || value.contains(":\\") -> File(value)
                else -> value
            }
        }
        else -> model
    }
