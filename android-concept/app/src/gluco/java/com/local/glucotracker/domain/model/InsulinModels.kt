package com.local.glucotracker.domain.model

import kotlinx.datetime.Instant

data class InsulinEvent(
    val id: String,
    val timestamp: Instant,
    val doseUnits: Double,
    val source: String,
    val sourceEventId: String?,
    val eventType: InsulinEventType,
    val isReadOnly: Boolean = true,
    // Optimistic row from the local outbox, not yet visible on the server.
    val isPending: Boolean = false,
)

enum class InsulinEventType {
    Bolus,

    /**
     * Given to chase a rise the meal was already causing, once the first bolus
     * had visibly not held. Neither ordinary meal insulin nor a correction: it
     * knows something the dose at the plate could not.
     */
    CatchUp,
    Correction,
    Basal,
    Unknown,
}

/**
 * Backend-attributed insulin for one local day.
 *
 * Grouping comes from the unified episodes engine: [byMealId] maps a meal id
 * to the insulin events anchored to it; [orphans] are standalone events
 * (corrections) plus optimistic outbox entries not yet on the server.
 */
/**
 * How the backend read an episode: food, a small one, sugar taken to recover
 * from a low, or insulin given on its own. Assigned by the episode engine, not
 * inferred on the client.
 */
enum class EpisodeTherapyClass {
    Meal,
    Snack,
    CarbCorrection,
    InsulinCorrection,
    Mixed,
    Unresolved,
}

enum class EpisodeOutcomeStatus {
    Complete,
    Ongoing,
    NoCgm,
}

enum class EpisodeOutcomeKind {
    Peak,
    Recovery,
    Minimum,
}

/** Backend-owned facts for the compact diary footer. */
data class EpisodeFooterOutcome(
    val status: EpisodeOutcomeStatus,
    val kind: EpisodeOutcomeKind,
    val startValue: Double?,
    val resultValue: Double?,
    val deltaMmolL: Double?,
    val isLow: Boolean,
)

data class EpisodeFooterSummary(
    val episodeKey: String,
    val classification: EpisodeTherapyClass,
    val outcome: EpisodeFooterOutcome,
)

data class InsulinDayContext(
    val byMealId: Map<String, List<InsulinEvent>>,
    val orphans: List<InsulinEvent>,
    // Meal ids that the backend episode engine groups as one eating event
    // (only groups with 2+ meals). Drives "one card per episode" on Today.
    val mealEpisodeGroups: List<List<String>> = emptyList(),
    // Backend classification per meal id. A rescue eaten to climb out of a low
    // and an ordinary plate are different acts and should not read alike.
    val classificationByMealId: Map<String, EpisodeTherapyClass> = emptyMap(),
    // The episode key each meal belongs to, which is what the breakdown is
    // fetched by. Server-assigned, never rebuilt here: it is derived from the
    // grouping and a key assembled on the client would resolve to nothing.
    val episodeKeyByMealId: Map<String, String> = emptyMap(),
    // Backend-owned recommendation context. Every meal id in a multi-dish
    // sitting is included so the shared sitting header can render one marker.
    val firstAfterSleepMealIds: Set<String> = emptySet(),
    // Compact server-calculated result, indexed both ways so standalone
    // insulin corrections can use the same footer as meal episodes.
    val footerByMealId: Map<String, EpisodeFooterSummary> = emptyMap(),
    val footerByInsulinId: Map<String, EpisodeFooterSummary> = emptyMap(),
) {
    val allEvents: List<InsulinEvent>
        get() = byMealId.values.flatten() + orphans

    companion object {
        val Empty = InsulinDayContext(byMealId = emptyMap(), orphans = emptyList())
    }
}
