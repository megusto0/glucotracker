package com.local.glucotracker.ui.design.tokens

import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

data class GTSpacing(
    val hairline: Dp,
    val xxs: Dp,
    val xs: Dp,
    val sm: Dp,
    val md: Dp,
    val lg: Dp,
    val xl: Dp,
    val touch: Dp,
)

val GTDefaultSpacing = GTSpacing(
    hairline = 0.5.dp,
    xxs = 2.dp,
    xs = 4.dp,
    sm = 8.dp,
    md = 12.dp,
    lg = 16.dp,
    xl = 18.dp,
    touch = 44.dp,
)

val LocalGTSpacing = staticCompositionLocalOf { GTDefaultSpacing }
