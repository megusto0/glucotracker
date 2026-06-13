package com.local.glucotracker.ui.feature.capture

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.LocalLifecycleOwner
import coil3.compose.AsyncImage
import com.local.glucotracker.R
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import java.io.File
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant

@Composable
fun PhotoCaptureScreen(
    onPhotoQueued: (outboxId: String) -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: CaptureViewModel = hiltViewModel(),
) {
    val context = LocalContext.current
    var hasCameraPermission by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
                PackageManager.PERMISSION_GRANTED,
        )
    }
    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission(),
    ) { granted ->
        hasCameraPermission = granted
    }

    LaunchedEffect(Unit) {
        if (!hasCameraPermission) {
            permissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    if (hasCameraPermission) {
        CameraPreviewScreen(
            onPhotoQueued = onPhotoQueued,
            onClose = onClose,
            viewModel = viewModel,
            modifier = modifier,
        )
    } else {
        CameraPermissionScreen(
            onRequestPermission = { permissionLauncher.launch(Manifest.permission.CAMERA) },
            onClose = onClose,
            modifier = modifier,
        )
    }
}

@Composable
private fun CameraPreviewScreen(
    onPhotoQueued: (outboxId: String) -> Unit,
    onClose: () -> Unit,
    viewModel: CaptureViewModel,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val mainExecutor = remember(context) { ContextCompat.getMainExecutor(context) }
    val cameraProviderFuture = remember(context) { ProcessCameraProvider.getInstance(context) }
    val previewView = remember(context) {
        PreviewView(context).apply {
            scaleType = PreviewView.ScaleType.FILL_CENTER
        }
    }
    val imageCapture = remember {
        ImageCapture.Builder()
            .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
            .build()
    }
    var camera by remember { mutableStateOf<androidx.camera.core.Camera?>(null) }
    var torchOn by remember { mutableStateOf(false) }
    var captureError by remember { mutableStateOf(false) }
    var captureState by remember { mutableStateOf(CameraCaptureState.Idle) }
    // A captured-but-not-yet-sent photo awaiting the user's Send/Retake/Close.
    var capturedPhoto by remember { mutableStateOf<CapturedPhoto?>(null) }
    val captureOverlayAlpha by animateFloatAsState(
        targetValue = if (captureState == CameraCaptureState.Idle) 0f else 1f,
        animationSpec = tween(durationMillis = 120),
        label = "cameraCaptureOverlay",
    )
    val captureFlashAlpha by animateFloatAsState(
        targetValue = if (captureState == CameraCaptureState.Saving) 0.18f else 0f,
        animationSpec = tween(durationMillis = 110),
        label = "cameraCaptureFlash",
    )

    DisposableEffect(lifecycleOwner, cameraProviderFuture, previewView, imageCapture) {
        val listener = Runnable {
            val cameraProvider = cameraProviderFuture.get()
            val preview = Preview.Builder().build().also {
                it.surfaceProvider = previewView.surfaceProvider
            }
            cameraProvider.unbindAll()
            camera = cameraProvider.bindToLifecycle(
                lifecycleOwner,
                CameraSelector.DEFAULT_BACK_CAMERA,
                preview,
                imageCapture,
            )
        }
        cameraProviderFuture.addListener(listener, mainExecutor)

        onDispose {
            try {
                cameraProviderFuture.get().unbindAll()
            } catch (_: Exception) {
            }
        }
    }

    val shutterDesc = stringResource(R.string.camera_shutter_content_description)
    val torchDesc = stringResource(R.string.camera_torch_content_description)
    val closeDesc = stringResource(R.string.camera_close_content_description)

    Box(modifier = modifier.fillMaxSize().background(Color.Black)) {
        AndroidView(
            factory = { previewView },
            modifier = Modifier.fillMaxSize(),
        )

        if (captureError) {
            Text(
                text = stringResource(R.string.camera_capture_error),
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .padding(top = 24.dp)
                    .background(Color.Black.copy(alpha = 0.46f), GT.shapes.tag)
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                color = GT.colors.surface2,
                style = GT.type.sansLabel,
            )
        }

        if (capturedPhoto == null) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .align(Alignment.BottomCenter)
                    .background(Color.Black.copy(alpha = 0.52f))
                    .padding(vertical = GT.space.lg),
                contentAlignment = Alignment.Center,
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = GT.space.lg),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    TorchButton(
                        enabled = torchOn,
                        onClick = {
                            torchOn = !torchOn
                            camera?.cameraControl?.enableTorch(torchOn)
                        },
                        contentDescription = torchDesc,
                    )

                    ShutterButton(
                        enabled = captureState == CameraCaptureState.Idle,
                        onClick = {
                            captureError = false
                            captureState = CameraCaptureState.Saving
                            // Shutter moment is the meal time (eaten_at); it is
                            // preserved through Send, never overwritten later.
                            val capturedAt = Clock.System.now()
                            val outputFile = File.createTempFile("capture_", ".jpg", context.cacheDir)
                            val outputOptions = ImageCapture.OutputFileOptions.Builder(outputFile).build()
                            imageCapture.takePicture(
                                outputOptions,
                                mainExecutor,
                                object : ImageCapture.OnImageSavedCallback {
                                    override fun onImageSaved(outputFileResults: ImageCapture.OutputFileResults) {
                                        captureState = CameraCaptureState.Idle
                                        capturedPhoto = CapturedPhoto(outputFile, capturedAt)
                                    }

                                    override fun onError(exception: ImageCaptureException) {
                                        outputFile.delete()
                                        captureState = CameraCaptureState.Idle
                                        captureError = true
                                    }
                                },
                            )
                        },
                        contentDescription = shutterDesc,
                    )

                    CloseButton(
                        onClick = onClose,
                        contentDescription = closeDesc,
                    )
                }
            }
        }

        capturedPhoto?.let { photo ->
            PhotoReviewOverlay(
                file = photo.file,
                sending = captureState == CameraCaptureState.Saving ||
                    captureState == CameraCaptureState.Queued,
                onClose = {
                    photo.file.delete()
                    capturedPhoto = null
                    onClose()
                },
                onRetake = {
                    photo.file.delete()
                    capturedPhoto = null
                    captureError = false
                },
                onSend = {
                    captureState = CameraCaptureState.Saving
                    // enqueueCameraPhoto copies into storage and deletes the
                    // temp file itself, so we don't delete it here.
                    viewModel.enqueueCameraPhoto(photo.file, photo.capturedAt) { outboxId ->
                        captureState = CameraCaptureState.Queued
                        capturedPhoto = null
                        onPhotoQueued(outboxId)
                    }
                },
                modifier = Modifier.fillMaxSize(),
            )
        }

        if (captureFlashAlpha > 0f) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Color.White.copy(alpha = captureFlashAlpha)),
            )
        }

        if (captureOverlayAlpha > 0f) {
            CaptureProgressOverlay(
                state = captureState,
                modifier = Modifier
                    .fillMaxSize()
                    .alpha(captureOverlayAlpha),
            )
        }
    }
}

private enum class CameraCaptureState {
    Idle,
    Saving,
    Queued,
}

private data class CapturedPhoto(
    val file: File,
    val capturedAt: Instant,
)

@Composable
private fun PhotoReviewOverlay(
    file: File,
    sending: Boolean,
    onClose: () -> Unit,
    onRetake: () -> Unit,
    onSend: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val reviewDesc = stringResource(R.string.camera_review_content_description)
    Box(modifier = modifier.background(Color.Black)) {
        AsyncImage(
            model = file,
            contentDescription = reviewDesc,
            modifier = Modifier.fillMaxSize(),
        )

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .align(Alignment.BottomCenter)
                .background(Color.Black.copy(alpha = 0.52f))
                .navigationBarsPadding()
                .padding(horizontal = GT.space.lg, vertical = GT.space.lg),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            ReviewActionButton(
                text = stringResource(R.string.camera_review_close),
                onClick = onClose,
                enabled = !sending,
                modifier = Modifier.weight(1f),
            )
            ReviewActionButton(
                text = stringResource(R.string.camera_review_retake),
                onClick = onRetake,
                enabled = !sending,
                modifier = Modifier.weight(1f),
            )
            ReviewActionButton(
                text = stringResource(R.string.camera_review_send),
                onClick = onSend,
                enabled = !sending,
                primary = true,
                modifier = Modifier.weight(1f),
            )
        }
    }
}

@Composable
private fun ReviewActionButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    primary: Boolean = false,
) {
    val shape = RoundedCornerShape(10.dp)
    val container = if (primary) GT.colors.surface2 else Color.Transparent
    val label = if (primary) GT.colors.ink else GT.colors.surface2
    val alpha = if (enabled) 1f else 0.5f
    Box(
        modifier = modifier
            .heightIn(min = GT.space.touch)
            .clip(shape)
            .background(container.copy(alpha = if (primary) alpha else 0f))
            .then(
                if (primary) {
                    Modifier
                } else {
                    Modifier.border(1.dp, GT.colors.surface2.copy(alpha = alpha), shape)
                },
            )
            .clickable(enabled = enabled, onClick = onClick)
            .padding(vertical = 12.dp, horizontal = 8.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = text,
            color = label.copy(alpha = alpha),
            style = GT.type.sansLabel,
            maxLines = 1,
        )
    }
}

@Composable
private fun CaptureProgressOverlay(
    state: CameraCaptureState,
    modifier: Modifier = Modifier,
) {
    if (state == CameraCaptureState.Idle) return

    val text = when (state) {
        CameraCaptureState.Idle -> ""
        CameraCaptureState.Saving -> stringResource(R.string.camera_capture_saving)
        CameraCaptureState.Queued -> stringResource(R.string.camera_capture_queued)
    }

    Box(
        modifier = modifier.background(Color.Black.copy(alpha = 0.22f)),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = text,
            modifier = Modifier
                .background(Color.Black.copy(alpha = 0.68f), GT.shapes.tag)
                .padding(horizontal = 14.dp, vertical = 9.dp),
            color = GT.colors.surface2,
            style = GT.type.sansLabel,
            maxLines = 1,
        )
    }
}

@Composable
private fun CameraPermissionScreen(
    onRequestPermission: () -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg)
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            text = stringResource(R.string.camera_permission_title),
            color = GT.colors.ink,
            style = GT.type.serifSection,
        )
        Text(
            text = stringResource(R.string.camera_permission_body),
            modifier = Modifier.padding(top = 8.dp),
            color = GT.colors.ink2,
            style = GT.type.sansBody,
        )
        Row(
            modifier = Modifier.padding(top = 18.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            GTOutlineButton(
                text = stringResource(R.string.camera_permission_request),
                onClick = onRequestPermission,
            )
            GTOutlineButton(
                text = stringResource(R.string.camera_permission_close),
                onClick = onClose,
            )
        }
    }
}

@Composable
private fun ShutterButton(
    enabled: Boolean,
    onClick: () -> Unit,
    contentDescription: String,
) {
    val ink = GT.colors.ink
    val surface2 = GT.colors.surface2
    Box(
        modifier = Modifier
            .size(70.dp)
            .clip(CircleShape)
            .background(ink.copy(alpha = if (enabled) 1f else 0.55f))
            .clickable(enabled = enabled, onClick = onClick)
            .semantics { this.contentDescription = contentDescription },
        contentAlignment = Alignment.Center,
    ) {
        Canvas(modifier = Modifier.size(58.dp)) {
            drawCircle(
                color = surface2,
                radius = size.minDimension / 2f,
                style = Stroke(width = 4.dp.toPx()),
            )
        }
    }
}

@Composable
private fun TorchButton(
    enabled: Boolean,
    onClick: () -> Unit,
    contentDescription: String,
) {
    val color = if (enabled) GT.colors.surface2 else GT.colors.surface2.copy(alpha = 0.6f)
    Box(
        modifier = Modifier
            .size(GT.space.touch)
            .semantics { this.contentDescription = contentDescription }
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Canvas(modifier = Modifier.size(24.dp)) {
            val stroke = Stroke(width = 2.dp.toPx(), cap = StrokeCap.Round)
            val cx = size.width / 2f
            val cy = size.height / 2f
            drawCircle(
                color = color,
                radius = size.minDimension / 4f,
                style = stroke,
            )
            drawLine(
                color = color,
                start = Offset(cx, cy - size.minDimension / 2f),
                end = Offset(cx, cy - size.minDimension / 4f),
                strokeWidth = 2.dp.toPx(),
                cap = StrokeCap.Round,
            )
            drawLine(
                color = color,
                start = Offset(cx - size.minDimension / 6f, cy - size.minDimension / 4f + 2.dp.toPx()),
                end = Offset(cx + size.minDimension / 6f, cy - size.minDimension / 4f + 2.dp.toPx()),
                strokeWidth = 2.dp.toPx(),
                cap = StrokeCap.Round,
            )
        }
    }
}

@Composable
private fun CloseButton(
    onClick: () -> Unit,
    contentDescription: String,
) {
    val color = GT.colors.surface2
    Box(
        modifier = Modifier
            .size(GT.space.touch)
            .semantics { this.contentDescription = contentDescription }
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Canvas(modifier = Modifier.size(24.dp)) {
            val stroke = 2.dp.toPx()
            val cap = StrokeCap.Round
            val inset = size.minDimension / 4f
            drawLine(
                color = color,
                start = Offset(inset, inset),
                end = Offset(size.width - inset, size.height - inset),
                strokeWidth = stroke,
                cap = cap,
            )
            drawLine(
                color = color,
                start = Offset(size.width - inset, inset),
                end = Offset(inset, size.height - inset),
                strokeWidth = stroke,
                cap = cap,
            )
        }
    }
}
