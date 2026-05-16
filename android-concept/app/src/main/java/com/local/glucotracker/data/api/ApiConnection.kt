package com.local.glucotracker.data.api

import java.net.URI

object ApiConnection {
    const val BASE_URL: String = "http://192.168.3.6:8000"

    fun resolveUrl(value: String, baseUrl: String = BASE_URL): String {
        val trimmed = value.trim()
        val normalizedBase = baseUrl.trimEnd('/')
        return when {
            isHttpUrl(trimmed) -> trimmed
            trimmed.startsWith("/") -> normalizedBase + trimmed
            else -> "$normalizedBase/$trimmed"
        }
    }

    fun imageCacheKey(value: String, baseUrl: String = BASE_URL): String {
        val trimmed = value.trim()
        return when {
            isSameApiUrl(trimmed, baseUrl) -> apiPathWithQuery(trimmed)
            isApiRelativeUrl(trimmed) -> normalizeApiPath(trimmed)
            else -> trimmed
        }
    }

    fun isApiImageUrl(value: String): Boolean =
        isApiRelativeUrl(value) || isSameApiUrl(value)

    fun isHttpUrl(value: String): Boolean {
        val trimmed = value.trim()
        return trimmed.startsWith("http://", ignoreCase = true) ||
            trimmed.startsWith("https://", ignoreCase = true)
    }

    fun isSameApiUrl(value: String): Boolean =
        isSameApiUrl(value, BASE_URL)

    fun isApiRelativeUrl(value: String): Boolean {
        val path = normalizeApiPath(value)
        return path.startsWith("/photos/") || path.startsWith("/products/")
    }

    private fun normalizeApiPath(value: String): String =
        when {
            isHttpUrl(value) -> value.trim()
            else -> "/" + value.trim().trimStart('/')
        }

    private fun isSameApiUrl(value: String, baseUrl: String): Boolean {
        val valueUri = value.toUriOrNull() ?: return false
        val baseUri = baseUrl.toUriOrNull() ?: return false
        return valueUri.scheme.equals(baseUri.scheme, ignoreCase = true) &&
            valueUri.host.equals(baseUri.host, ignoreCase = true) &&
            valueUri.normalizedPort() == baseUri.normalizedPort()
    }

    private fun apiPathWithQuery(value: String): String {
        val uri = value.toUriOrNull() ?: return value.trim()
        val path = uri.rawPath?.ifBlank { "/" } ?: "/"
        val query = uri.rawQuery?.let { "?$it" }.orEmpty()
        return path + query
    }

    private fun String.toUriOrNull(): URI? =
        runCatching { URI(this.trim()) }.getOrNull()

    private fun URI.normalizedPort(): Int =
        when {
            port != -1 -> port
            scheme.equals("https", ignoreCase = true) -> 443
            scheme.equals("http", ignoreCase = true) -> 80
            else -> -1
        }
}
