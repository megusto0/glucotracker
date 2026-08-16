package com.local.glucotracker.ui.snapshots

import com.local.glucotracker.domain.model.EpisodeFooterOutcome
import com.local.glucotracker.domain.model.EpisodeFooterSummary
import com.local.glucotracker.domain.model.EpisodeOutcomeKind
import com.local.glucotracker.domain.model.EpisodeOutcomeStatus
import com.local.glucotracker.domain.model.EpisodeTherapyClass
import com.local.glucotracker.domain.model.InsulinEvent
import com.local.glucotracker.domain.model.InsulinEventType
import kotlinx.datetime.LocalDate
import kotlinx.datetime.LocalDateTime
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toInstant

/**
 * The evening correction from the report: a unit given on its own at 11:11,
 * against 12,5 that came down to 4,7.
 *
 * Built in the render's own zone. A fixed UTC instant prints four hours off on
 * this device config, and a golden nobody can read is a golden nobody checks.
 */
internal fun standaloneCorrection(): InsulinEvent = InsulinEvent(
    id = "22222222-2222-2222-2222-222222222222",
    timestamp = LocalDateTime(2026, 8, 8, 11, 11).toInstant(TimeZone.currentSystemDefault()),
    doseUnits = 1.0,
    source = "nightscout",
    sourceEventId = "ns-1",
    eventType = InsulinEventType.Correction,
)

internal fun standaloneCorrectionFooter(): EpisodeFooterSummary = EpisodeFooterSummary(
    episodeKey = "2026-08-08:insulin:22222222-2222-2222-2222-222222222222",
    classification = EpisodeTherapyClass.InsulinCorrection,
    outcome = EpisodeFooterOutcome(
        status = EpisodeOutcomeStatus.Complete,
        kind = EpisodeOutcomeKind.Minimum,
        startValue = 12.5,
        resultValue = 4.7,
        deltaMmolL = -7.8,
        isLow = false,
    ),
)

internal fun standaloneCorrectionDate(): LocalDate = LocalDate(2026, 8, 8)
