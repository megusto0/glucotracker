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
data class InsulinDayContext(
    val byMealId: Map<String, List<InsulinEvent>>,
    val orphans: List<InsulinEvent>,
) {
    val allEvents: List<InsulinEvent>
        get() = byMealId.values.flatten() + orphans

    companion object {
        val Empty = InsulinDayContext(byMealId = emptyMap(), orphans = emptyList())
    }
}
