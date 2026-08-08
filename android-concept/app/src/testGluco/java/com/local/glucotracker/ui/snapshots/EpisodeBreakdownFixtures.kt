package com.local.glucotracker.ui.snapshots

import com.local.glucotracker.ui.glucose.BreakdownAnchorUi
import com.local.glucotracker.ui.glucose.BreakdownCrossingUi
import com.local.glucotracker.ui.glucose.BreakdownDerivedUi
import com.local.glucotracker.ui.glucose.BreakdownPointUi
import com.local.glucotracker.ui.glucose.EpisodeBreakdownUi
import kotlin.math.roundToInt
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDateTime
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toInstant

/**
 * The night behind mockup screen H, as the backend returns it.
 *
 * Same trace as the backend's own breakdown test: a correction at 00:18, the
 * low it caused at 01:05, twelve grams of juice answering it, and a biscuit at
 * 02:20 whose rise belongs to the biscuit.
 */
// Built in the render's own zone so the golden prints the clock times the
// mockup names. A fixed UTC instant renders four hours off on this device
// config, and a golden nobody can read is a golden nobody checks.
private val NIGHT = LocalDateTime(2026, 8, 6, 0, 0)
    .toInstant(TimeZone.currentSystemDefault())

private fun at(minutes: Int): Instant = NIGHT.plus(kotlin.time.Duration.parse("${minutes}m"))

private val CURVE = listOf(
    -30 to 7.4, 0 to 6.8, 18 to 6.1, 42 to 4.8, 60 to 3.7, 65 to 3.6,
    84 to 4.4, 102 to 6.3, 114 to 7.5, 123 to 7.9, 140 to 7.2, 162 to 7.8,
    186 to 8.3, 210 to 7.6, 240 to 6.6, 276 to 6.1, 330 to 5.8,
)

private fun curvePoints(): List<BreakdownPointUi> {
    val points = mutableListOf<BreakdownPointUi>()
    CURVE.zipWithNext { (startMin, startValue), (endMin, endValue) ->
        var step = startMin
        while (step < endMin) {
            val share = (step - startMin).toDouble() / (endMin - startMin)
            val value = startValue + (endValue - startValue) * share
            points += BreakdownPointUi(
                at = at(step),
                value = (value * 10).roundToInt() / 10.0,
                isLow = value < 3.9,
            )
            step += 5
        }
    }
    val last = CURVE.last()
    points += BreakdownPointUi(at(last.first), last.second, last.second < 3.9)
    return points
}

internal fun nightRescueBreakdown(): EpisodeBreakdownUi = EpisodeBreakdownUi(
    classification = "carb_correction",
    title = "Сок яблочный",
    subtitle = "12 г",
    startAt = at(65),
    windowFrom = at(-55),
    windowTo = at(305),
    lowThreshold = 3.9,
    points = curvePoints(),
    anchors = listOf(
        BreakdownAnchorUi("trough", "Минимум перед приёмом", at(65), 3.6, null),
        BreakdownAnchorUi("peak", "Пик", at(123), 7.9, "через 58 мин"),
        BreakdownAnchorUi("settle", "После усвоения", at(185), 7.2, "2 ч"),
    ),
    derived = listOf(
        BreakdownDerivedUi("Подъём на 12 г", 4.3, 0.36, "ммоль/л на г"),
    ),
    crossings = listOf(
        BreakdownCrossingUi(
            kind = "insulin",
            therapyClass = "insulin_correction",
            label = "Коррекция инсулином 3,0 ЕД",
            at = at(18),
            offsetMinutes = -47,
            detail = null,
        ),
        BreakdownCrossingUi(
            kind = "episode",
            therapyClass = "meal",
            label = "Печенье, 53 г · 4,0 ЕД",
            at = at(140),
            offsetMinutes = 75,
            detail = null,
        ),
        BreakdownCrossingUi(
            kind = "sleep",
            therapyClass = null,
            label = "Сон",
            at = at(40),
            offsetMinutes = -25,
            detail = "00:40—06:40",
        ),
    ),
    causeText = "Гипо через 47 мин после коррекции инсулином на активном IOB 2,4 ЕД." +
        " Не еда — доза.",
    frequencyLabel = "Ночная гипо за 30 дней: 4",
)

/** The same frame for ordinary food, which is the point of the system. */
internal fun coveredMealBreakdown(): EpisodeBreakdownUi = EpisodeBreakdownUi(
    classification = "meal",
    title = "Паста с курицей",
    subtitle = "78 г · 8,0 ЕД",
    startAt = at(65),
    windowFrom = at(-55),
    windowTo = at(305),
    lowThreshold = 3.9,
    points = curvePoints(),
    anchors = listOf(
        BreakdownAnchorUi("start", "Перед едой", at(65), 3.6, null),
        BreakdownAnchorUi("peak", "Пик", at(123), 7.9, "через 58 мин"),
        BreakdownAnchorUi("settle", "Через 2 ч", at(185), 7.2, null),
    ),
    derived = listOf(
        BreakdownDerivedUi("Подъём на 78 г", 4.3, 0.06, "ммоль/л на г"),
    ),
    crossings = listOf(
        BreakdownCrossingUi(
            kind = "episode",
            therapyClass = "snack",
            label = "Печенье, 53 г",
            at = at(140),
            offsetMinutes = 75,
            detail = null,
        ),
    ),
    causeText = "На фоне болюса 8,0 ЕД: 3,6 → 7,9 (+4,3) за 58 мин.",
    frequencyLabel = "Таких приёмов за 30 дней: 3",
)
