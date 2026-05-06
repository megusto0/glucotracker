package com.local.glucotracker.data.local

import android.content.Context
import android.media.ExifInterface
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.datetime.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

@Singleton
class PhotoStorage @Inject constructor(
    @ApplicationContext context: Context,
) {
    private val photosDir: File = File(context.filesDir, "photos")

    fun saveJpeg(
        bytes: ByteArray,
        capturedAt: Instant,
        id: String = UUID.randomUUID().toString(),
    ): File {
        val file = File(photosDir.also { it.mkdirs() }, "$id.jpg")
        file.writeBytes(bytes)
        writeOriginalCaptureTime(file, capturedAt)
        return file
    }

    fun copyIntoStorage(
        source: File,
        capturedAt: Instant,
        id: String = UUID.randomUUID().toString(),
    ): File {
        val file = File(photosDir.also { it.mkdirs() }, "$id.jpg")
        source.copyTo(file, overwrite = true)
        writeOriginalCaptureTime(file, capturedAt)
        return file
    }

    fun sweepOrphans(referencedPaths: Set<String>): Int =
        sweepOrphans(photosDir, referencedPaths)

    private fun writeOriginalCaptureTime(file: File, capturedAt: Instant) {
        val exif = ExifInterface(file.absolutePath)
        exif.setAttribute(ExifInterface.TAG_DATETIME_ORIGINAL, capturedAt.toExifDateTime())
        exif.saveAttributes()
    }

    companion object {
        fun sweepOrphans(photosDir: File, referencedPaths: Set<String>): Int {
            val files = photosDir.listFiles()?.filter { it.isFile }.orEmpty()
            var deleted = 0
            files.forEach { file ->
                if (file.absolutePath !in referencedPaths && file.canonicalPath !in referencedPaths) {
                    if (file.delete()) deleted += 1
                }
            }
            return deleted
        }
    }
}

private fun Instant.toExifDateTime(): String {
    val dateTime = toLocalDateTime(TimeZone.currentSystemDefault())
    return buildString {
        append(dateTime.year.toString().padStart(4, '0'))
        append(':')
        append(dateTime.monthNumber.toString().padStart(2, '0'))
        append(':')
        append(dateTime.dayOfMonth.toString().padStart(2, '0'))
        append(' ')
        append(dateTime.hour.toString().padStart(2, '0'))
        append(':')
        append(dateTime.minute.toString().padStart(2, '0'))
        append(':')
        append(dateTime.second.toString().padStart(2, '0'))
    }
}
