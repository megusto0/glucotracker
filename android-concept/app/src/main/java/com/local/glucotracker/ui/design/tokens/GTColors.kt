package com.local.glucotracker.ui.design.tokens

import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

data class GTColors(
    val bg: Color,
    val surface: Color,
    val surface2: Color,
    val ink: Color,
    val ink2: Color,
    val muted: Color,
    val hairline: Color,
    val hairline2: Color,
    val accent: Color,
    val good: Color,
    val warn: Color,
    val bad: Color,
    val info: Color,
)

val GTLightColors = GTColors(
    bg = Color(0xFFF6F4EF),
    surface = Color(0xFFFBFAF6),
    surface2 = Color(0xFFFFFFFF),
    ink = Color(0xFF25241F),
    ink2 = Color(0xFF4A4842),
    muted = Color(0xFF8A857A),
    hairline = Color(0xFFE6E2D6),
    hairline2 = Color(0xFFD8D3C4),
    accent = Color(0xFF5E6F3A),
    good = Color(0xFF6B8A5A),
    warn = Color(0xFFC98A55),
    bad = Color(0xFF2D3340),
    info = Color(0xFF6B7A92),
)

val LocalGTColors = staticCompositionLocalOf { GTLightColors }
