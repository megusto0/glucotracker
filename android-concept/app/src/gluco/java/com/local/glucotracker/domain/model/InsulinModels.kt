package com.local.glucotracker.domain.model

import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlin.math.abs

data class InsulinEvent(
    val id: String,
    val timestamp: Instant,
    val doseUnits: Double,
    val source: String,
    val sourceEventId: String?,
    val eventType: InsulinEventType,
    val isReadOnly: Boolean = true,
)

enum class InsulinEventType {
    Bolus,
    Correction,
    Basal,
    Unknown,
}

data class MealWithInsulin<T>(
    val meal: T,
    val pairedInsulin: List<InsulinEvent>,
)

data class DayContent<T>(
    val date: LocalDate,
    val mealsWithInsulin: List<MealWithInsulin<T>>,
    val orphanInsulin: List<InsulinEvent>,
)

data class PairableMeal<T>(
    val value: T,
    val id: String,
    val eatenAt: Instant,
)

fun <T> pairInsulinWithMeals(
    date: LocalDate,
    meals: List<PairableMeal<T>>,
    insulinEvents: List<InsulinEvent>,
): DayContent<T> {
    val visibleEvents = insulinEvents
        .filter { event -> event.doseUnits > 0.0 && event.eventType != InsulinEventType.Basal }
        .sortedBy { event -> event.timestamp }
    val grouped = meals.associate { meal -> meal.id to mutableListOf<InsulinEvent>() }
    val orphan = mutableListOf<InsulinEvent>()

    visibleEvents.forEach { event ->
        val closestMeal = meals
            .filter { meal -> event.timestamp in meal.windowStart..meal.windowEnd }
            .minWithOrNull(
                compareBy<PairableMeal<T>> { meal ->
                    abs(event.timestamp.toEpochMilliseconds() - meal.eatenAt.toEpochMilliseconds())
                }.thenBy { meal -> meal.eatenAt },
            )

        if (closestMeal == null) {
            orphan += event
        } else {
            grouped.getValue(closestMeal.id) += event
        }
    }

    return DayContent(
        date = date,
        mealsWithInsulin = meals
            .sortedByDescending { meal -> meal.eatenAt }
            .map { meal ->
                MealWithInsulin(
                    meal = meal.value,
                    pairedInsulin = grouped.getValue(meal.id).sortedBy { event -> event.timestamp },
                )
            },
        orphanInsulin = orphan.sortedByDescending { event -> event.timestamp },
    )
}

private val <T> PairableMeal<T>.windowStart: Instant
    get() = Instant.fromEpochMilliseconds(eatenAt.toEpochMilliseconds() - PairWindowBeforeMillis)

private val <T> PairableMeal<T>.windowEnd: Instant
    get() = Instant.fromEpochMilliseconds(eatenAt.toEpochMilliseconds() + PairWindowAfterMillis)

private const val PairWindowBeforeMillis = 15 * 60 * 1_000L
private const val PairWindowAfterMillis = 30 * 60 * 1_000L
