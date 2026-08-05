package com.local.glucotracker.ui.glucose

import kotlin.time.Duration
import kotlin.time.Duration.Companion.minutes
import kotlinx.datetime.Instant

/**
 * Largest gap between two plates that still counts as one sitting.
 *
 * The backend episode engine connects meals through shared insulin, so a bolus
 * that falls inside the linking window of two meals merges them however far
 * apart they are. That is the right unit for attributing insulin, but not for
 * asking how much a meal needs: on 2026-08-02 it joined a 16:19 lunch to a
 * 17:21 snack and offered a dose for both at once.
 *
 * Must equal SITTING_SPAN in backend `grouping.py`. ADR-019 §2.3 wants this
 * narrowing gone and the sitting supplied by the backend; it stays until the
 * episodes response carries sittings, because insulin-linked episodes still
 * span wider than one and removing it would undo 9b41bef.
 */
val EatingOccasionGap: Duration = 30.minutes

/**
 * Narrow an episode to the sitting that contains [anchorId].
 *
 * Walks outward from the anchor while consecutive plates stay within
 * [EatingOccasionGap], so a later snack that the episode happens to include is
 * left out. Meals with no known time are kept, since dropping them would
 * silently shrink the carbohydrate the caller is asking about.
 */
fun eatingOccasion(
    episodeMealIds: List<String>,
    eatenAt: Map<String, Instant>,
    anchorId: String,
): List<String> {
    if (anchorId !in episodeMealIds) return listOf(anchorId)
    val timed = episodeMealIds.filter { it in eatenAt }.sortedBy { eatenAt.getValue(it) }
    val untimed = episodeMealIds.filter { it !in eatenAt }
    if (anchorId !in timed) return episodeMealIds

    val anchor = timed.indexOf(anchorId)
    var first = anchor
    while (first > 0 &&
        eatenAt.getValue(timed[first]) - eatenAt.getValue(timed[first - 1]) <=
        EatingOccasionGap
    ) {
        first--
    }
    var last = anchor
    while (last < timed.lastIndex &&
        eatenAt.getValue(timed[last + 1]) - eatenAt.getValue(timed[last]) <=
        EatingOccasionGap
    ) {
        last++
    }
    val kept = timed.subList(first, last + 1).toSet()
    return episodeMealIds.filter { it in kept || it in untimed }
}
