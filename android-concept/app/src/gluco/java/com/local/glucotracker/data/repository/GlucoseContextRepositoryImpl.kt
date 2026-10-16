package com.local.glucotracker.data.repository

import com.local.glucotracker.data.api.GlucoseApi
import com.local.glucotracker.domain.model.ActiveGlucoseContext
import com.local.glucotracker.domain.model.BodySpan
import com.local.glucotracker.domain.model.GlucoseEpisodeMark
import com.local.glucotracker.domain.model.GlucoseTirDay
import com.local.glucotracker.domain.model.InsulinEvent
import com.local.glucotracker.domain.repository.GlucoseContextRepository
import com.local.glucotracker.generated.model.BodyStateIntervalResponse
import com.local.glucotracker.generated.model.DayEpisodeInsulinResponse
import com.local.glucotracker.generated.model.DayEpisodeResponse
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.math.roundToInt
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flowOf
import kotlinx.datetime.DatePeriod
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.plus
import kotlinx.datetime.toLocalDateTime

/** Window for the IOB/COB summary call: only `summary` is read from it. */
private const val ActiveContextLookbackMillis = 15L * 60L * 1_000L

/** `/glucose/tir-daily` only knows these periods; seven days covers today. */
private const val TirPeriod = "7d"

@Singleton
class GlucoseContextRepositoryImpl @Inject constructor(
    private val insulinRepository: InsulinRepository,
    private val glucoseApi: GlucoseApi,
) : GlucoseContextRepository {

    override fun observeInsulin(from: Instant, to: Instant): Flow<List<InsulinEvent>> {
        val days = localDaysBetween(from, to)
        if (days.isEmpty()) return flowOf(emptyList())
        return combine(days.map(insulinRepository::observeContextForDay)) { contexts ->
            contexts
                .flatMap { it.allEvents }
                .filter { it.timestamp >= from && it.timestamp <= to }
                .distinctBy { it.id }
                .sortedBy { it.timestamp }
        }
    }

    override suspend fun refreshInsulin(from: Instant, to: Instant) {
        localDaysBetween(from, to).forEach { day ->
            runCatching { insulinRepository.refreshDay(day) }
        }
    }

    override suspend fun bodySpans(from: Instant, to: Instant): List<BodySpan> =
        glucoseApi.bodyStates(from = from, to = to).states.map { it.toBodySpan() }

    override suspend fun episodes(from: Instant, to: Instant): List<GlucoseEpisodeMark> =
        glucoseApi.episodes(from = from, to = to).episodes.map { it.toMark() }

    override suspend fun activeContext(now: Instant): ActiveGlucoseContext? {
        val summary = glucoseApi.dashboard(
            from = Instant.fromEpochMilliseconds(now.toEpochMilliseconds() - ActiveContextLookbackMillis),
            to = now,
        ).summary
        return ActiveGlucoseContext(
            iobUnits = summary.iobUnits?.toDouble() ?: 0.0,
            iobMinutesRemaining = summary.iobMinutesRemaining,
            cobGrams = summary.cobG?.toDouble() ?: 0.0,
            cobMinutesRemaining = summary.cobMinutesRemaining,
        )
    }

    override suspend fun tirForDay(date: LocalDate): GlucoseTirDay? =
        glucoseApi.tirDaily(TirPeriod).days
            .firstOrNull { it.date == date }
            ?.let { day ->
                GlucoseTirDay(
                    date = day.date,
                    veryLowPercent = day.veryLowPct?.toDouble(),
                    lowPercent = day.lowPct?.toDouble(),
                    inRangePercent = day.inRangePct?.toDouble(),
                    highPercent = day.highPct?.toDouble(),
                    veryHighPercent = day.veryHighPct?.toDouble(),
                )
            }
}

/** Local days a range touches; insulin is cached per local day. */
internal fun localDaysBetween(
    from: Instant,
    to: Instant,
    zone: TimeZone = TimeZone.currentSystemDefault(),
): List<LocalDate> {
    if (to < from) return emptyList()
    val first = from.toLocalDateTime(zone).date
    val last = to.toLocalDateTime(zone).date
    return generateSequence(first) { day -> day.plus(DatePeriod(days = 1)).takeIf { it <= last } }.toList()
}

private fun BodyStateIntervalResponse.toBodySpan(): BodySpan = BodySpan(
    kind = when (kind) {
        BodyStateIntervalResponse.Kind.SLEEP -> BodySpan.Kind.Sleep
        BodyStateIntervalResponse.Kind.ACTIVITY -> BodySpan.Kind.Activity
    },
    startAt = startAt,
    endAt = endAt,
    totalMinutes = totalMinutes,
    label = label?.takeIf { it.isNotBlank() },
    inferred = source == BodyStateIntervalResponse.Source.HEART_RATE,
    meanBpm = meanBpm?.toDouble()?.roundToInt(),
)

private fun DayEpisodeResponse.toMark(): GlucoseEpisodeMark {
    val doses = insulin.filter { (it.insulinUnits?.toDouble() ?: 0.0) > 0.0 }
    return GlucoseEpisodeMark(
        key = key,
        startAt = startAt,
        mealIds = mealIds.mapTo(mutableSetOf()) { it.toString() },
        insulinIds = insulin.mapTo(mutableSetOf()) { it.id.toString() },
        totalCarbsG = totalCarbsG.toDouble(),
        totalInsulinUnits = totalInsulinUnits.toDouble(),
        firstInsulinAt = doses.minOfOrNull { it.timestamp },
        correctionOnly = doses.isNotEmpty() && doses.none { it.kind == DayEpisodeInsulinResponse.Kind.FOOD },
    )
}
