package com.local.glucotracker.ui.design.primitives

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil3.compose.AsyncImage
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.image.rememberApiImageModel

@Composable
fun GTHairlineDivider(modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(GT.space.hairline)
            .background(GT.colors.hairline),
    )
}

@Composable
fun GTSectionLabel(
    text: String,
    modifier: Modifier = Modifier,
) {
    Text(
        text = text.uppercase(),
        modifier = modifier,
        color = GT.colors.muted,
        style = GT.type.kicker,
        maxLines = 1,
        overflow = TextOverflow.Ellipsis,
    )
}

@Composable
fun GTKicker(
    text: String,
    modifier: Modifier = Modifier,
) {
    GTSectionLabel(text = text, modifier = modifier)
}

@Composable
fun GTBrandLockup(
    name: String,
    mark: @Composable () -> Unit,
    modifier: Modifier = Modifier,
    rightSlot: @Composable RowScope.() -> Unit = {},
) {
    Column(modifier = modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(24.dp)
                .padding(horizontal = 18.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                modifier = Modifier.size(16.dp),
                contentAlignment = Alignment.Center,
            ) {
                mark()
            }
            Spacer(Modifier.width(8.dp))
            Text(
                text = name,
                color = GT.colors.ink,
                style = GT.type.serifSection.copy(fontSize = 13.sp),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Spacer(Modifier.weight(1f))
            rightSlot()
        }
        GTHairlineDivider()
    }
}

@Composable
fun GTKpiCard(
    label: String,
    value: String,
    sub: String,
    progress: Float,
    modifier: Modifier = Modifier,
    progressColor: Color = GT.colors.accent.copy(alpha = 0.65f),
    extra: String? = null,
) {
    Column(
        modifier = modifier
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .padding(horizontal = 12.dp, vertical = 10.dp),
    ) {
        GTSectionLabel(text = label)
        Row(
            modifier = Modifier.padding(top = 4.dp),
            verticalAlignment = Alignment.Bottom,
        ) {
            Text(
                text = value,
                color = GT.colors.ink,
                style = GT.type.monoNumber,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        GTProgressLine(
            progress = progress,
            color = progressColor,
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 8.dp),
        )
        Text(
            text = sub,
            modifier = Modifier.padding(top = 6.dp),
            color = GT.colors.muted,
            style = GT.type.monoLabel,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        if (extra != null) {
            Text(
                text = extra,
                modifier = Modifier.padding(top = 2.dp),
                color = GT.colors.muted,
                style = GT.type.monoLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
fun GTKcalRing(
    value: String,
    goalText: String,
    progress: Float?,
    ringColor: Color,
    remainingValue: String,
    remainingLabel: String,
    observation: String?,
    contentDescription: String,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .semantics { this.contentDescription = contentDescription },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier.size(110.dp),
            contentAlignment = Alignment.Center,
        ) {
            val trackColor = GT.colors.hairline
            Canvas(modifier = Modifier.size(110.dp)) {
                val stroke = 9.dp.toPx()
                val inset = stroke / 2f
                val arcSize = Size(size.width - stroke, size.height - stroke)
                drawArc(
                    color = trackColor,
                    startAngle = -90f,
                    sweepAngle = 360f,
                    useCenter = false,
                    topLeft = Offset(inset, inset),
                    size = arcSize,
                    style = Stroke(width = stroke, cap = StrokeCap.Round),
                )
                val safeProgress = progress?.coerceIn(0f, 1f) ?: 0f
                if (safeProgress > 0f) {
                    drawArc(
                        color = ringColor,
                        startAngle = -90f,
                        sweepAngle = 360f * safeProgress,
                        useCenter = false,
                        topLeft = Offset(inset, inset),
                        size = arcSize,
                        style = Stroke(width = stroke, cap = StrokeCap.Round),
                    )
                }
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    text = value,
                    color = GT.colors.ink,
                    style = GT.type.monoNumber,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = goalText,
                    color = GT.colors.muted,
                    style = GT.type.sansLabel.copy(fontSize = 10.sp),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        Column(
            modifier = Modifier
                .weight(1f)
                .padding(start = 16.dp),
        ) {
            Text(
                text = remainingValue,
                color = GT.colors.ink,
                style = GT.type.monoNumber.copy(fontSize = 18.sp),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                text = remainingLabel,
                modifier = Modifier.padding(top = 2.dp),
                color = GT.colors.muted,
                style = GT.type.sansLabel.copy(fontSize = 11.sp),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (observation != null) {
                Text(
                    text = observation,
                    modifier = Modifier.padding(top = 8.dp),
                    color = GT.colors.ink2,
                    style = GT.type.sansBody.copy(fontSize = 12.5.sp),
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
fun GTMacroBar(
    label: String,
    value: String,
    percentOfDay: Float?,
    color: Color,
    contentDescription: String,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .semantics { this.contentDescription = contentDescription },
    ) {
        Row(verticalAlignment = Alignment.Bottom) {
            GTKicker(text = label)
            Spacer(Modifier.weight(1f))
            Text(
                text = value,
                color = GT.colors.ink,
                style = GT.type.monoLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 6.dp)
                .height(4.dp)
                .background(GT.colors.hairline),
        ) {
            val safePercent = percentOfDay?.coerceIn(0f, 1f) ?: 0f
            if (safePercent > 0f) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth(safePercent)
                        .height(4.dp)
                        .background(color),
                )
            }
        }
    }
}

@Composable
fun GTTag(
    text: String,
    active: Boolean = false,
    modifier: Modifier = Modifier,
) {
    val bg = if (active) GT.colors.ink else GT.colors.surface
    val fg = if (active) GT.colors.surface2 else GT.colors.ink2
    val borderColor = if (active) GT.colors.ink else GT.colors.hairline2

    Box(
        modifier = modifier
            .height(22.dp)
            .background(bg, GT.shapes.tag)
            .border(GT.space.hairline, borderColor, GT.shapes.tag)
            .padding(horizontal = 9.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = text,
            color = fg,
            style = GT.type.sansLabel,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
fun GTOutlineButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    GTButtonFrame(
        text = text,
        onClick = onClick,
        modifier = modifier,
        enabled = enabled,
        fill = GT.colors.surface,
        contentColor = GT.colors.ink2,
        borderColor = GT.colors.hairline2,
    )
}

@Composable
fun GTPrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    GTButtonFrame(
        text = text,
        onClick = onClick,
        modifier = modifier,
        enabled = enabled,
        fill = GT.colors.ink,
        contentColor = GT.colors.surface2,
        borderColor = GT.colors.ink,
    )
}

@Composable
fun GTIconButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    content: @Composable () -> Unit,
) {
    Box(
        modifier = modifier
            .size(GT.space.touch)
            .clickable(enabled = enabled, role = Role.Button, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .size(28.dp)
                .background(GT.colors.surface, GT.shapes.iconButton)
                .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.iconButton),
            contentAlignment = Alignment.Center,
        ) {
            content()
        }
    }
}

@Composable
fun GTSegmented(
    options: List<String>,
    selected: String,
    onSelect: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .padding(3.dp),
        horizontalArrangement = Arrangement.spacedBy(3.dp),
    ) {
        options.forEach { option ->
            val active = option == selected
            val bg = if (active) GT.colors.ink else GT.colors.surface
            val fg = if (active) GT.colors.surface2 else GT.colors.muted
            Box(
                modifier = Modifier
                    .weight(1f)
                    .heightIn(min = GT.space.touch)
                    .clickable(role = Role.Tab, onClick = { onSelect(option) }),
                contentAlignment = Alignment.Center,
            ) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(28.dp)
                        .background(bg, GT.shapes.tag)
                        .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.tag),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = option,
                        color = fg,
                        style = GT.type.sansLabel,
                        maxLines = 1,
                    )
                }
            }
        }
    }
}

enum class GTPhotoPlaceholderTone {
    Surface,
    Background,
    Muted,
}

@Composable
fun GTPhotoSlot(
    model: Any?,
    modifier: Modifier = Modifier,
    placeholderTone: GTPhotoPlaceholderTone = GTPhotoPlaceholderTone.Background,
) {
    val imageModel = rememberApiImageModel(model)
    val placeholderColor = when (placeholderTone) {
        GTPhotoPlaceholderTone.Surface -> GT.colors.surface
        GTPhotoPlaceholderTone.Background -> GT.colors.bg
        GTPhotoPlaceholderTone.Muted -> GT.colors.hairline
    }
    Box(
        modifier = modifier
            .size(32.dp)
            .clip(GT.shapes.iconButton)
            .background(placeholderColor)
            .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.iconButton),
        contentAlignment = Alignment.Center,
    ) {
        if (imageModel == null) {
            GTPhotoGlyph()
        } else {
            AsyncImage(
                model = imageModel,
                contentDescription = null,
                modifier = Modifier.matchParentSize(),
                contentScale = ContentScale.Crop,
            )
        }
    }
}

enum class GTStatusTone {
    Muted,
    Info,
    Good,
    Warn,
}

data class GTMealRowStatus(
    val icon: String,
    val text: String,
    val tone: GTStatusTone,
)

@Composable
fun GTMealRow(
    time: String,
    photo: Any?,
    name: String,
    meta: String,
    primaryRight: String,
    secondaryRight: String,
    status: GTMealRowStatus?,
    modifier: Modifier = Modifier,
    muted: Boolean = false,
    primaryRightColor: Color? = null,
) {
    val primaryTextColor = if (muted) GT.colors.muted else GT.colors.ink
    val secondaryTextColor = if (muted) GT.colors.muted else GT.colors.ink2
    Row(
        modifier = modifier
            .fillMaxWidth()
            .heightIn(min = 56.dp)
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Text(
            text = time,
            modifier = Modifier.width(36.dp),
            color = secondaryTextColor,
            style = GT.type.monoLabel,
            maxLines = 1,
        )
        GTPhotoSlot(model = photo, modifier = Modifier.size(32.dp))
        Column(
            modifier = Modifier
                .weight(1f)
                .padding(start = 10.dp, end = 10.dp),
        ) {
            Text(
                text = name,
                color = primaryTextColor,
                style = GT.type.sansLabel,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Row(
                modifier = Modifier.padding(top = 3.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (status != null) {
                    GTStatusPill(status)
                    Spacer(Modifier.width(6.dp))
                }
                Text(
                    text = meta,
                    color = GT.colors.muted,
                    style = GT.type.monoLabel,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(
                text = primaryRight,
                color = primaryRightColor ?: primaryTextColor,
                style = GT.type.monoLabel,
                maxLines = 1,
            )
            Text(
                text = secondaryRight,
                modifier = Modifier.padding(top = 1.dp),
                color = primaryTextColor,
                style = GT.type.monoLabel,
                maxLines = 1,
            )
        }
    }
}

data class GTBottomBarItem(
    val id: String,
    val label: String,
    val selected: Boolean = false,
    val icon: @Composable () -> Unit,
)

@Composable
fun GTBottomBar(
    items: List<GTBottomBarItem>,
    onClick: (String) -> Unit,
    modifier: Modifier = Modifier,
    centerSlot: (@Composable () -> Unit)? = null,
    activeIndicatorColor: Color = GT.colors.ink,
    activeIndicatorUnderIcon: Boolean = false,
) {
    val hairlineColor = GT.colors.hairline
    val hairlineWidth = GT.space.hairline
    if (centerSlot == null) {
        Row(
            modifier = modifier
                .fillMaxWidth()
                .height(64.dp)
                .background(GT.colors.surface)
                .drawBehind {
                    drawLine(
                        color = hairlineColor,
                        start = Offset.Zero,
                        end = Offset(size.width, 0f),
                        strokeWidth = hairlineWidth.toPx(),
                    )
                }
                .padding(horizontal = 6.dp),
            verticalAlignment = Alignment.Top,
        ) {
            items.forEach { item ->
                GTBottomBarButton(
                    item = item,
                    onClick = onClick,
                    modifier = Modifier.weight(1f),
                    activeIndicatorColor = activeIndicatorColor,
                    activeIndicatorUnderIcon = activeIndicatorUnderIcon,
                )
            }
        }
        return
    }

    val splitIndex = items.size / 2
    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(64.dp)
            .background(GT.colors.surface)
            .drawBehind {
                drawLine(
                    color = hairlineColor,
                    start = Offset.Zero,
                    end = Offset(size.width, 0f),
                    strokeWidth = hairlineWidth.toPx(),
                )
            }
            .padding(horizontal = 6.dp),
    ) {
        Row(
            modifier = Modifier.matchParentSize(),
            verticalAlignment = Alignment.Top,
        ) {
            Row(
                modifier = Modifier.weight(1f),
                verticalAlignment = Alignment.Top,
            ) {
                items.take(splitIndex).forEach { item ->
                    GTBottomBarButton(
                        item = item,
                        onClick = onClick,
                        modifier = Modifier.weight(1f),
                        activeIndicatorColor = activeIndicatorColor,
                        activeIndicatorUnderIcon = activeIndicatorUnderIcon,
                    )
                }
            }
            Spacer(Modifier.width(72.dp))
            Row(
                modifier = Modifier.weight(1f),
                verticalAlignment = Alignment.Top,
            ) {
                items.drop(splitIndex).forEach { item ->
                    GTBottomBarButton(
                        item = item,
                        onClick = onClick,
                        modifier = Modifier.weight(1f),
                        activeIndicatorColor = activeIndicatorColor,
                        activeIndicatorUnderIcon = activeIndicatorUnderIcon,
                    )
                }
            }
        }
        Box(
            modifier = Modifier.align(Alignment.TopCenter),
            contentAlignment = Alignment.TopCenter,
        ) {
            centerSlot()
        }
    }
}

@Composable
fun GTFab(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit = { GTPlusGlyph() },
) {
    Box(
        modifier = modifier
            .size(56.dp)
            .background(GT.colors.ink, GT.shapes.fab)
            .clickable(role = Role.Button, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        content()
    }
}

@Composable
fun GTHintBox(
    text: String,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .fillMaxWidth()
            .dottedBorder(
                color = GT.colors.hairline2,
                strokeWidth = GT.space.hairline,
                radius = 10.dp,
            )
            .background(GT.colors.surface, GT.shapes.card)
            .padding(horizontal = 14.dp, vertical = 12.dp),
    ) {
        Text(
            text = text,
            color = GT.colors.muted,
            style = GT.type.sansBody,
        )
    }
}

@Composable
private fun GTButtonFrame(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier,
    enabled: Boolean,
    fill: Color,
    contentColor: Color,
    borderColor: Color,
) {
    Box(
        modifier = modifier
            .heightIn(min = GT.space.touch)
            .clickable(enabled = enabled, role = Role.Button, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .height(30.dp)
                .widthIn(min = 76.dp)
                .background(fill, GT.shapes.tag)
                .border(GT.space.hairline, borderColor, GT.shapes.tag)
                .padding(horizontal = 14.dp),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = text,
                color = contentColor,
                style = GT.type.sansLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun GTProgressLine(
    progress: Float,
    color: Color,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .height(2.dp)
            .background(GT.colors.hairline),
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth(progress.coerceIn(0f, 1f))
                .height(2.dp)
                .background(color),
        )
    }
}

@Composable
private fun GTStatusPill(status: GTMealRowStatus) {
    val color = status.tone.color()
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier
                .size(14.dp)
                .border(GT.space.hairline, color, CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = status.icon,
                color = color,
                style = GT.type.monoLabel,
                maxLines = 1,
            )
        }
        Spacer(Modifier.width(4.dp))
        Text(
            text = status.text,
            color = color,
            style = GT.type.monoLabel,
            maxLines = 1,
        )
    }
}

@Composable
private fun GTStatusTone.color(): Color = when (this) {
    GTStatusTone.Muted -> GT.colors.muted
    GTStatusTone.Info -> GT.colors.info
    GTStatusTone.Good -> GT.colors.good
    GTStatusTone.Warn -> GT.colors.warn
}

@Composable
private fun GTBottomBarButton(
    item: GTBottomBarItem,
    onClick: (String) -> Unit,
    modifier: Modifier = Modifier,
    activeIndicatorColor: Color = GT.colors.ink,
    activeIndicatorUnderIcon: Boolean = false,
) {
    val color = if (item.selected) GT.colors.ink else GT.colors.muted
    Column(
        modifier = modifier
            .heightIn(min = GT.space.touch)
            .testTag("bottom-tab")
            .clickable(role = Role.Tab, onClick = { onClick(item.id) })
            .padding(top = 7.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(
            modifier = Modifier.size(22.dp),
            contentAlignment = Alignment.Center,
        ) {
            item.icon()
        }
        if (item.selected && activeIndicatorUnderIcon) {
            Box(
                modifier = Modifier
                    .padding(top = 2.dp)
                    .size(4.dp)
                    .background(activeIndicatorColor, CircleShape),
            )
        }
        Text(
            text = item.label.uppercase(),
            modifier = Modifier.padding(top = 3.dp),
            color = color,
            style = GT.type.kicker,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        if (item.selected && !activeIndicatorUnderIcon) {
            Box(
                modifier = Modifier
                    .padding(top = 4.dp)
                    .size(4.dp)
                    .background(activeIndicatorColor, CircleShape),
            )
        }
    }
}

@Composable
private fun GTPhotoGlyph() {
    val color = GT.colors.muted
    Canvas(modifier = Modifier.size(15.dp)) {
        val stroke = Stroke(width = 1.dp.toPx())
        drawRoundRect(
            color = color,
            style = stroke,
            cornerRadius = CornerRadius(2.dp.toPx(), 2.dp.toPx()),
            size = size,
        )
        drawCircle(
            color = color,
            radius = 1.2.dp.toPx(),
            center = Offset(size.width * 0.35f, size.height * 0.38f),
        )
        drawLine(
            color = color,
            start = Offset(size.width * 0.18f, size.height * 0.72f),
            end = Offset(size.width * 0.46f, size.height * 0.52f),
            strokeWidth = 1.dp.toPx(),
            cap = StrokeCap.Round,
        )
        drawLine(
            color = color,
            start = Offset(size.width * 0.46f, size.height * 0.52f),
            end = Offset(size.width * 0.68f, size.height * 0.68f),
            strokeWidth = 1.dp.toPx(),
            cap = StrokeCap.Round,
        )
        drawLine(
            color = color,
            start = Offset(size.width * 0.68f, size.height * 0.68f),
            end = Offset(size.width * 0.86f, size.height * 0.48f),
            strokeWidth = 1.dp.toPx(),
            cap = StrokeCap.Round,
        )
    }
}

@Composable
private fun GTPlusGlyph() {
    val color = GT.colors.surface2
    Canvas(modifier = Modifier.size(22.dp)) {
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

private fun Modifier.dottedBorder(
    color: Color,
    strokeWidth: Dp,
    radius: Dp,
): Modifier = drawBehind {
    val strokePx = strokeWidth.toPx()
    val inset = strokePx / 2f
    clipRect {
        drawRoundRect(
            color = color,
            topLeft = Offset(inset, inset),
            size = Size(size.width - strokePx, size.height - strokePx),
            cornerRadius = CornerRadius(radius.toPx(), radius.toPx()),
            style = Stroke(
                width = strokePx,
                pathEffect = PathEffect.dashPathEffect(
                    intervals = floatArrayOf(4.dp.toPx(), 4.dp.toPx()),
                ),
            ),
        )
    }
}
