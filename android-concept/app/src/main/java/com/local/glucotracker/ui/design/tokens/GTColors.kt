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
    /**
     * What a record was, and what the body was doing under it.
     *
     * Six carriers of meaning that lightness alone could not separate: four
     * kinds of entry a day is made of, plus sleep and effort. They live only in
     * a marker — a dot, a rail, a strip over a photo, the outline of a circle
     * on the chart. Never a row background, never text, never a number: six
     * kinds tinting whole rows turns a journal into a traffic light.
     *
     * A meal is graphite on purpose. It is the commonest kind and must not
     * shout; the ones worth finding by eye are the two corrections.
     */
    val kindMeal: Color,
    val kindSnack: Color,
    val kindCarbRescue: Color,
    val kindInsulinCorrection: Color,
    val stateSleep: Color,
    val stateActivity: Color,
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
    kindMeal = Color(0xFF56534C),
    kindSnack = Color(0xFF9A7B33),
    kindCarbRescue = Color(0xFFA8624E),
    kindInsulinCorrection = Color(0xFF4F6274),
    stateSleep = Color(0xFF6B6A80),
    stateActivity = Color(0xFF5E6B4A),
)

val LocalGTColors = staticCompositionLocalOf { GTLightColors }
