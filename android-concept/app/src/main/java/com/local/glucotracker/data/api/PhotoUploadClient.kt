package com.local.glucotracker.data.api

import com.local.glucotracker.generated.model.PhotoResponse
import com.local.glucotracker.data.sync.OutboxConflictException
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

class PhotoUploadClient @Inject constructor(
    @Named("apiBaseUrl") private val baseUrl: String,
    private val client: HttpClient,
) {
    suspend fun uploadMealPhoto(mealId: UUID, localPhotoPath: String): PhotoResponse {
        val file = File(localPhotoPath)
        val response = client.post("$baseUrl/meals/$mealId/photos") {
            setBody(
                MultiPartFormDataContent(
                    formData {
                        append(
                            key = "file",
                            value = file.readBytes(),
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
        if (response.status.value !in 200..299) throw IOException("HTTP ${response.status.value}")
        return response.body()
    }
}
