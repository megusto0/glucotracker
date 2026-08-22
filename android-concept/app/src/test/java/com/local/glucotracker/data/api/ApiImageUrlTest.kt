package com.local.glucotracker.data.api

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ApiImageUrlTest {
    @Test
    fun everyPathTheServerKeepsPicturesUnderIsRecognised() {
        // Each of these needs the host and the bearer token attached; a prefix
        // missing from the list is a row that silently draws nothing.
        assertTrue(ApiConnection.isApiImageUrl("/photos/abc/file"))
        assertTrue(ApiConnection.isApiImageUrl("/products/abc/image/file"))
        assertTrue(ApiConnection.isApiImageUrl("/uploaded-media/abc.jpg"))
        assertTrue(ApiConnection.isApiImageUrl("/fridge/mealpreps/abc/photo"))
    }

    @Test
    fun templateAndRestaurantPicturesAreRecognisedToo() {
        // The one that was missing: 148 cached templates are served from here.
        assertTrue(
            ApiConnection.isApiImageUrl("/patterns/93569f11-0400-4866-b762-5bff65a3a1ff/image/file"),
        )
    }

    @Test
    fun somebodyElsesPictureIsLeftAlone() {
        assertFalse(ApiConnection.isApiImageUrl("https://avatars.mds.yandex.net/get-eda/1/2/400x400"))
        assertFalse(ApiConnection.isApiImageUrl("/some/other/path.jpg"))
    }
}
