package com.local.glucotracker.data.sync

import androidx.work.ExistingWorkPolicy
import org.junit.Assert.assertEquals
import org.junit.Test

class OutboxWorkerPolicyTest {
    @Test
    fun immediateWorkDoesNotReplaceAnActivePhotoEstimate() {
        assertEquals(ExistingWorkPolicy.APPEND_OR_REPLACE, ImmediateWorkPolicy)
    }
}
