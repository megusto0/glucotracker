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
        assertTrue(ApiConnection.isSameApiUrl("${ApiConnection.BASE_URL}/photos/456/file"))
    }
}
