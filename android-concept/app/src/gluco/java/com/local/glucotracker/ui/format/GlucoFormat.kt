package com.local.glucotracker.ui.format

import java.math.BigDecimal
import java.text.DecimalFormat
import java.text.DecimalFormatSymbols
import java.util.Locale

/** Gluco-only formatting; the food flavor has no insulin to show. */

private val GlucoRuLocale = Locale("ru")

/** Insulin units, one decimal with the Russian comma: «4,0». */
fun formatInsulinUnits(value: Double): String =
    DecimalFormat("0.0", DecimalFormatSymbols(GlucoRuLocale)).format(BigDecimal.valueOf(value))

/** A span as it is spoken about: «7:12», not «432 мин». */
fun formatClockDuration(totalMinutes: Int): String {
    val minutes = totalMinutes.coerceAtLeast(0)
    return "%d:%02d".format(minutes / 60, minutes % 60)
}
