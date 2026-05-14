package com.local.glucotracker.ui.glucose

import androidx.compose.runtime.Composable
import androidx.compose.runtime.ProvidableCompositionLocal
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate

interface GlucoseSurfaces {
    @Composable
    fun MiniGlucoseCard(modifier: Modifier = Modifier)

    @Composable
    fun StatsTirSection()

    @Composable
    fun StatsDaypartSection()

    @Composable
    fun RecordGlucoseAtMealPanel(eatenAt: Instant)

    @Composable
    fun StackMealGlucoseMetaRow(eatenAt: Instant)

    @Composable
    fun HistoryDayCgmSparkline(date: LocalDate)

    @Composable
    fun MoreNightscoutSection()
}

val LocalGlucoseSurfaces: ProvidableCompositionLocal<GlucoseSurfaces> =
    staticCompositionLocalOf { GlucoseSurfacesNoop }

object GlucoseSurfacesNoop : GlucoseSurfaces {
    @Composable
    override fun MiniGlucoseCard(modifier: Modifier) = Unit

    @Composable
    override fun StatsTirSection() = Unit

    @Composable
    override fun StatsDaypartSection() = Unit

    @Composable
    override fun RecordGlucoseAtMealPanel(eatenAt: Instant) = Unit

    @Composable
    override fun StackMealGlucoseMetaRow(eatenAt: Instant) = Unit

    @Composable
    override fun HistoryDayCgmSparkline(date: LocalDate) = Unit

    @Composable
    override fun MoreNightscoutSection() = Unit
}
