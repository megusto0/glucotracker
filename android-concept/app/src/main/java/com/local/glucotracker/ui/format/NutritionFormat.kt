package com.local.glucotracker.ui.format

import java.math.BigDecimal
import java.math.RoundingMode
import java.text.DecimalFormat
import java.text.DecimalFormatSymbols
import java.text.NumberFormat
import java.util.Locale
import kotlin.math.roundToInt

private val RuLocale = Locale("ru")

fun formatKcal(value: Number): String =
    NumberFormat.getIntegerInstance(RuLocale)
        .format(BigDecimal.valueOf(value.toDouble()).setScale(0, RoundingMode.HALF_UP))

fun formatGrams(value: Double): String =
    decimal("#,##0.#").format(BigDecimal.valueOf(value))

fun formatMmol(value: Double): String =
    decimal("0.0").format(BigDecimal.valueOf(value))

fun formatKg(value: Double): String =
    decimal("0.00").format(BigDecimal.valueOf(value))

fun formatSignedKcal(value: Long): String =
    if (value < 0) "−${-value}" else value.toString()

fun formatPercent(value: Double): String =
    "${value.roundToInt()}%"

fun truncateToLines(text: String, maxLines: Int, charsPerLine: Int): String {
    val maxChars = maxLines * charsPerLine
    if (text.length <= maxChars) return text
    val cut = text.substring(0, maxChars)
    val lastSentenceEnd = cut.lastIndexOf(". ")
    if (lastSentenceEnd > 0) {
        return cut.substring(0, lastSentenceEnd + 1)
    }
    return text
}

private fun decimal(pattern: String): DecimalFormat =
    DecimalFormat(pattern, DecimalFormatSymbols(RuLocale)).apply {
        isGroupingUsed = pattern.contains("#,")
        roundingMode = RoundingMode.HALF_UP
    }
