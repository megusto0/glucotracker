package com.local.glucotracker.ui.feature.capture

import android.content.Context
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.data.local.PhotoStorage
import com.local.glucotracker.data.repository.BrandPrefix
import com.local.glucotracker.data.settings.SettingsStore
import com.local.glucotracker.data.telemetry.PhotoEstimateTelemetryLogger
import com.local.glucotracker.domain.model.MealDraft
import com.local.glucotracker.domain.model.MealItemPayload
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.Product
import com.local.glucotracker.domain.model.Template
import com.local.glucotracker.domain.repository.OutboxRepository
import com.local.glucotracker.domain.repository.ProductsRepository
import com.local.glucotracker.ui.feature.mealentry.toProductMealKind
import com.local.glucotracker.ui.feature.mealentry.toTemplateMealKind
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import java.util.UUID
import javax.inject.Inject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant

@HiltViewModel
class CaptureViewModel @Inject constructor(
    private val outboxRepository: OutboxRepository,
    private val productsRepository: ProductsRepository,
    private val photoStorage: PhotoStorage,
    private val settingsStore: SettingsStore,
    private val photoTelemetryLogger: PhotoEstimateTelemetryLogger,
    @ApplicationContext private val context: Context,
) : ViewModel() {
    val composeSheetOpenCount = settingsStore.composeSheetOpenCount

    fun enqueueCameraPhoto(tempFile: File, capturedAt: Instant, onQueued: (String) -> Unit) {
        viewModelScope.launch {
            val storedFile = withContext(Dispatchers.IO) {
                photoStorage.copyIntoStorage(tempFile, capturedAt).also {
                    tempFile.delete()
                }
            }
            val item = outboxRepository.enqueue(
                OutboxKind.CapturedMeal(
                    localPhotoPath = storedFile.absolutePath,
                    capturedAt = capturedAt,
                    source = "photo",
                    idempotencyKey = UUID.randomUUID().toString(),
                ),
            )
            (item.kind as? OutboxKind.CapturedMeal)?.let { kind ->
                photoTelemetryLogger.captureQueued(item.id, kind)
            }
            onQueued(item.id)
        }
    }

    fun enqueueGalleryPhoto(uri: Uri, onQueued: (String) -> Unit) {
        viewModelScope.launch {
            val capturedAt = withContext(Dispatchers.IO) { readGalleryCapturedAt(uri) } ?: Clock.System.now()
            val storedFile = withContext(Dispatchers.IO) {
                val tempFile = copyUriToTemp(uri)
                photoStorage.copyIntoStorage(tempFile, capturedAt).also {
                    tempFile.delete()
                }
            }
            val item = outboxRepository.enqueue(
                OutboxKind.CapturedMeal(
                    localPhotoPath = storedFile.absolutePath,
                    capturedAt = capturedAt,
                    source = "gallery",
                    idempotencyKey = UUID.randomUUID().toString(),
                ),
            )
            (item.kind as? OutboxKind.CapturedMeal)?.let { kind ->
                photoTelemetryLogger.captureQueued(item.id, kind)
            }
            onQueued(item.id)
        }
    }

    fun onComposeSheetOpened() {
        viewModelScope.launch {
            settingsStore.incrementComposeSheetOpenCount()
        }
    }

    fun enqueueTextMeal(query: String, weightGrams: Double? = null, onQueued: (String) -> Unit = {}) {
        viewModelScope.launch {
            val now = Clock.System.now()
            val item = outboxRepository.enqueue(
                OutboxKind.CapturedMeal(
                    localPhotoPath = null,
                    capturedAt = now,
                    source = "text",
                    optimisticName = query.trim(),
                    optimisticWeightG = weightGrams?.toInt(),
                ),
            )
            onQueued(item.id)
        }
    }

    fun enqueueProductMeal(product: Product, weightGrams: Double?, onQueued: (String) -> Unit = {}) {
        viewModelScope.launch {
            val item = outboxRepository.enqueue(product.toProductMealKind(weightGrams = weightGrams))
            onQueued(item.id)
        }
    }

    fun enqueueFromTemplate(template: Template, weightGrams: Double?, onQueued: (String) -> Unit = {}) {
        viewModelScope.launch {
            val item = outboxRepository.enqueue(template.toTemplateMealKind(weightGrams = weightGrams))
            onQueued(item.id)
        }
    }

    fun deletePendingCapture(outboxId: String) {
        viewModelScope.launch {
            outboxRepository.remove(outboxId)
        }
    }

    fun searchProducts(query: String, prefix: BrandPrefix? = null, callback: (List<Product>) -> Unit) {
        viewModelScope.launch {
            val results = productsRepository.searchLocal(query, prefix = prefix)
            callback(results)
        }
    }

    fun searchTemplates(query: String, callback: (List<Template>) -> Unit) {
        viewModelScope.launch {
            val results = productsRepository.searchTemplatesLocal(query)
            callback(results)
        }
    }

    private suspend fun estimateKcalForText(query: String, weightGrams: Double): Double {
        val products = productsRepository.searchLocal(query, limit = 1)
        val product = products.firstOrNull()
        return product?.kcal?.let { per100 ->
            per100 * (weightGrams / 100.0)
        } ?: 0.0
    }

    private fun readGalleryCapturedAt(uri: Uri): Instant? =
        readExifCapturedAt(uri) ?: readMediaModifiedAt(uri)

    private fun readExifCapturedAt(uri: Uri): Instant? {
        return try {
            context.contentResolver.openInputStream(uri)?.use { input ->
                val exif = android.media.ExifInterface(input)
                val dateTimeStr = exif.getAttribute(android.media.ExifInterface.TAG_DATETIME_ORIGINAL)
                if (dateTimeStr != null) {
                    val sdf = java.text.SimpleDateFormat("yyyy:MM:dd HH:mm:ss", java.util.Locale.US)
                    val date = sdf.parse(dateTimeStr) ?: return null
                    Instant.fromEpochMilliseconds(date.time)
                } else {
                    null
                }
            }
        } catch (_: Exception) {
            null
        }
    }

    private fun readMediaModifiedAt(uri: Uri): Instant? {
        return try {
            val projection = arrayOf(android.provider.MediaStore.MediaColumns.DATE_MODIFIED)
            context.contentResolver.query(uri, projection, null, null, null)?.use { cursor ->
                val index = cursor.getColumnIndex(android.provider.MediaStore.MediaColumns.DATE_MODIFIED)
                if (index < 0 || !cursor.moveToFirst()) {
                    null
                } else {
                    val seconds = cursor.getLong(index)
                    seconds.takeIf { it > 0L }?.let { Instant.fromEpochSeconds(it) }
                }
            }
        } catch (_: Exception) {
            null
        }
    }

    private fun copyUriToTemp(uri: Uri): File {
        val tempFile = File.createTempFile("gallery_", ".jpg", context.cacheDir)
        context.contentResolver.openInputStream(uri)?.use { input ->
            tempFile.outputStream().use { output -> input.copyTo(output) }
        }
        return tempFile
    }
}
