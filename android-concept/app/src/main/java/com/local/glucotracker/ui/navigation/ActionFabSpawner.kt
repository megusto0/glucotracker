package com.local.glucotracker.ui.navigation

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.LinearOutSlowInEasing
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shadow
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.local.glucotracker.R
import com.local.glucotracker.ui.design.GT

@Composable
fun ActionFabSpawner(
    isOpen: Boolean,
    openAccentColor: Color,
    onDismiss: () -> Unit,
    onPenTap: () -> Unit,
    onCameraTap: () -> Unit,
    onGalleryTap: () -> Unit,
    modifier: Modifier = Modifier,
    extraActionLabel: String? = null,
    onExtraActionTap: (() -> Unit)? = null,
) {
    val scrimAlpha by animateFloatAsState(
        targetValue = if (isOpen) 0.42f else 0f,
        animationSpec = tween(300, easing = LinearOutSlowInEasing),
        label = "fab-spawner-scrim",
    )
    if (scrimAlpha <= 0.01f && !isOpen) return

    Box(modifier = modifier.fillMaxSize()) {
        val hasExtraAction = extraActionLabel != null && onExtraActionTap != null
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(GT.colors.ink.copy(alpha = scrimAlpha))
                .clickable(
                    interactionSource = remember { MutableInteractionSource() },
                    indication = null,
                    onClick = onDismiss,
                ),
        )
        if (hasExtraAction) {
            OptionCircle(
                kind = ActionOptionKind.Number,
                label = extraActionLabel.orEmpty(),
                offsetX = (-96).dp,
                offsetY = (-86).dp,
                isVisible = isOpen,
                openDelayMillis = 30,
                closeDelayMillis = 180,
                onClick = { onExtraActionTap?.invoke() },
            )
        }
        OptionCircle(
            kind = ActionOptionKind.Pen,
            label = stringResource(R.string.fab_option_manual),
            offsetX = if (hasExtraAction) (-34).dp else (-60).dp,
            offsetY = if (hasExtraAction) (-122).dp else (-90).dp,
            isVisible = isOpen,
            openDelayMillis = if (hasExtraAction) 80 else 40,
            closeDelayMillis = if (hasExtraAction) 120 else 160,
            onClick = onPenTap,
        )
        OptionCircle(
            kind = ActionOptionKind.Camera,
            label = stringResource(R.string.fab_option_photo),
            offsetX = if (hasExtraAction) 34.dp else 0.dp,
            offsetY = if (hasExtraAction) (-122).dp else (-120).dp,
            isVisible = isOpen,
            openDelayMillis = if (hasExtraAction) 130 else 100,
            closeDelayMillis = if (hasExtraAction) 70 else 80,
            onClick = onCameraTap,
        )
        OptionCircle(
            kind = ActionOptionKind.Gallery,
            label = stringResource(R.string.fab_option_gallery),
            offsetX = if (hasExtraAction) 96.dp else 60.dp,
            offsetY = if (hasExtraAction) (-86).dp else (-90).dp,
            isVisible = isOpen,
            openDelayMillis = if (hasExtraAction) 180 else 160,
            closeDelayMillis = 0,
            onClick = onGalleryTap,
        )
        BottomNavFab(
            isOptionsOpen = isOpen,
            openAccentColor = openAccentColor,
            onClick = onDismiss,
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .navigationBarsPadding()
                .padding(bottom = 4.dp),
        )
    }
}

@Composable
fun BottomNavFab(
    isOptionsOpen: Boolean,
    openAccentColor: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val captureDescription = stringResource(
        if (isOptionsOpen) {
            R.string.nav_capture_close_content_description
        } else {
            R.string.nav_capture_content_description
        },
    )
    val rotation by animateFloatAsState(
        targetValue = if (isOptionsOpen) 45f else 0f,
        animationSpec = tween(220, easing = LinearOutSlowInEasing),
        label = "fab-rotation",
    )
    val backgroundColor by animateColorAsState(
        targetValue = if (isOptionsOpen) openAccentColor else GT.colors.ink,
        animationSpec = tween(200, easing = LinearOutSlowInEasing),
        label = "fab-color",
    )
    Box(
        modifier = modifier
            .size(56.dp)
            .background(backgroundColor, GT.shapes.fab)
            .clickable(onClick = onClick)
            .semantics { contentDescription = captureDescription },
        contentAlignment = Alignment.Center,
    ) {
        PlusGlyph(modifier = Modifier.graphicsLayer { rotationZ = rotation })
    }
}

@Composable
private fun BoxScope.OptionCircle(
    kind: ActionOptionKind,
    label: String,
    offsetX: Dp,
    offsetY: Dp,
    isVisible: Boolean,
    openDelayMillis: Int,
    closeDelayMillis: Int,
    onClick: () -> Unit,
) {
    val delay = if (isVisible) openDelayMillis else closeDelayMillis
    val scale by animateFloatAsState(
        targetValue = if (isVisible) 1f else 0f,
        animationSpec = tween(
            durationMillis = if (isVisible) 320 else 240,
            delayMillis = delay,
            easing = LinearOutSlowInEasing,
        ),
        label = "option-scale-$kind",
    )
    val alpha by animateFloatAsState(
        targetValue = if (isVisible) 1f else 0f,
        animationSpec = tween(
            durationMillis = if (isVisible) 220 else 140,
            delayMillis = delay,
            easing = LinearOutSlowInEasing,
        ),
        label = "option-alpha-$kind",
    )
    val labelAlpha by animateFloatAsState(
        targetValue = if (isVisible) 0.95f else 0f,
        animationSpec = tween(
            durationMillis = if (isVisible) 150 else 90,
            delayMillis = if (isVisible) openDelayMillis + 320 else 0,
            easing = LinearOutSlowInEasing,
        ),
        label = "option-label-$kind",
    )

    Box(
        modifier = Modifier
            .align(Alignment.BottomCenter)
            .navigationBarsPadding()
            .offset(x = offsetX, y = offsetY)
            .graphicsLayer {
                scaleX = scale
                scaleY = scale
                this.alpha = alpha
            }
            .shadow(2.dp, CircleShape, clip = false)
            .size(64.dp)
            .background(GT.colors.surface2, CircleShape)
            .border(GT.space.hairline, GT.colors.hairline2, CircleShape)
            .clickable(enabled = isVisible, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        OptionGlyph(kind = kind)
    }
    Text(
        text = label,
        modifier = Modifier
            .align(Alignment.BottomCenter)
            .navigationBarsPadding()
            .offset(x = offsetX, y = offsetY + 24.dp)
            .width(128.dp)
            .graphicsLayer { this.alpha = labelAlpha },
        color = GT.colors.surface2,
        style = GT.type.kicker.copy(
            shadow = Shadow(
                color = GT.colors.ink.copy(alpha = 0.3f),
                offset = Offset(0f, 1f),
                blurRadius = 2f,
            ),
        ),
        textAlign = TextAlign.Center,
        maxLines = 1,
    )
}

private enum class ActionOptionKind {
    Number,
    Pen,
    Camera,
    Gallery,
}

@Composable
private fun OptionGlyph(kind: ActionOptionKind) {
    val color = GT.colors.ink
    Canvas(modifier = Modifier.size(24.dp)) {
        val stroke = Stroke(width = 1.8.dp.toPx(), cap = StrokeCap.Round)
        when (kind) {
            ActionOptionKind.Number -> Unit
            ActionOptionKind.Pen -> {
                drawLine(color, Offset(6.dp.toPx(), 18.dp.toPx()), Offset(17.dp.toPx(), 7.dp.toPx()), stroke.width, StrokeCap.Round)
                drawLine(color, Offset(15.dp.toPx(), 5.dp.toPx()), Offset(19.dp.toPx(), 9.dp.toPx()), stroke.width, StrokeCap.Round)
                drawLine(color, Offset(5.dp.toPx(), 19.dp.toPx()), Offset(10.dp.toPx(), 18.dp.toPx()), stroke.width, StrokeCap.Round)
            }
            ActionOptionKind.Camera -> {
                drawRoundRect(
                    color = color,
                    topLeft = Offset(3.dp.toPx(), 7.dp.toPx()),
                    size = androidx.compose.ui.geometry.Size(18.dp.toPx(), 12.dp.toPx()),
                    cornerRadius = androidx.compose.ui.geometry.CornerRadius(2.dp.toPx(), 2.dp.toPx()),
                    style = stroke,
                )
                drawCircle(color, 3.4.dp.toPx(), Offset(12.dp.toPx(), 13.dp.toPx()), style = stroke)
                drawLine(color, Offset(8.dp.toPx(), 7.dp.toPx()), Offset(9.dp.toPx(), 5.dp.toPx()), stroke.width, StrokeCap.Round)
                drawLine(color, Offset(9.dp.toPx(), 5.dp.toPx()), Offset(15.dp.toPx(), 5.dp.toPx()), stroke.width, StrokeCap.Round)
            }
            ActionOptionKind.Gallery -> {
                drawRoundRect(
                    color = color,
                    topLeft = Offset(4.dp.toPx(), 4.dp.toPx()),
                    size = androidx.compose.ui.geometry.Size(16.dp.toPx(), 16.dp.toPx()),
                    cornerRadius = androidx.compose.ui.geometry.CornerRadius(2.dp.toPx(), 2.dp.toPx()),
                    style = stroke,
                )
                drawLine(color, Offset(6.dp.toPx(), 17.dp.toPx()), Offset(10.dp.toPx(), 13.dp.toPx()), stroke.width, StrokeCap.Round)
                drawLine(color, Offset(10.dp.toPx(), 13.dp.toPx()), Offset(14.dp.toPx(), 16.dp.toPx()), stroke.width, StrokeCap.Round)
                drawCircle(color, 1.4.dp.toPx(), Offset(9.dp.toPx(), 9.dp.toPx()))
            }
        }
    }
    if (kind == ActionOptionKind.Number) {
        Text(
            text = "1.0",
            color = color,
            style = GT.type.monoLabel,
            maxLines = 1,
        )
    }
}

@Composable
private fun PlusGlyph(modifier: Modifier = Modifier) {
    val color = GT.colors.surface2
    Canvas(modifier = modifier.size(22.dp)) {
        val middle = size.width / 2f
        drawLine(
            color = color,
            start = Offset(middle, 4.dp.toPx()),
            end = Offset(middle, size.height - 4.dp.toPx()),
            strokeWidth = 2.dp.toPx(),
            cap = StrokeCap.Round,
        )
        drawLine(
            color = color,
            start = Offset(4.dp.toPx(), middle),
            end = Offset(size.width - 4.dp.toPx(), middle),
            strokeWidth = 2.dp.toPx(),
            cap = StrokeCap.Round,
        )
    }
}
