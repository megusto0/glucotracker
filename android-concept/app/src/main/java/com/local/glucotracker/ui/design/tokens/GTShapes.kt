package com.local.glucotracker.ui.design.tokens

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.unit.dp

data class GTShapes(
    val card: Shape,
    val tag: Shape,
    val iconButton: Shape,
    val fab: Shape,
)

val GTDefaultShapes = GTShapes(
    card = RoundedCornerShape(10.dp),
    tag = RoundedCornerShape(6.dp),
    iconButton = RoundedCornerShape(6.dp),
    fab = RoundedCornerShape(16.dp),
)

val LocalGTShapes = staticCompositionLocalOf { GTDefaultShapes }
