package com.local.glucotracker.ui.feature.insulin

import kotlin.math.abs

/**
 * Doses are entered and displayed to a tenth, so anything smaller than half a
 * step is a rounding artefact rather than a real disagreement.
 */
const val DoseMatchToleranceUnits = 0.05

/** How an already-given dose compares with the historical calculation. */
sealed interface DoseComparison {
    /** The two agree once dose rounding is taken into account. */
    data object Match : DoseComparison

    /** The calculation asks for more than was given, by [byUnits]. */
    data class CalculationHigher(val byUnits: Double) : DoseComparison

    /** The calculation asks for less than was given, by [byUnits]. */
    data class CalculationLower(val byUnits: Double) : DoseComparison
}

/**
 * Compare what was actually injected against the historical calculation.
 *
 * Returns null when there is nothing to compare, so a caller can keep showing a
 * plain recommendation rather than a comparison of a number against nothing.
 */
fun doseComparison(givenUnits: Double, recommendedUnits: Double): DoseComparison? {
    if (givenUnits <= 0.0) return null
    val delta = recommendedUnits - givenUnits
    return when {
        abs(delta) < DoseMatchToleranceUnits -> DoseComparison.Match
        delta > 0.0 -> DoseComparison.CalculationHigher(delta)
        else -> DoseComparison.CalculationLower(-delta)
    }
}
