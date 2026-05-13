package com.local.glucotracker.data.api

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ApiConnectionTest {
    @Test
    fun resolvesRelativeApiImageUrlsAgainstBaseUrl() {
        assertEquals(
            "${ApiConnection.BASE_URL}/products/123/image/file",
            ApiConnection.resolveUrl("/products/123/image/file"),
        )
        assertEquals(
            "${ApiConnection.BASE_URL}/photos/456/file",
            ApiConnection.resolveUrl("photos/456/file"),
        )
    }

    @Test
    fun keepsExternalUrlsUnchanged() {
        val url = "https://example.test/item.png"

        assertEquals(url, ApiConnection.resolveUrl(url))
        assertFalse(ApiConnection.isApiRelativeUrl(url))
    }

    @Test
    fun detectsApiOwnedImageUrls() {
        assertTrue(ApiConnection.isApiRelativeUrl("/photos/456/file"))
        assertTrue(ApiConnection.isApiRelativeUrl("/products/123/image/file"))
        assertTrue(ApiConnection.isApiRelativeUrl(" photos/456/file "))
        assertTrue(ApiConnection.isApiImageUrl("${ApiConnection.BASE_URL}/products/123/image/file"))
        assertTrue(ApiConnection.isSameApiUrl("${ApiConnection.BASE_URL}/photos/456/file"))
        assertFalse(ApiConnection.isSameApiUrl("${ApiConnection.BASE_URL}.evil.test/photos/456/file"))
    }

    @Test
    fun usesStableCacheKeysForApiImages() {
        assertEquals(
            "/photos/456/file",
            ApiConnection.imageCacheKey("${ApiConnection.BASE_URL}/photos/456/file"),
        )
        assertEquals(
            "/products/123/image/file",
            ApiConnection.imageCacheKey("products/123/image/file"),
        )
    }

    @Test
    fun resolvesAgainstInjectedBaseUrl() {
        assertEquals(
            "http://10.0.2.2:8000/photos/456/file",
            ApiConnection.resolveUrl("/photos/456/file", baseUrl = "http://10.0.2.2:8000/"),
        )
    }
}
