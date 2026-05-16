package com.local.glucotracker.ui.design.tokens

import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.local.glucotracker.R

data class GTTypography(
    val serifTitle: TextStyle,
    val serifSection: TextStyle,
    val sansBody: TextStyle,
    val sansLabel: TextStyle,
    val monoNumber: TextStyle,
    val monoLabel: TextStyle,
    val kicker: TextStyle,
)

val GTSerifFamily = FontFamily(
    Font(R.font.pt_serif_regular, FontWeight.Normal),
    Font(R.font.pt_serif_bold, FontWeight.Bold),
)

val GTSansFamily = FontFamily(
    Font(R.font.inter_variable, FontWeight.Normal),
    Font(R.font.inter_variable, FontWeight.Medium),
    Font(R.font.inter_variable, FontWeight.SemiBold),
    Font(R.font.inter_variable, FontWeight.Bold),
)

val GTMonoFamily = FontFamily(
    Font(R.font.jetbrains_mono_regular, FontWeight.Normal),
    Font(R.font.jetbrains_mono_medium, FontWeight.Medium),
)

val GTDefaultTypography = GTTypography(
    serifTitle = TextStyle(
        fontFamily = GTSerifFamily,
        fontSize = 30.sp,
        fontWeight = FontWeight.Normal,
        letterSpacing = 0.sp,
        lineHeight = 34.sp,
    ),
    serifSection = TextStyle(
        fontFamily = GTSerifFamily,
        fontSize = 22.sp,
        fontWeight = FontWeight.Normal,
        letterSpacing = 0.sp,
        lineHeight = 27.sp,
    ),
    sansBody = TextStyle(
        fontFamily = GTSansFamily,
        fontSize = 13.sp,
        fontWeight = FontWeight.Normal,
        letterSpacing = 0.sp,
        lineHeight = 18.sp,
    ),
    sansLabel = TextStyle(
        fontFamily = GTSansFamily,
        fontSize = 12.sp,
        fontWeight = FontWeight.Medium,
        letterSpacing = 0.sp,
        lineHeight = 16.sp,
    ),
    monoNumber = TextStyle(
        fontFamily = GTMonoFamily,
        fontSize = 22.sp,
        fontWeight = FontWeight.Medium,
        letterSpacing = 0.sp,
        lineHeight = 27.sp,
    ),
    monoLabel = TextStyle(
        fontFamily = GTMonoFamily,
        fontSize = 10.sp,
        fontWeight = FontWeight.Normal,
        letterSpacing = 0.sp,
        lineHeight = 14.sp,
    ),
    kicker = TextStyle(
        fontFamily = GTSansFamily,
        fontSize = 9.sp,
        fontWeight = FontWeight.SemiBold,
        letterSpacing = 1.2.sp,
        lineHeight = 12.sp,
    ),
)

val LocalGTTypography = staticCompositionLocalOf { GTDefaultTypography }
