package com.local.glucotracker.data.local

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.media.ExifInterface
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.ByteArrayOutputStream
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
        val optimized = writeOptimizedJpeg(source, file)
        if (!optimized) {
            source.copyTo(file, overwrite = true)
        }
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
        fun optimizedUploadBytes(source: File): ByteArray? =
            decodeOptimizedJpeg(source)

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

private const val MaxUploadDimensionPx = 1600
private const val TargetUploadBytes = 1_200_000

private fun sampleSizeFor(width: Int, height: Int): Int {
    var sample = 1
    while (width / sample > MaxUploadDimensionPx ||
        height / sample > MaxUploadDimensionPx
    ) {
        sample *= 2
    }
    return sample
}

private fun Bitmap.scaleWithin(maxDimension: Int): Bitmap {
    val longest = maxOf(width, height)
    if (longest <= maxDimension) return this
    val scale = maxDimension.toFloat() / longest.toFloat()
    val nextWidth = (width * scale).toInt().coerceAtLeast(1)
    val nextHeight = (height * scale).toInt().coerceAtLeast(1)
    return Bitmap.createScaledBitmap(this, nextWidth, nextHeight, true)
}

private fun Bitmap.applyExifOrientation(source: File): Bitmap {
    val orientation = runCatching {
        ExifInterface(source.absolutePath).getAttributeInt(
            ExifInterface.TAG_ORIENTATION,
            ExifInterface.ORIENTATION_NORMAL,
        )
    }.getOrDefault(ExifInterface.ORIENTATION_NORMAL)
    val matrix = Matrix()
    when (orientation) {
        ExifInterface.ORIENTATION_ROTATE_90 -> matrix.postRotate(90f)
        ExifInterface.ORIENTATION_ROTATE_180 -> matrix.postRotate(180f)
        ExifInterface.ORIENTATION_ROTATE_270 -> matrix.postRotate(270f)
        ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> matrix.preScale(-1f, 1f)
        ExifInterface.ORIENTATION_FLIP_VERTICAL -> matrix.preScale(1f, -1f)
        ExifInterface.ORIENTATION_TRANSPOSE -> {
            matrix.postRotate(90f)
            matrix.preScale(-1f, 1f)
        }
        ExifInterface.ORIENTATION_TRANSVERSE -> {
            matrix.postRotate(270f)
            matrix.preScale(-1f, 1f)
        }
        else -> return this
    }
    return Bitmap.createBitmap(this, 0, 0, width, height, matrix, true)
}

private fun Bitmap.compressForUpload(): ByteArray {
    for (quality in listOf(84, 78, 72, 68)) {
        val output = ByteArrayOutputStream()
        compress(Bitmap.CompressFormat.JPEG, quality, output)
        val bytes = output.toByteArray()
        if (bytes.size <= TargetUploadBytes || quality == 68) {
            return bytes
        }
    }
    error("Unreachable upload compression quality loop.")
}

private fun writeOptimizedJpeg(source: File, destination: File): Boolean {
    val bytes = decodeOptimizedJpeg(source) ?: return false
    destination.writeBytes(bytes)
    return true
}

private fun decodeOptimizedJpeg(source: File): ByteArray? {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeFile(source.absolutePath, bounds)
    if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null

    val decodeOptions = BitmapFactory.Options().apply {
        inSampleSize = sampleSizeFor(bounds.outWidth, bounds.outHeight)
    }
    val decoded = BitmapFactory.decodeFile(source.absolutePath, decodeOptions) ?: return null
    val scaled = decoded.scaleWithin(MaxUploadDimensionPx)
    if (scaled !== decoded) decoded.recycle()
    val oriented = scaled.applyExifOrientation(source)
    if (oriented !== scaled) scaled.recycle()

    return try {
        oriented.compressForUpload()
    } finally {
        oriented.recycle()
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
