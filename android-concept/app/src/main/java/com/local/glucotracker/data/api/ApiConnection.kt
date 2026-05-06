package com.local.glucotracker.data.api

object ApiConnection {
    const val BASE_URL: String = "http://192.168.3.6:8000"
    const val TOKEN: String = "dev"

    fun resolveUrl(value: String): String =
        when {
            isHttpUrl(value) -> value
            value.startsWith("/") -> BASE_URL.trimEnd('/') + value
            else -> BASE_URL.trimEnd('/') + "/$value"
        }

    fun isHttpUrl(value: String): Boolean =
        value.startsWith("http://", ignoreCase = true) ||
            value.startsWith("https://", ignoreCase = true)

    fun isSameApiUrl(value: String): Boolean =
        value.startsWith(BASE_URL.trimEnd('/'), ignoreCase = true)

    fun isApiRelativeUrl(value: String): Boolean =
        value.startsWith("/photos/") ||
            value.startsWith("/products/") ||
            value.startsWith("photos/") ||
            value.startsWith("products/")
}
