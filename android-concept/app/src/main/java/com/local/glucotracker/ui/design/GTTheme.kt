package com.local.glucotracker.ui.design

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.ReadOnlyComposable
import com.local.glucotracker.ui.design.tokens.GTColors
import com.local.glucotracker.ui.design.tokens.GTDefaultShapes
import com.local.glucotracker.ui.design.tokens.GTDefaultSpacing
import com.local.glucotracker.ui.design.tokens.GTDefaultTypography
import com.local.glucotracker.ui.design.tokens.GTLightColors
import com.local.glucotracker.ui.design.tokens.GTShapes
import com.local.glucotracker.ui.design.tokens.GTSpacing
import com.local.glucotracker.ui.design.tokens.GTTypography
import com.local.glucotracker.ui.design.tokens.LocalGTColors
import com.local.glucotracker.ui.design.tokens.LocalGTShapes
import com.local.glucotracker.ui.design.tokens.LocalGTSpacing
import com.local.glucotracker.ui.design.tokens.LocalGTTypography

object GT {
    val colors: GTColors
        @Composable
        @ReadOnlyComposable
        get() = LocalGTColors.current

    val type: GTTypography
        @Composable
        @ReadOnlyComposable
        get() = LocalGTTypography.current

    val space: GTSpacing
        @Composable
        @ReadOnlyComposable
        get() = LocalGTSpacing.current

    val shapes: GTShapes
        @Composable
        @ReadOnlyComposable
        get() = LocalGTShapes.current
}

@Composable
fun GTTheme(
    colors: GTColors = GTLightColors,
    type: GTTypography = GTDefaultTypography,
    space: GTSpacing = GTDefaultSpacing,
    shapes: GTShapes = GTDefaultShapes,
    content: @Composable () -> Unit,
) {
    val materialColors = lightColorScheme(
        primary = colors.ink,
        onPrimary = colors.surface2,
        secondary = colors.accent,
        onSecondary = colors.surface2,
        tertiary = colors.warn,
        background = colors.bg,
        onBackground = colors.ink,
        surface = colors.bg,
        onSurface = colors.ink,
        surfaceVariant = colors.surface,
        onSurfaceVariant = colors.ink2,
        outline = colors.muted,
        outlineVariant = colors.hairline2,
    )

    val materialTypography = Typography(
        displaySmall = type.serifTitle,
        headlineMedium = type.serifTitle,
        titleMedium = type.serifSection,
        bodyMedium = type.sansBody,
        labelMedium = type.sansLabel,
    )

    CompositionLocalProvider(
        LocalGTColors provides colors,
        LocalGTTypography provides type,
        LocalGTSpacing provides space,
        LocalGTShapes provides shapes,
    ) {
        MaterialTheme(
            colorScheme = materialColors,
            typography = materialTypography,
            content = content,
        )
    }
}
