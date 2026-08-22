package com.local.glucotracker.data.api

import com.local.glucotracker.BuildConfig
import java.net.URI

object ApiConnection {
    val BASE_URL: String = BuildConfig.API_BASE_URL

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

    // Paths the server serves pictures from. A path outside this list is left
    // as the literal string it is, so Coil asks for «/uploaded-media/x.jpg»
    // against nothing and draws the empty-photo glyph — which is exactly what
    // fridge stock and meal-prep photographs did, both being served from
    // mounts that nobody had added here.
    private val API_IMAGE_PREFIXES = listOf(
        "/photos/",
        "/products/",
        // Restaurant and template pictures. A hundred and forty-eight rows in
        // the search list are served from here, and leaving the prefix out
        // meant Coil was handed a bare path with no host and no token — so
        // every Burger King and Rostic's row drew the empty glyph.
        "/patterns/",
        "/uploaded-media/",
        "/fridge/",
    )

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
        return API_IMAGE_PREFIXES.any { prefix -> path.startsWith(prefix) }
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
