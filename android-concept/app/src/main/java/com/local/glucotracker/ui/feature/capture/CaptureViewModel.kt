package com.local.glucotracker.ui.feature.capture

import android.content.Context
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.data.local.PhotoStorage
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.MealDraft
import com.local.glucotracker.domain.model.MealItemPayload
import com.local.glucotracker.domain.model.Product
import com.local.glucotracker.domain.model.Template
import com.local.glucotracker.domain.repository.OutboxRepository
import com.local.glucotracker.domain.repository.ProductsRepository
import com.local.glucotracker.domain.repository.SyncRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import java.util.UUID
import javax.inject.Inject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant

@HiltViewModel
class CaptureViewModel @Inject constructor(
    private val outboxRepository: OutboxRepository,
    private val productsRepository: ProductsRepository,
    private val syncRepository: SyncRepository,
    private val photoStorage: PhotoStorage,
    @ApplicationContext private val context: Context,
) : ViewModel() {

    fun enqueueCameraPhoto(tempFile: File, capturedAt: Instant, onQueued: (String) -> Unit) {
        viewModelScope.launch {
            val storedFile = withContext(Dispatchers.IO) {
                photoStorage.copyIntoStorage(tempFile, capturedAt).also {
                    tempFile.delete()
                }
            }
            val item = outboxRepository.enqueue(
                OutboxKind.PhotoEstimateRequest(
                    localPhotoPath = storedFile.absolutePath,
                    capturedAt = capturedAt,
                    source = "photo",
                ),
            )
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
                OutboxKind.PhotoEstimateRequest(
                    localPhotoPath = storedFile.absolutePath,
                    capturedAt = capturedAt,
                    source = "gallery",
                ),
            )
            onQueued(item.id)
        }
    }

    fun enqueueTextMeal(query: String, weightGrams: Double?) {
        viewModelScope.launch {
            val now = Clock.System.now()
            val kcal = weightGrams?.let { w -> estimateKcalForText(query, w) }
            outboxRepository.enqueue(
                OutboxKind.CreateMeal(
                    payload = MealDraft(
                        id = java.util.UUID.randomUUID().toString(),
                        eatenAt = now,
                        title = query.trim(),
                        note = null,
                        localPhotoPath = null,
                        totalKcal = kcal ?: 0.0,
                        totalCarbsG = 0.0,
                        totalProteinG = 0.0,
                        totalFatG = 0.0,
                        totalFiberG = 0.0,
                    ),
                    eatenAt = now,
                    source = "text",
                    items = listOf(
                        MealItemPayload(
                            name = query.trim(),
                            grams = weightGrams,
                            sourceKind = "text",
                        ),
                    ),
                ),
            )
        }
    }

    fun enqueueFromTemplate(template: Template, weightGrams: Double?) {
        viewModelScope.launch {
            val now = Clock.System.now()
            val grams = weightGrams ?: template.defaultGrams ?: 100.0
            val ratio = grams / (template.defaultGrams ?: 100.0)
            outboxRepository.enqueue(
                OutboxKind.CreateMeal(
                    payload = MealDraft(
                        id = java.util.UUID.randomUUID().toString(),
                        eatenAt = now,
                        title = template.name,
                        note = null,
                        localPhotoPath = null,
                        totalKcal = (template.defaultKcal ?: 0.0) * ratio,
                        totalCarbsG = (template.defaultCarbsG ?: 0.0) * ratio,
                        totalProteinG = (template.defaultProteinG ?: 0.0) * ratio,
                        totalFatG = (template.defaultFatG ?: 0.0) * ratio,
                        totalFiberG = (template.defaultFiberG ?: 0.0) * ratio,
                    ),
                    eatenAt = now,
                    source = "template",
                    items = listOf(
                        MealItemPayload(
                            name = template.name,
                            grams = grams,
                            sourceKind = "template",
                        ),
                    ),
                ),
            )
        }
    }

    fun acceptDraft(outboxId: String, estimateId: String, eatenAt: Instant, weightOverride: Double?) {
        viewModelScope.launch {
            val sourceItem = outboxRepository.observe().first().firstOrNull { item -> item.id == outboxId }
            val acceptedDraft = sourceItem?.draft?.let { draft ->
                draft.withAcceptedOverrides(eatenAt = eatenAt, weightOverride = weightOverride)
            }
            outboxRepository.enqueue(
                OutboxItem(
                    id = UUID.randomUUID().toString(),
                    kind = OutboxKind.AcceptDraft(
                        estimateId = estimateId,
                        eatenAt = eatenAt,
                        weightOverride = weightOverride,
                        items = acceptedDraft?.items.orEmpty(),
                    ),
                    state = OutboxState.Queued,
                    createdAt = Clock.System.now(),
                    lastAttemptAt = null,
                    attempts = 0,
                    serverIdOnSuccess = null,
                    errorMessage = null,
                    draft = acceptedDraft,
                ),
            )
            outboxRepository.remove(outboxId)
            syncRepository.requestSync()
        }
    }

    fun rejectDraft(outboxId: String) {
        viewModelScope.launch {
            outboxRepository.remove(outboxId)
        }
    }

    fun searchProducts(query: String, callback: (List<Product>) -> Unit) {
        viewModelScope.launch {
            val results = productsRepository.searchLocal(query)
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

private fun MealDraft.withAcceptedOverrides(eatenAt: Instant, weightOverride: Double?): MealDraft {
    val currentWeight = weightGrams ?: items.singleOrNull()?.grams
    val scale = if (weightOverride != null && currentWeight != null && currentWeight > 0.0) {
        weightOverride / currentWeight
    } else {
        null
    }
    return copy(
        eatenAt = eatenAt,
        weightGrams = weightOverride ?: weightGrams,
        totalKcal = totalKcal.scaleBy(scale),
        totalCarbsG = totalCarbsG.scaleBy(scale),
        totalProteinG = totalProteinG.scaleBy(scale),
        totalFatG = totalFatG.scaleBy(scale),
        totalFiberG = totalFiberG.scaleBy(scale),
        items = items.map { item -> item.scaleBy(scale, weightOverride) },
    )
}

private fun MealItemPayload.scaleBy(scale: Double?, weightOverride: Double?): MealItemPayload =
    if (scale == null) {
        this
    } else {
        copy(
            grams = weightOverride ?: grams?.scaleBy(scale),
            kcal = kcal?.scaleBy(scale),
            carbsG = carbsG?.scaleBy(scale),
            proteinG = proteinG?.scaleBy(scale),
            fatG = fatG?.scaleBy(scale),
            fiberG = fiberG?.scaleBy(scale),
        )
    }

private fun Double.scaleBy(scale: Double?): Double =
    if (scale == null) this else kotlin.math.round(this * scale * 10.0) / 10.0

@HiltViewModel
class DraftViewModel @Inject constructor(
    private val outboxRepository: OutboxRepository,
) : ViewModel() {

    private val _draftState = MutableStateFlow<DraftUiState>(DraftUiState.Loading)
    val draftState: StateFlow<DraftUiState> = _draftState

    fun loadDraft(outboxId: String) {
        viewModelScope.launch {
            outboxRepository.observe()
                .map { items -> items.find { it.id == outboxId } }
                .collect { item ->
                    if (item == null) {
                        _draftState.value = DraftUiState.NotFound
                    } else {
                        _draftState.value = DraftUiState.Loaded(
                            outboxItem = item,
                            isEstimateReady = item.state == OutboxState.EstimateReady,
                            draft = item.draft,
                        )
                    }
                }
        }
    }

    fun retryCurrent() {
        val loaded = _draftState.value as? DraftUiState.Loaded ?: return
        viewModelScope.launch {
            outboxRepository.enqueue(
                loaded.outboxItem.copy(
                    state = OutboxState.Queued,
                    errorMessage = null,
                ),
            )
        }
    }
}

sealed interface DraftUiState {
    data object Loading : DraftUiState
    data object NotFound : DraftUiState
    data class Loaded(
        val outboxItem: OutboxItem,
        val isEstimateReady: Boolean,
        val draft: MealDraft?,
    ) : DraftUiState
}
