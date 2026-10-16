package com.local.glucotracker.domain.model

import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate

/** Sleep or effort as a background span on the glucose chart. */
data class BodySpan(
    val kind: Kind,
    val startAt: Instant,
    val endAt: Instant,
    val totalMinutes: Int,
    /** What the watch or the owner called it ("Велосипед"), if anyone did. */
    val label: String?,
    /** Read from heart rate by the server rather than recorded by a device. */
    val inferred: Boolean,
    val meanBpm: Int?,
) {
    enum class Kind { Sleep, Activity }
}

/** Insulin and carbs still acting, as the server's models see them now. */
data class ActiveGlucoseContext(
    val iobUnits: Double,
    val iobMinutesRemaining: Int?,
    val cobGrams: Double,
    val cobMinutesRemaining: Int?,
)

/** Server-computed time in range for one local day; null when not measured. */
data class GlucoseTirDay(
    val date: LocalDate,
    val veryLowPercent: Double?,
    val lowPercent: Double?,
    val inRangePercent: Double?,
    val highPercent: Double?,
    val veryHighPercent: Double?,
)

/**
 * One sitting as the server grouped it: its meals and the insulin given for
 * them, with the server's totals. The chart draws it as one carbs mark and
 * one insulin mark.
 */
data class GlucoseEpisodeMark(
    val key: String,
    val startAt: Instant,
    val mealIds: Set<String>,
    val insulinIds: Set<String>,
    val totalCarbsG: Double,
    val totalInsulinUnits: Double,
    val firstInsulinAt: Instant?,
    /** Every dose in the sitting was a correction or catch-up, none for food. */
    val correctionOnly: Boolean,
)
