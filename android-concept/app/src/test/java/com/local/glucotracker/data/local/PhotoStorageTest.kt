package com.local.glucotracker.data.local

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class PhotoStorageTest {
    @get:Rule
    val temporaryFolder = TemporaryFolder()

    @Test
    fun orphanSweepKeepsReferencedFilesAndDeletesUnreferencedFiles() {
        val photosDir = temporaryFolder.newFolder("photos")
        val referenced = File(photosDir, "referenced.jpg").apply { writeText("keep") }
        val orphan = File(photosDir, "orphan.jpg").apply { writeText("delete") }

        val deleted = PhotoStorage.sweepOrphans(
            photosDir = photosDir,
            referencedPaths = setOf(referenced.absolutePath),
        )

        assertEquals(1, deleted)
        assertTrue(referenced.exists())
        assertFalse(orphan.exists())
    }
}
