package com.local.glucotracker.data.sync

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NotificationStringsTest {
    @Test
    fun syncNotificationStringsArePresentAndAvoidTreatmentLanguage() {
        val strings = File("src/main/res/values/strings.xml").readText()

        assertTrue(strings.contains("notification_estimate_ready_title"))
        assertTrue(strings.contains("notification_photo_upload_text"))

        listOf("доз", "болюс", "коррекц", "целев").forEach { forbidden ->
            assertFalse(strings.lowercase().contains(forbidden))
        }
    }
}
