package com.local.glucotracker.ui.feature.sensor

import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.platform.LocalContext
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning

@Composable
internal fun rememberSensorCodeScanner(
    onDecoded: (String) -> Unit,
    onFailure: () -> Unit,
): () -> Unit {
    val context = LocalContext.current
    val currentDecoded = rememberUpdatedState(onDecoded)
    val currentFailure = rememberUpdatedState(onFailure)
    val scanner = remember(context) {
        val options = GmsBarcodeScannerOptions.Builder()
            .setBarcodeFormats(Barcode.FORMAT_DATA_MATRIX)
            .build()
        GmsBarcodeScanning.getClient(context, options)
    }
    return remember(scanner) {
        {
            scanner.startScan()
                .addOnSuccessListener { barcode ->
                    barcode.rawValue
                        ?.takeIf { it.isNotBlank() }
                        ?.let(currentDecoded.value)
                        ?: currentFailure.value()
                }
                .addOnFailureListener { currentFailure.value() }
        }
    }
}
