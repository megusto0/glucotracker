package com.local.glucotracker.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable

private val LightColorScheme = lightColorScheme(
    primary = Ink,
    onPrimary = Surface2,
    secondary = Accent,
    onSecondary = Surface2,
    tertiary = Warn,
    background = Bg,
    onBackground = Ink,
    surface = Surface,
    onSurface = Ink,
    surfaceVariant = Surface2,
    onSurfaceVariant = Ink2,
    outline = Hairline,
    outlineVariant = Hairline2,
)

@Composable
fun GlucotrackerTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = LightColorScheme,
        content = content,
    )
}
