package com.local.glucotracker.data.repository

import com.local.glucotracker.data.api.GlucoseApi
import com.local.glucotracker.data.auth.AuthRepository
import com.local.glucotracker.data.local.CachedEpisodeEntity
import com.local.glucotracker.data.local.CachedInsulinEventDao
import com.local.glucotracker.data.local.CachedInsulinEventEntity
import com.local.glucotracker.domain.model.EpisodeFooterOutcome
import com.local.glucotracker.domain.model.EpisodeFooterSummary
import com.local.glucotracker.domain.model.EpisodeOutcomeKind
import com.local.glucotracker.domain.model.EpisodeOutcomeStatus
import com.local.glucotracker.domain.model.EpisodeTherapyClass
import com.local.glucotracker.domain.model.InsulinDayContext
import com.local.glucotracker.domain.model.InsulinEvent
import com.local.glucotracker.domain.model.InsulinEventType
import com.local.glucotracker.generated.model.DayEpisodeOutcomeResponse
import com.local.glucotracker.generated.model.DayEpisodeTherapyResponse
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.datetime.Clock
import kotlinx.datetime.DatePeriod
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.atStartOfDayIn
import kotlinx.datetime.plus

private const val CorrectionKind = "correction"
private const val CatchUpKind = "catch_up"

@Singleton
@OptIn(ExperimentalCoroutinesApi::class)
class InsulinRepository @Inject constructor(
    private val glucoseApi: GlucoseApi,
    private val insulinEventDao: CachedInsulinEventDao,
    private val authRepository: AuthRepository,
) {
    /**
     * Local-first day attribution. Both event rows and their backend episode
     * snapshot come from Room, so grouping, labels and footers survive process
     * death and never leak across signed-in users.
     */
    fun observeContextForDay(date: LocalDate): Flow<InsulinDayContext> =
        authRepository.observeSession().flatMapLatest { session ->
            if (session == null) {
                flowOf(InsulinDayContext.Empty)
            } else {
                val userId = session.userId.toString()
                combine(
                    insulinEventDao.observeDay(userId, date),
                    insulinEventDao.observeEpisodesDay(userId, date),
                ) { events, episodes -> cachedContext(events, episodes) }
            }
        }

    /** Pull a complete backend-owned day snapshot into the cache. */
    suspend fun refreshDay(date: LocalDate) {
        val zone = TimeZone.currentSystemDefault()
        val from = date.atStartOfDayIn(zone)
        val to = date.plus(DatePeriod(days = 1)).atStartOfDayIn(zone)
        val fetchedAt = Clock.System.now()
        val userId = authRepository.observeSession().filterNotNull().first().userId.toString()
        val episodes = glucoseApi.episodes(from, to).episodes
        val eventEntities = episodes.flatMap { episode ->
            episode.insulin.mapNotNull { event ->
                val dose = event.insulinUnits?.toDouble() ?: return@mapNotNull null
                if (dose <= 0.0) return@mapNotNull null
                CachedInsulinEventEntity(
                    id = event.id.toString(),
                    userId = userId,
                    day = date,
                    timestamp = event.timestamp,
                    doseUnits = dose,
                    kind = event.kind.value,
                    anchorMealId = event.anchorMealId?.toString(),
                    isEditable = event.editable == true,
                    fetchedAt = fetchedAt,
                )
            }
        }
        val episodeEntities = episodes.map { episode ->
            CachedEpisodeEntity(
                userId = userId,
                key = episode.key,
                day = date,
                startAt = episode.startAt,
                classification = episode.therapy.classification.value,
                mealIdsCsv = episode.mealIds.joinToString(","),
                insulinIdsCsv = episode.insulin.joinToString(",") { it.id.toString() },
                outcomeStatus = episode.outcome.status.value,
                outcomeKind = episode.outcome.kind.value,
                outcomeStartValue = episode.outcome.startValue?.toDouble(),
                outcomeResultValue = episode.outcome.resultValue?.toDouble(),
                outcomeDeltaMmolL = episode.outcome.deltaMmolL?.toDouble(),
                outcomeIsLow = episode.outcome.isLow == true,
                fetchedAt = fetchedAt,
            )
        }
        // The visible insulin and the metadata explaining its grouping/footer
        // are one snapshot, never two independently observable refreshes.
        insulinEventDao.replaceDay(userId, date, eventEntities, episodeEntities)
    }
}

internal fun cachedContext(
    eventEntities: List<CachedInsulinEventEntity>,
    episodeEntities: List<CachedEpisodeEntity>,
): InsulinDayContext {
    val byMealId = mutableMapOf<String, MutableList<InsulinEvent>>()
    val orphans = mutableListOf<InsulinEvent>()
    eventEntities.forEach { entity ->
        val event = entity.toDomain()
        val anchorMealId = entity.anchorMealId
        if (anchorMealId != null) {
            byMealId.getOrPut(anchorMealId) { mutableListOf() }.add(event)
        } else {
            orphans.add(event)
        }
    }
    val summaries = episodeEntities.associateWith { it.toFooterSummary() }
    return InsulinDayContext(
        byMealId = byMealId,
        orphans = orphans,
        mealEpisodeGroups = episodeEntities.map { it.mealIds() }.filter { it.size >= 2 },
        classificationByMealId = buildMap {
            summaries.forEach { (episode, summary) ->
                episode.mealIds().forEach { put(it, summary.classification) }
            }
        },
        episodeKeyByMealId = buildMap {
            episodeEntities.forEach { episode ->
                episode.mealIds().forEach { put(it, episode.key) }
            }
        },
        footerByMealId = buildMap {
            summaries.forEach { (episode, summary) ->
                episode.mealIds().forEach { put(it, summary) }
            }
        },
        footerByInsulinId = buildMap {
            summaries.forEach { (episode, summary) ->
                episode.insulinIds().forEach { put(it, summary) }
            }
        },
    )
}

private fun CachedEpisodeEntity.mealIds(): List<String> =
    mealIdsCsv.split(',').filter { it.isNotBlank() }

private fun CachedEpisodeEntity.insulinIds(): List<String> =
    insulinIdsCsv.split(',').filter { it.isNotBlank() }

internal fun CachedEpisodeEntity.toFooterSummary(): EpisodeFooterSummary =
    EpisodeFooterSummary(
        episodeKey = key,
        classification = classification.toTherapyClass(),
        outcome = EpisodeFooterOutcome(
            status = outcomeStatus.toOutcomeStatus(),
            kind = outcomeKind.toOutcomeKind(),
            startValue = outcomeStartValue,
            resultValue = outcomeResultValue,
            deltaMmolL = outcomeDeltaMmolL,
            isLow = outcomeIsLow,
        ),
    )

private fun DayEpisodeTherapyResponse.Classification.toDomain(): EpisodeTherapyClass =
    when (this) {
        DayEpisodeTherapyResponse.Classification.MEAL -> EpisodeTherapyClass.Meal
        DayEpisodeTherapyResponse.Classification.SNACK -> EpisodeTherapyClass.Snack
        DayEpisodeTherapyResponse.Classification.CARB_CORRECTION ->
            EpisodeTherapyClass.CarbCorrection
        DayEpisodeTherapyResponse.Classification.INSULIN_CORRECTION ->
            EpisodeTherapyClass.InsulinCorrection
        DayEpisodeTherapyResponse.Classification.MIXED -> EpisodeTherapyClass.Mixed
        DayEpisodeTherapyResponse.Classification.UNRESOLVED -> EpisodeTherapyClass.Unresolved
    }

private fun String.toTherapyClass(): EpisodeTherapyClass =
    DayEpisodeTherapyResponse.Classification.entries
        .firstOrNull { it.value == this }
        ?.toDomain()
        ?: EpisodeTherapyClass.Unresolved

private fun String.toOutcomeStatus(): EpisodeOutcomeStatus = when (this) {
    DayEpisodeOutcomeResponse.Status.COMPLETE.value -> EpisodeOutcomeStatus.Complete
    DayEpisodeOutcomeResponse.Status.ONGOING.value -> EpisodeOutcomeStatus.Ongoing
    else -> EpisodeOutcomeStatus.NoCgm
}

private fun String.toOutcomeKind(): EpisodeOutcomeKind = when (this) {
    DayEpisodeOutcomeResponse.Kind.PEAK.value -> EpisodeOutcomeKind.Peak
    DayEpisodeOutcomeResponse.Kind.RECOVERY.value -> EpisodeOutcomeKind.Recovery
    else -> EpisodeOutcomeKind.Minimum
}

private fun CachedInsulinEventEntity.toDomain(): InsulinEvent =
    InsulinEvent(
        id = id,
        timestamp = timestamp,
        doseUnits = doseUnits,
        source = "Nightscout",
        sourceEventId = id,
        eventType = when (kind) {
            CorrectionKind -> InsulinEventType.Correction
            CatchUpKind -> InsulinEventType.CatchUp
            else -> InsulinEventType.Bolus
        },
        isReadOnly = !isEditable,
    )
