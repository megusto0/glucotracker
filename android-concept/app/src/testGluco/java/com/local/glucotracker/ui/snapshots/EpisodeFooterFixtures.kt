package com.local.glucotracker.ui.snapshots

import com.local.glucotracker.domain.model.EpisodeFooterOutcome
import com.local.glucotracker.domain.model.EpisodeFooterSummary
import com.local.glucotracker.domain.model.EpisodeOutcomeKind
import com.local.glucotracker.domain.model.EpisodeOutcomeStatus
import com.local.glucotracker.domain.model.EpisodeTherapyClass
import com.local.glucotracker.domain.model.InsulinEvent
import com.local.glucotracker.domain.model.InsulinEventType
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDateTime
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toInstant

/**
 * The widest the meal footer gets: a long dose line beside an unsettled
 * outcome.
 *
 * This is the case the even split could not hold — «9,0 ЕД вместе с едой» was
 * given half the card next to the outcome and came out as «9,0 ЕД вместе с
 * едо…», while the outcome clipped on its own side with no ellipsis at all.
 * Both sides have to survive at once, so the golden asks for both at once.
 */
internal val FOOTER_MEAL_AT: Instant =
    LocalDateTime(2026, 8, 16, 14, 11).toInstant(TimeZone.currentSystemDefault())

internal fun footerMealBolus(): List<InsulinEvent> = listOf(
    InsulinEvent(
        id = "33333333-3333-3333-3333-333333333333",
        timestamp = FOOTER_MEAL_AT,
        doseUnits = 9.0,
        source = "nightscout",
        sourceEventId = "ns-2",
        eventType = InsulinEventType.Bolus,
    ),
)

internal fun footerOngoing(): EpisodeFooterSummary = EpisodeFooterSummary(
    episodeKey = "2026-08-16:meal:44444444-4444-4444-4444-444444444444",
    classification = EpisodeTherapyClass.Meal,
    outcome = EpisodeFooterOutcome(
        status = EpisodeOutcomeStatus.Ongoing,
        kind = EpisodeOutcomeKind.Peak,
        startValue = 6.2,
        resultValue = null,
        deltaMmolL = null,
        isLow = false,
    ),
)

/** The settled form, which is the one carrying two numbers on the right. */
internal fun footerPeak(): EpisodeFooterSummary = footerOngoing().copy(
    outcome = footerOngoing().outcome.copy(
        status = EpisodeOutcomeStatus.Complete,
        resultValue = 11.4,
        deltaMmolL = 5.2,
    ),
)

internal fun footerMealIds(): List<String> =
    listOf("44444444-4444-4444-4444-444444444444")
