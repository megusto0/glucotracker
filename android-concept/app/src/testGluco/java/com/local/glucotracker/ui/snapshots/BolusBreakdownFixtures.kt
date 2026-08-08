package com.local.glucotracker.ui.snapshots

import com.local.glucotracker.domain.model.InsulinEvent
import com.local.glucotracker.domain.model.InsulinEventType
import com.local.glucotracker.ui.glucose.BolusCalcUi
import com.local.glucotracker.ui.glucose.BolusStateUi
import com.local.glucotracker.ui.glucose.BolusTermUi
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDateTime
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toInstant

/** The sitting behind mockup screen G: four boluses, the last one chasing. */
private val EVENING = LocalDateTime(2026, 8, 6, 19, 55)
    .toInstant(TimeZone.currentSystemDefault())

private fun at(minutes: Int): Instant =
    EVENING.plus(kotlin.time.Duration.parse("${minutes}m"))

internal fun sittingBoluses(): List<InsulinEvent> = listOf(
    dose("a", 1.4, at(0), InsulinEventType.Bolus),
    dose("b", 8.0, at(18), InsulinEventType.Bolus),
    dose("c", 3.0, at(35), InsulinEventType.Bolus),
    dose("d", 2.2, at(97), InsulinEventType.CatchUp),
)

internal fun sittingMealAt(): Instant = at(18)

private fun dose(id: String, units: Double, at: Instant, kind: InsulinEventType) =
    InsulinEvent(
        id = id,
        timestamp = at,
        doseUnits = units,
        source = "Nightscout",
        sourceEventId = id,
        eventType = kind,
    )

internal fun chasingBolusCalc(): BolusCalcUi = BolusCalcUi(
    state = BolusStateUi(
        glucose = 12.4,
        iob = 3.9,
        cob = 34.0,
        icr = 8.0,
        isf = 2.6,
        target = 6.0,
    ),
    terms = listOf(
        BolusTermUi("correction", "(12,4−6,0) / 2,6", 2.5),
        BolusTermUi("carbs", "34 г / 8,0", 4.3),
        BolusTermUi("iob", null, -3.9),
    ),
    suggestedUnits = 2.9,
    unavailableNote = null,
    projectionStale = true,
)
