package com.local.glucotracker.ui.stock

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import com.local.glucotracker.ui.design.GT
import java.io.File
import androidx.compose.ui.res.stringResource
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.Product
import com.local.glucotracker.ui.design.primitives.GTTag

/**
 * Where a row came from, when it came from stock rather than the catalogue.
 *
 * Shared by База and the search sheet because the two lists show the same
 * entries and a mark that appears on one of them is worse than no mark: it
 * reads as a property of the screen instead of a property of the food.
 */
@Composable
fun stockLabel(product: Product): String? = when (product.sourceKind) {
    "fridge" -> stringResource(R.string.base_stock_fridge)
    "meal_prep" -> stringResource(R.string.base_stock_mealprep)
    else -> null
}

@Composable
fun StockTag(product: Product) {
    stockLabel(product)?.let { label -> GTTag(text = label) }
}

/**
 * Take a picture of a cooked batch.
 *
 * Straight to a cache file through a FileProvider rather than through the meal
 * capture screen: that screen exists to create a meal, and this photograph
 * creates nothing — it names a dish that already exists.
 */
@Composable
fun MealPrepPhotoButton(
    hasPhoto: Boolean,
    onCaptured: (path: String, onResult: (String?) -> Unit) -> Unit,
) {
    val context = LocalContext.current
    var pendingPath by remember { mutableStateOf<String?>(null) }
    // The upload used to fail into a log line. From the counter that looks
    // exactly like nothing happening, which is what it looked like.
    var status by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val cameraLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.TakePicture(),
    ) { saved ->
        val path = pendingPath
        pendingPath = null
        if (saved && path != null) {
            busy = true
            status = null
            onCaptured(path) { error ->
                busy = false
                status = error ?: "Фото сохранено"
            }
        }
    }
    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (!granted) pendingPath = null
    }

    Column(modifier = Modifier.fillMaxWidth()) {
    Text(
        text = when {
            busy -> "Отправляем…"
            hasPhoto -> "Переснять блюдо"
            else -> "Сфотографировать блюдо"
        },
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = 44.dp)
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.card)
            .clickable {
                if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) !=
                    PackageManager.PERMISSION_GRANTED
                ) {
                    permissionLauncher.launch(Manifest.permission.CAMERA)
                    return@clickable
                }
                val dir = File(context.cacheDir, "camera").apply { mkdirs() }
                val target = File(dir, "mealprep_${System.currentTimeMillis()}.jpg")
                pendingPath = target.absolutePath
                cameraLauncher.launch(
                    FileProvider.getUriForFile(
                        context,
                        "${context.packageName}.fileprovider",
                        target,
                    ),
                )
            }
            .padding(horizontal = 14.dp, vertical = 12.dp),
        color = GT.colors.ink,
        style = GT.type.sansLabel,
    )
    status?.let { text ->
        Text(
            text = text,
            modifier = Modifier.padding(top = 6.dp),
            color = if (text == "Фото сохранено") GT.colors.muted else GT.colors.warn,
            style = GT.type.kicker,
        )
    }
    }
}
