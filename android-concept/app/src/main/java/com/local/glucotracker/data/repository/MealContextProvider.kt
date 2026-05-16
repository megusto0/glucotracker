package com.local.glucotracker.data.repository

import kotlinx.datetime.Instant

data class MealContextFlags(
    val hasCgm: Boolean = false,
    val hasInsulin: Boolean = false,
)

interface MealContextProvider {
    suspend fun contextByMealId(from: Instant, to: Instant): Map<String, MealContextFlags>
}

object NoopMealContextProvider : MealContextProvider {
    override suspend fun contextByMealId(from: Instant, to: Instant): Map<String, MealContextFlags> =
        emptyMap()
}
