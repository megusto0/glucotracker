package com.local.glucotracker.ui.design.primitives.__previews__

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.GTTheme
import com.local.glucotracker.ui.design.primitives.GTBottomBar
import com.local.glucotracker.ui.design.primitives.GTBottomBarItem
import com.local.glucotracker.ui.design.primitives.GTFab
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTHintBox
import com.local.glucotracker.ui.design.primitives.GTIconButton
import com.local.glucotracker.ui.design.primitives.GTKicker
import com.local.glucotracker.ui.design.primitives.GTKpiCard
import com.local.glucotracker.ui.design.primitives.GTMealRow
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.design.primitives.GTPhotoPlaceholderTone
import com.local.glucotracker.ui.design.primitives.GTPhotoSlot
import com.local.glucotracker.ui.design.primitives.GTPrimaryButton
import com.local.glucotracker.ui.design.primitives.GTSectionLabel
import com.local.glucotracker.ui.design.primitives.GTSegmented
import com.local.glucotracker.ui.design.primitives.GTTag

@Preview(showBackground = true, backgroundColor = 0xFFF6F4EF)
@Composable
fun GTHairlineDividerPreview() {
    PreviewFrame {
        GTHairlineDivider()
    }
}

@Preview(showBackground = true, backgroundColor = 0xFFF6F4EF)
@Composable
fun GTSectionLabelPreview() {
    PreviewFrame {
        GTSectionLabel(text = "СЕГОДНЯ")
    }
}

@Preview(showBackground = true, backgroundColor = 0xFFF6F4EF)
@Composable
fun GTKickerPreview() {
    PreviewFrame {
        GTKicker(text = "ВТОРНИК")
    }
}

@Preview(showBackground = true, backgroundColor = 0xFFF6F4EF)
@Composable
fun GTKpiCardPreview() {
    PreviewFrame {
        GTKpiCard(
            label = "ККАЛ",
            value = "1536",
            sub = "цель 2200 · 70%",
            progress = 0.7f,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Preview(showBackground = true, backgroundColor = 0xFFF6F4EF)
@Composable
fun GTTagPreview() {
    PreviewFrame {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            GTTag(text = "Частые", active = true)
            GTTag(text = "Фото")
        }
    }
}

@Preview(showBackground = true, backgroundColor = 0xFFF6F4EF)
@Composable
fun GTOutlineButtonPreview() {
    PreviewFrame {
        GTOutlineButton(text = "Отклонить", onClick = {})
    }
}

@Preview(showBackground = true, backgroundColor = 0xFFF6F4EF)
@Composable
fun GTPrimaryButtonPreview() {
    PreviewFrame {
        GTPrimaryButton(text = "Принять", onClick = {})
    }
}

@Preview(showBackground = true, backgroundColor = 0xFFF6F4EF)
@Composable
fun GTIconButtonPreview() {
    PreviewFrame {
        GTIconButton(onClick = {}) {
            ChevronIcon()
        }
    }
}

@Preview(showBackground = true, backgroundColor = 0xFFF6F4EF)
@Composable
fun GTSegmentedPreview() {
    PreviewFrame {
        GTSegmented(
            options = listOf("3 ч", "6 ч", "24 ч", "7 дн"),
            selected = "6 ч",
            onSelect = {},
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Preview(showBackground = true, backgroundColor = 0xFFF6F4EF)
@Composable
fun GTPhotoSlotPreview() {
    PreviewFrame {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            GTPhotoSlot(model = null, placeholderTone = GTPhotoPlaceholderTone.Background)
            GTPhotoSlot(model = null, placeholderTone = GTPhotoPlaceholderTone.Surface, modifier = Modifier.size(64.dp))
        }
    }
}

@Preview(showBackground = true, backgroundColor = 0xFFF6F4EF)
@Composable
fun GTMealRowPreview() {
    PreviewFrame {
        GTMealRow(
            time = "20:08",
            photo = null,
            name = "Бисквит-сэндвич ×2",
            meta = "20:08 · фото",
            primaryRight = "37 г угл",
            secondaryRight = "246 ккал",
            status = null,
        )
    }
}

@Preview(showBackground = true, backgroundColor = 0xFFF6F4EF)
@Composable
fun GTBottomBarPreview() {
    PreviewFrame {
        GTBottomBar(
            items = listOf(
                GTBottomBarItem("today", "Сегодня", selected = true) { CalendarIcon() },
                GTBottomBarItem("stats", "Стат.") { SparkIcon() },
                GTBottomBarItem("history", "История") { ClockIcon() },
                GTBottomBarItem("more", "Ещё") { MoreIcon() },
            ),
            onClick = {},
            centerSlot = {
                GTFab(onClick = {}, modifier = Modifier.padding(top = 4.dp))
            },
        )
    }
}

@Preview(showBackground = true, backgroundColor = 0xFFF6F4EF)
@Composable
fun GTFabPreview() {
    PreviewFrame {
        GTFab(onClick = {})
    }
}

@Preview(showBackground = true, backgroundColor = 0xFFF6F4EF)
@Composable
fun GTHintBoxPreview() {
    PreviewFrame {
        GTHintBox(text = "Доступно в десктоп-версии.")
    }
}

@Composable
private fun PreviewFrame(content: @Composable () -> Unit) {
    GTTheme {
        Box(
            modifier = Modifier
                .background(GT.colors.bg)
                .padding(18.dp),
            contentAlignment = Alignment.Center,
        ) {
            content()
        }
    }
}

@Composable
private fun ChevronIcon() {
    val color = GT.colors.ink2
    Canvas(modifier = Modifier.size(14.dp)) {
        drawLine(
            color = color,
            start = androidx.compose.ui.geometry.Offset(size.width * 0.35f, size.height * 0.2f),
            end = androidx.compose.ui.geometry.Offset(size.width * 0.65f, size.height * 0.5f),
            strokeWidth = 1.6.dp.toPx(),
            cap = StrokeCap.Round,
        )
        drawLine(
            color = color,
            start = androidx.compose.ui.geometry.Offset(size.width * 0.65f, size.height * 0.5f),
            end = androidx.compose.ui.geometry.Offset(size.width * 0.35f, size.height * 0.8f),
            strokeWidth = 1.6.dp.toPx(),
            cap = StrokeCap.Round,
        )
    }
}

@Composable
private fun CalendarIcon() {
    val color = GT.colors.ink
    OutlineBoxIcon {
        drawLine(color, androidx.compose.ui.geometry.Offset(2.dp.toPx(), 7.dp.toPx()), androidx.compose.ui.geometry.Offset(size.width - 2.dp.toPx(), 7.dp.toPx()), 1.4.dp.toPx())
    }
}

@Composable
private fun ClockIcon() {
    val color = GT.colors.muted
    Canvas(modifier = Modifier.size(20.dp)) {
        drawCircle(color = color, radius = 7.dp.toPx(), style = Stroke(1.4.dp.toPx()))
        drawLine(color, center, androidx.compose.ui.geometry.Offset(center.x, center.y - 4.dp.toPx()), 1.4.dp.toPx(), cap = StrokeCap.Round)
        drawLine(color, center, androidx.compose.ui.geometry.Offset(center.x + 3.dp.toPx(), center.y + 2.dp.toPx()), 1.4.dp.toPx(), cap = StrokeCap.Round)
    }
}

@Composable
private fun SparkIcon() {
    val color = GT.colors.muted
    Canvas(modifier = Modifier.size(20.dp)) {
        val points = listOf(
            androidx.compose.ui.geometry.Offset(2.dp.toPx(), 12.dp.toPx()),
            androidx.compose.ui.geometry.Offset(6.dp.toPx(), 12.dp.toPx()),
            androidx.compose.ui.geometry.Offset(8.dp.toPx(), 7.dp.toPx()),
            androidx.compose.ui.geometry.Offset(11.dp.toPx(), 15.dp.toPx()),
            androidx.compose.ui.geometry.Offset(14.dp.toPx(), 10.dp.toPx()),
            androidx.compose.ui.geometry.Offset(18.dp.toPx(), 10.dp.toPx()),
        )
        points.zipWithNext().forEach { (start, end) ->
            drawLine(color, start, end, 1.4.dp.toPx(), cap = StrokeCap.Round)
        }
    }
}

@Composable
private fun MoreIcon() {
    val color = GT.colors.muted
    Canvas(modifier = Modifier.size(20.dp)) {
        drawCircle(color, radius = 1.4.dp.toPx(), center = androidx.compose.ui.geometry.Offset(4.5.dp.toPx(), center.y))
        drawCircle(color, radius = 1.4.dp.toPx(), center = center)
        drawCircle(color, radius = 1.4.dp.toPx(), center = androidx.compose.ui.geometry.Offset(15.5.dp.toPx(), center.y))
    }
}

@Composable
private fun OutlineBoxIcon(content: androidx.compose.ui.graphics.drawscope.DrawScope.() -> Unit = {}) {
    val color = GT.colors.muted
    Canvas(modifier = Modifier.size(20.dp)) {
        drawRoundRect(
            color = color,
            topLeft = androidx.compose.ui.geometry.Offset(2.5.dp.toPx(), 3.5.dp.toPx()),
            size = androidx.compose.ui.geometry.Size(15.dp.toPx(), 14.dp.toPx()),
            style = Stroke(1.4.dp.toPx()),
        )
        content()
    }
}
