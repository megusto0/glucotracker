package com.local.glucotracker.ui.glucose

import kotlin.time.Duration
import kotlin.time.Duration.Companion.minutes

/**
 * Insulin given later than this after its own meal is a follow-up rather than
 * coverage. Ten minutes keeps a bolus logged a moment after the plate on the
 * "with the food" side while still separating a genuine catch-up dose.
 */
val OnTimeBolusWindow: Duration = 10.minutes

/** One bolus and how long after its meal it arrived. */
data class EpisodeDose(
    val units: Double,
    val lateBy: Duration,
)

/**
 * What an eating occasion's dose actually worked out to.
 *
 * The totals already on screen cannot show this: the same number of units can
 * be right for the food and still arrive after it, and that is what leaves
 * insulin acting once the carbohydrate is gone.
 */
data class EpisodeCoverage(
    val gramsPerUnit: Double,
    val onTimeUnits: Double,
    val lateUnits: Double,
)

/** Return the achieved ratio and timing split, or null when either is undefined. */
fun episodeCoverage(
    doses: List<EpisodeDose>,
    totalCarbs: Double,
    totalInsulin: Double,
): EpisodeCoverage? {
    if (totalCarbs <= 0.0 || totalInsulin <= 0.0) return null
    var onTime = 0.0
    var late = 0.0
    doses.forEach { dose ->
        if (dose.lateBy > OnTimeBolusWindow) {
            late += dose.units
        } else {
            onTime += dose.units
        }
    }
    return EpisodeCoverage(
        gramsPerUnit = totalCarbs / totalInsulin,
        onTimeUnits = onTime,
        lateUnits = late,
    )
}
