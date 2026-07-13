package com.local.glucotracker.data.api

import com.local.glucotracker.data.local.PhotoStorage
import com.local.glucotracker.data.sync.OutboxConflictException
import com.local.glucotracker.data.sync.OutboxHttpException
import com.local.glucotracker.generated.model.PhotoResponse
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.forms.MultiPartFormDataContent
import io.ktor.client.request.forms.formData
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.Headers
import io.ktor.http.HttpHeaders
import java.io.IOException
import java.io.File
import java.util.UUID
import javax.inject.Inject
import javax.inject.Named
import kotlinx.datetime.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class PhotoCaptureResponse(
    @SerialName("meal_id")
    val mealId: String,
    @SerialName("estimate_status")
    val estimateStatus: String,
    @SerialName("captured_at")
    val capturedAt: Instant,
    @SerialName("photo_url")
    val photoUrl: String,
)

class PhotoUploadClient @Inject constructor(
    @Named("apiBaseUrl") private val baseUrl: String,
    private val client: HttpClient,
) {
    suspend fun createMealFromPhoto(
        localPhotoPath: String,
        capturedAt: Instant,
        source: String,
        idempotencyKey: String,
        context: String? = null,
    ): PhotoCaptureResponse {
        val file = File(localPhotoPath)
        val uploadBytes = file.bytesForUpload()
        val response = client.post("$baseUrl/meals/from-photo") {
            setBody(
                MultiPartFormDataContent(
                    formData {
                        append("captured_at", capturedAt.toWallClockIso())
                        append("source", source.toPhotoCaptureSource())
                        append("idempotency_key", idempotencyKey)
                        context?.takeIf { it.isNotBlank() }?.let {
                            append("context", it)
                        }
                        append(
                            key = "photo",
                            value = uploadBytes,
                            headers = Headers.build {
                                append(HttpHeaders.ContentType, "image/jpeg")
                                append(
                                    HttpHeaders.ContentDisposition,
                                    "form-data; name=\"photo\"; filename=\"${file.name}\"",
                                )
                            },
                        )
                    },
                ),
            )
        }
        if (response.status.value == 409) throw OutboxConflictException()
        if (response.status.value !in 200..299) {
            throw OutboxHttpException(response.status.value, "HTTP ${response.status.value}")
        }
        return response.body()
    }

    suspend fun uploadMealPhoto(mealId: UUID, localPhotoPath: String): PhotoResponse {
        val file = File(localPhotoPath)
        val uploadBytes = file.bytesForUpload()
        val response = client.post("$baseUrl/meals/$mealId/photos") {
            setBody(
                MultiPartFormDataContent(
                    formData {
                        append(
                            key = "file",
                            value = uploadBytes,
                            headers = Headers.build {
                                append(HttpHeaders.ContentType, "image/jpeg")
                                append(
                                    HttpHeaders.ContentDisposition,
                                    "form-data; name=\"file\"; filename=\"${file.name}\"",
                                )
                            },
                        )
                    },
                ),
            )
        }
        if (response.status.value == 409) throw OutboxConflictException()
        if (response.status.value !in 200..299) {
            throw OutboxHttpException(response.status.value, "HTTP ${response.status.value}")
        }
        return response.body()
    }
}

private fun String.toPhotoCaptureSource(): String =
    when (this) {
        "gallery" -> "gallery"
        else -> "camera"
    }

private fun Instant.toWallClockIso(): String =
    toLocalDateTime(TimeZone.currentSystemDefault()).toString()

private fun File.bytesForUpload(): ByteArray {
    val optimized = PhotoStorage.optimizedUploadBytes(this)
    if (optimized != null && optimized.size <= PhotoStorage.ServerMultipartPhotoByteLimit) {
        return optimized
    }

    val raw = readBytes()
    if (raw.size <= PhotoStorage.ServerMultipartPhotoByteLimit) {
        return raw
    }

    val bestSize = minOf(raw.size, optimized?.size ?: Int.MAX_VALUE)
    throw IOException(
        "photo is ${bestSize / 1024}KB; unable to optimize under the " +
            "${PhotoStorage.ServerMultipartPhotoByteLimit / 1024}KB server multipart limit",
    )
}
